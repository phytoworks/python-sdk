"""Credential exchange for the Hub operator API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ._transport import AsyncTransport, Transport
from .config import require_secure_hub
from .errors import AuthError


class Credential(Protocol):
    """The small credential contract consumed by both PWS facades."""

    def headers(self) -> Mapping[str, str]:
        """Return headers for the next API request."""

    def refresh(self, transport: Transport) -> None:
        """Exchange bootstrap credentials for a session when needed."""

    async def async_refresh(self, transport: AsyncTransport) -> None:
        """Async equivalent of :meth:`refresh`."""


class ApiKeyCredential:
    """Device-plane bootstrap: an agent access key exchanged for an agent JWT.

    The JWT that ``POST /agents/device/self-discovery`` returns authenticates
    ``/agents/*`` routes only.  Operator routes such as ``/organizations`` or
    ``/media/capture-sessions`` are guarded by Better Auth and answer 401 to
    it -- sign in with ``pws auth login`` (a device session) for those until a
    server-side operator key exists (Phase 2).
    """

    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._access_token: str | None = None
        self.expires_at: datetime | None = None
        self.jwks_url: str | None = None
        self._refresh_lock = threading.Lock()
        self._async_refresh_lock = asyncio.Lock()

    def headers(self) -> Mapping[str, str]:
        if self._access_token is not None:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {"X-API-Key": self._api_key}

    def refresh(self, transport: Transport) -> None:
        require_secure_hub(transport.base_url)  # before the cached-JWT shortcut: a cached JWT is a credential too
        with self._refresh_lock:
            if self._token_is_valid():
                return
            payload = transport.request(
                "POST",
                "/agents/device/self-discovery",
                headers={"X-API-Key": self._api_key},
            )
            self._store_session(payload)

    async def async_refresh(self, transport: AsyncTransport) -> None:
        require_secure_hub(transport.base_url)
        async with self._async_refresh_lock:
            if self._token_is_valid():
                return
            payload = await transport.request(
                "POST",
                "/agents/device/self-discovery",
                headers={"X-API-Key": self._api_key},
            )
            self._store_session(payload)

    def _store_session(self, payload: object) -> None:
        session: object = payload
        if isinstance(payload, Mapping):
            session = payload.get("session", payload)
        if not isinstance(session, Mapping):
            raise ValueError("self-discovery response did not contain a session")
        token = session.get("accessToken", session.get("access_token"))
        if not isinstance(token, str) or not token:
            raise ValueError("self-discovery response did not contain an access token")
        self._access_token = token
        expires_at = session.get("expiresAt", session.get("expires_at"))
        self.expires_at = _parse_datetime(expires_at) if isinstance(expires_at, str) else None
        jwks_url = session.get("jwksUrl", session.get("jwks_url"))
        self.jwks_url = jwks_url if isinstance(jwks_url, str) else None

    def _token_is_valid(self) -> bool:
        if self._access_token is None:
            return False
        if self.expires_at is None:
            return True
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) < expires_at


class AgentKeyCredential(ApiKeyCredential):
    """Agent-key credential with canonical Agent.id-derived identity fields."""

    def __init__(self, api_key: str, *, agent_id: str) -> None:
        super().__init__(api_key)
        if not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        self.agent_id = agent_id

    @property
    def username(self) -> str:
        return self.agent_id

    @property
    def client_id(self) -> str:
        return f"agent-{self.agent_id}"

    @property
    def topic_root(self) -> str:
        return f"agents/{self.agent_id}"


SESSION_COOKIE = "pws.session_token"
_JWT_REFRESH_MARGIN = timedelta(seconds=60)
_JWT_FALLBACK_LIFETIME = timedelta(minutes=14)
_session_warning_emitted = False


class SessionCredential:
    """A Better Auth session token exchanged for short-lived operator JWTs.

    Operator routes (``/organizations``, ``/media/...``) accept the JWT that
    ``GET /auth/token`` mints for a Better Auth session; they reject agent JWTs
    (see :class:`ApiKeyCredential`).  This credential holds an already issued
    session token (``PWS_SESSION_TOKEN``, e.g. a CI or E2E seed) and re-mints
    the JWT from it before it expires; it never signs in.  People sign in with
    ``pws auth login`` (:class:`~phytoworks.device_auth.DeviceSessionCredential`).
    The email/password sign-in this class used to perform is retired.  The
    warning is emitted once per process.
    """

    def __init__(self, *, session_token: str, _logger: logging.Logger | None = None) -> None:
        if not session_token.strip():
            raise ValueError("session_token must not be empty")
        self._session_token = session_token
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._refresh_lock = threading.Lock()
        self._async_refresh_lock = asyncio.Lock()
        self._logger = _logger or logging.getLogger(__name__)
        _warn_once()

    @property
    def session_token(self) -> str:
        """The Better Auth session token this credential exchanges."""

        return self._session_token

    @property
    def user_id(self) -> str | None:
        """The signed-in user's Better Auth id: the ``sub`` of the current session JWT (after a refresh)."""

        subject = _jwt_claims(self._access_token).get("sub") if self._access_token else None
        return subject if isinstance(subject, str) and subject else None

    @property
    def user_email(self) -> str | None:
        email = _jwt_claims(self._access_token).get("email") if self._access_token else None
        return email if isinstance(email, str) and email else None

    @property
    def expires_at(self) -> datetime | None:
        return self._expires_at

    def headers(self) -> Mapping[str, str]:
        if self._access_token is None:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    def refresh(self, transport: Transport) -> None:
        require_secure_hub(transport.base_url)  # before the cached-JWT shortcut, as for an agent key
        with self._refresh_lock:
            if self._token_is_valid():
                return
            token_payload = transport.request("GET", "/auth/token", headers=self._cookie_header())
            self._store_token(token_payload)

    async def async_refresh(self, transport: AsyncTransport) -> None:
        require_secure_hub(transport.base_url)
        async with self._async_refresh_lock:
            if self._token_is_valid():
                return
            token_payload = await transport.request("GET", "/auth/token", headers=self._cookie_header())
            self._store_token(token_payload)

    def _cookie_header(self) -> Mapping[str, str]:
        return {"Cookie": f"{SESSION_COOKIE}={self._session_token}"}

    def _store_token(self, payload: object) -> None:
        token = payload.get("token") if isinstance(payload, Mapping) else None
        if not isinstance(token, str) or not token:
            raise AuthError("session token endpoint did not return a token", status_code=401)
        self._access_token = token
        self._expires_at = _jwt_expiry(token) or (datetime.now(UTC) + _JWT_FALLBACK_LIFETIME)
        self._logger.debug("Session credential established")

    def _token_is_valid(self) -> bool:
        if self._access_token is None or self._expires_at is None:
            return False
        return datetime.now(UTC) < self._expires_at - _JWT_REFRESH_MARGIN


def _warn_once() -> None:
    global _session_warning_emitted
    if _session_warning_emitted:
        return
    _session_warning_emitted = True
    warnings.warn(
        "SessionCredential (PWS_SESSION_TOKEN) is a development bridge; people sign in with `pws auth login`.",
        RuntimeWarning,
        stacklevel=3,
    )


def _jwt_claims(token: str) -> Mapping[str, object]:
    """Read the unverified claims; verification is the Hub's job, the SDK only reads its own session."""

    try:
        payload_segment = token.split(".")[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError, TypeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _jwt_expiry(token: str) -> datetime | None:
    exp = _jwt_claims(token).get("exp")
    if isinstance(exp, (int, float)):
        return datetime.fromtimestamp(exp, tz=UTC)
    return None


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
