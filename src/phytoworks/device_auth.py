"""Device authorization grant (RFC 8628) for the operator CLI and SDK.

The Hub wraps Better Auth's device plugin under ``/auth/device``:

1. ``POST /auth/device/code`` issues a device code and a short user code.
2. The user approves the user code in a browser.
3. ``POST /auth/device/token`` is polled until approval and returns the raw
   Better Auth session token of this device (not a JWT).
4. ``POST /auth/device/exchange`` turns that raw token, sent only as a Bearer
   header, into a short-lived API JWT; it is called again to refresh.
5. ``POST /auth/device/revoke`` ends exactly this device's session.

The raw session token is a secret: it is never printed, logged, or placed in
an exception or ``repr``.  Exceptions raised on these paths use ``from None``
so a traceback cannot carry an HTTP request that held it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx

from ._transport import AsyncTransport, Transport
from .auth import _jwt_claims, _jwt_expiry
from .config import DeviceJwtStore, normalize_hub_url, require_secure_hub
from .errors import AuthError, PWSError, TransportError

DEVICE_CLIENT_ID = "pws-cli"
"""The Hub's allow-listed first-party client id for the ``pws`` CLI and SDK."""

DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
SLOW_DOWN_STEP = 5.0
"""RFC 8628 §3.5: the Hub never raises the interval itself, so the client adds this on ``slow_down``."""
RATE_LIMIT_FALLBACK = 60.0
"""Hub device rate limits block for 60 s and may send no ``Retry-After``."""
MAX_NETWORK_RETRIES = 5
MAX_RATE_LIMIT_RETRIES = 5
_JWT_REFRESH_MARGIN = timedelta(seconds=60)
_JWT_FALLBACK_LIFETIME = timedelta(minutes=14)
_RELOGIN = "run `pws auth login` again"


class DeviceLoginError(AuthError):
    """The device authorization grant ended without a session."""


class DeviceAccessDenied(DeviceLoginError):  # noqa: N818 - mirrors the RFC 8628 error name
    """The user denied the request in the browser."""


class DeviceCodeExpired(DeviceLoginError):  # noqa: N818 - mirrors the RFC 8628 error name
    """The user code expired before it was approved."""


@dataclass(frozen=True, slots=True)
class DeviceCode:
    """What the user needs to approve this device; ``device_code`` stays private."""

    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: float
    interval: float
    device_code: str = field(repr=False)


class DeviceSessionCredential:
    """A device session: the stored raw session token, exchanged for short-lived API JWTs.

    Implements the :class:`~phytoworks.auth.Credential` protocol.  The JWT is
    re-minted from the session token shortly before it expires, or after the
    Hub answers 401 (:meth:`invalidate`).  An exchange 401 means the session
    was revoked or expired; there is no silent fallback to a password.
    """

    def __init__(
        self,
        session_token: str,
        *,
        hub_url: str | None = None,
        store: DeviceJwtStore | None = None,
        sleep: Callable[[float], None] | None = None,
        notice: Callable[[str], None] | None = None,
        _logger: logging.Logger | None = None,
    ) -> None:
        if not session_token.strip():
            raise ValueError("session_token must not be empty")
        self._session_token = session_token
        self._hub_url = normalize_hub_url(hub_url) if hub_url else None
        self._store = store
        self._sleep = sleep
        self._notice = notice or _stderr_notice
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._refresh_lock = threading.Lock()
        self._async_refresh_lock = asyncio.Lock()
        self._logger = _logger or logging.getLogger(__name__)
        cached = None
        if store is not None:
            try:
                cached = store.load()
            except (OSError, ValueError):
                cached = None
        if cached is not None:
            self._access_token, self._expires_at = cached

    def __repr__(self) -> str:
        expires = self._expires_at.isoformat(timespec="seconds") if self._expires_at else None
        return f"DeviceSessionCredential(expires_at={expires!r})"

    @property
    def session_token(self) -> str:
        """The raw device session token; store it with mode 0600 and never print it."""

        return self._session_token

    @property
    def user_id(self) -> str | None:
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

    def invalidate(self) -> None:
        """Forget the current JWT, in memory and in the profile cache, so the next refresh re-exchanges."""

        self._access_token = None
        self._expires_at = None
        self._persist(None)

    def refresh(self, transport: Transport) -> None:
        with self._refresh_lock:
            # Checked before the cached-JWT shortcut: a cached JWT is a credential too.
            self._check_hub(transport.base_url)
            if self._token_is_valid():
                return
            for attempt in range(2):
                payload, error = _exchange(transport, self._bearer())
                if error is None:
                    self._store_token(payload)
                    return
                if error.status_code == 401:
                    self.invalidate()
                if attempt == 0 and error.status_code == 429:
                    delay = _exchange_retry_delay(error)
                    self._notice(f"the Hub is rate limiting session refresh; waiting {delay:.0f}s")
                    (self._sleep or time.sleep)(delay)
                    continue
                raise error

    async def async_refresh(self, transport: AsyncTransport) -> None:
        async with self._async_refresh_lock:
            self._check_hub(transport.base_url)
            if self._token_is_valid():
                return
            for attempt in range(2):
                payload, error = await _async_exchange(transport, self._bearer())
                if error is None:
                    self._store_token(payload)
                    return
                if error.status_code == 401:
                    self.invalidate()
                if attempt == 0 and error.status_code == 429:
                    delay = _exchange_retry_delay(error)
                    self._notice(f"the Hub is rate limiting session refresh; waiting {delay:.0f}s")
                    await asyncio.sleep(delay) if self._sleep is None else self._sleep(delay)
                    continue
                raise error

    def _check_hub(self, base_url: str) -> None:
        """The session token only ever goes to the Hub that issued it, over a secure channel."""

        if self._hub_url is not None and normalize_hub_url(base_url) != self._hub_url:
            raise AuthError(
                f"this device session belongs to {self._hub_url}, not {normalize_hub_url(base_url)}; "
                "run `pws auth login` against that Hub"
            )
        require_secure_hub(base_url)

    def _bearer(self) -> Mapping[str, str]:
        return {"Authorization": f"Bearer {self._session_token}"}

    def _store_token(self, payload: object) -> None:
        token = payload.get("token") if isinstance(payload, Mapping) else None
        if not isinstance(token, str) or not token:
            raise AuthError("device session exchange did not return a token", status_code=401)
        self._access_token = token
        self._expires_at = _jwt_expiry(token) or (datetime.now(UTC) + _JWT_FALLBACK_LIFETIME)
        self._persist((token, self._expires_at))
        self._logger.debug("Device session credential established")

    def _persist(self, jwt: tuple[str, datetime] | None) -> None:
        """Update the profile's JWT cache; a cache that cannot be written (read-only file) is only a lost optimization."""

        if self._store is None:
            return
        try:
            if jwt is None:
                self._store.clear()
            else:
                self._store.save(*jwt)
        except OSError:
            self._logger.debug("Device session JWT cache not updated; continuing with the in-memory JWT")

    def _token_is_valid(self) -> bool:
        if self._access_token is None or self._expires_at is None:
            return False
        return datetime.now(UTC) < self._expires_at - _JWT_REFRESH_MARGIN


def _stderr_notice(message: str) -> None:
    print(f"pws: {message}", file=sys.stderr)


# Errors on token-bearing requests are built inside ``except`` but raised
# outside it: an exception raised within the handler would keep the original
# (whose HTTP request carried the Bearer session token) as its ``__context__``.


def _exchange(transport: Transport, headers: Mapping[str, str]) -> tuple[object, PWSError | None]:
    try:
        return transport.request("POST", "/auth/device/exchange", headers=headers), None
    except PWSError as exc:
        error = _exchange_error(exc)
    return None, error


async def _async_exchange(transport: AsyncTransport, headers: Mapping[str, str]) -> tuple[object, PWSError | None]:
    try:
        return await transport.request("POST", "/auth/device/exchange", headers=headers), None
    except PWSError as exc:
        error = _exchange_error(exc)
    return None, error


def _exchange_error(exc: PWSError) -> PWSError:
    if exc.status_code == 401:
        return AuthError(f"the device session expired or was revoked; {_RELOGIN}", status_code=401)
    if exc.status_code == 429:
        return _RateLimitedExchangeError(getattr(exc, "retry_after", None))
    if isinstance(exc, TransportError) and exc.status_code is None:
        return TransportError("device session exchange failed: the Hub could not be reached")
    return AuthError("device session exchange failed", status_code=exc.status_code)


class _RateLimitedExchangeError(AuthError):
    def __init__(self, retry_after: float | None) -> None:
        super().__init__("device session refresh stayed rate limited; retry in a minute", status_code=429)
        self.retry_after = retry_after


def _exchange_retry_delay(error: PWSError) -> float:
    retry_after = getattr(error, "retry_after", None)
    return float(retry_after) if isinstance(retry_after, (int, float)) and retry_after >= 0 else RATE_LIMIT_FALLBACK


RevokeOutcome = Literal["revoked", "already_revoked"]


def revoke_device_session(transport: Transport, session_token: str) -> RevokeOutcome:
    """End exactly this device's session on the Hub.

    ``revoked`` on 200; ``already_revoked`` on 401 (the Hub answers 401 alike
    for unknown, expired and revoked sessions).  A network failure raises
    :class:`TransportError` so the caller keeps its local credential.
    """

    require_secure_hub(transport.base_url)
    response: httpx.Response | None = None
    try:
        response = transport.request_raw(
            "POST", "/auth/device/revoke", headers={"Authorization": f"Bearer {session_token}"}
        )
    except PWSError:
        pass
    if response is None:
        raise TransportError("device session revoke failed: the Hub could not be reached")
    return _revoke_outcome(response)


async def async_revoke_device_session(transport: AsyncTransport, session_token: str) -> RevokeOutcome:
    """Async twin of :func:`revoke_device_session`."""

    require_secure_hub(transport.base_url)
    response: httpx.Response | None = None
    try:
        response = await transport.request_raw(
            "POST", "/auth/device/revoke", headers={"Authorization": f"Bearer {session_token}"}
        )
    except PWSError:
        pass
    if response is None:
        raise TransportError("device session revoke failed: the Hub could not be reached")
    return _revoke_outcome(response)


def _revoke_outcome(response: httpx.Response) -> RevokeOutcome:
    """Map the Hub revoke answer; anything but a confirmed revoke or a 401 keeps the local credential."""

    if response.status_code == 200:
        body = _json(response)
        data = body.get("data")
        if body.get("success") is True and isinstance(data, Mapping) and data.get("status") is True:
            return "revoked"
        raise TransportError("the Hub answered the device session revoke unexpectedly; retry", status_code=200)
    if response.status_code == 401:
        return "already_revoked"
    if response.status_code == 429:
        raise TransportError("device session revoke is rate limited; retry shortly", status_code=429)
    if response.status_code == 503:
        # The Hub blacklists this session's JWTs before deleting it; on failure the session is intact.
        raise TransportError("the Hub could not finish revoking this device session; retry", status_code=503)
    raise TransportError("device session revoke failed", status_code=response.status_code)


# ---------------------------------------------------------------------------
# The grant: code issue and polling
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _PollState:
    interval: float
    deadline: float
    network_failures: int = 0
    rate_limited: int = 0


class _Step:
    """One poll outcome: wait ``delay`` seconds and poll again, or finish with a token."""

    __slots__ = ("delay", "token")

    def __init__(self, *, delay: float = 0.0, token: str | None = None) -> None:
        self.delay = delay
        self.token = token


class DeviceLogin:
    """Run the device authorization grant against the Hub (synchronous).

    >>> login = DeviceLogin(transport)
    >>> code = login.start()
    >>> print(code.verification_uri_complete or code.verification_uri, code.user_code)
    >>> credential = login.wait(code)
    """

    def __init__(
        self,
        transport: Transport,
        *,
        client_id: str = DEVICE_CLIENT_ID,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._transport = transport
        self._client_id = client_id
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic

    def start(self) -> DeviceCode:
        """Request a device code, waiting out rate limits within a bounded budget."""

        require_secure_hub(self._transport.base_url)
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            response = self._post("/auth/device/code", {"client_id": self._client_id})
            if response.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                self._sleep(_rate_limit_delay(response, 0.0))
                continue
            return _device_code(response)
        raise AssertionError("unreachable")

    def wait(self, code: DeviceCode) -> DeviceSessionCredential:
        """Poll until the user approves, honouring ``interval`` and ``slow_down``."""

        state = _PollState(interval=code.interval, deadline=self._clock() + code.expires_in)
        delay = state.interval
        while True:
            self._sleep(delay)
            if self._clock() > state.deadline:
                raise DeviceCodeExpired(f"the device code expired before it was approved; {_RELOGIN}")
            response: httpx.Response | None = None
            try:
                response = self._post("/auth/device/token", _token_body(code, self._client_id))
            except TransportError:
                pass
            step = _network_failure(state) if response is None else _poll_step(response, state)
            if step.token is not None:
                return DeviceSessionCredential(step.token, hub_url=self._transport.base_url)
            delay = step.delay

    def _post(self, path: str, body: Mapping[str, str]) -> httpx.Response:
        return self._transport.request_raw("POST", path, json_body=dict(body))


class AsyncDeviceLogin:
    """Async twin of :class:`DeviceLogin`."""

    def __init__(
        self,
        transport: AsyncTransport,
        *,
        client_id: str = DEVICE_CLIENT_ID,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._transport = transport
        self._client_id = client_id
        self._sleep = sleep or asyncio.sleep
        self._clock = clock or time.monotonic

    async def start(self) -> DeviceCode:
        require_secure_hub(self._transport.base_url)
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            response = await self._post("/auth/device/code", {"client_id": self._client_id})
            if response.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                await self._sleep(_rate_limit_delay(response, 0.0))
                continue
            return _device_code(response)
        raise AssertionError("unreachable")

    async def wait(self, code: DeviceCode) -> DeviceSessionCredential:
        state = _PollState(interval=code.interval, deadline=self._clock() + code.expires_in)
        delay = state.interval
        while True:
            await self._sleep(delay)
            if self._clock() > state.deadline:
                raise DeviceCodeExpired(f"the device code expired before it was approved; {_RELOGIN}")
            response: httpx.Response | None = None
            try:
                response = await self._post("/auth/device/token", _token_body(code, self._client_id))
            except TransportError:
                pass
            step = _network_failure(state) if response is None else _poll_step(response, state)
            if step.token is not None:
                return DeviceSessionCredential(step.token, hub_url=self._transport.base_url)
            delay = step.delay

    async def _post(self, path: str, body: Mapping[str, str]) -> httpx.Response:
        return await self._transport.request_raw("POST", path, json_body=dict(body))


def _token_body(code: DeviceCode, client_id: str) -> Mapping[str, str]:
    return {"grant_type": DEVICE_GRANT_TYPE, "device_code": code.device_code, "client_id": client_id}


def _device_code(response: httpx.Response) -> DeviceCode:
    if response.status_code != 200:
        raise _issue_error(response)
    body = _json(response)
    user_code = body.get("user_code")
    device_code = body.get("device_code")
    uri = body.get("verification_uri")
    if not (isinstance(user_code, str) and isinstance(device_code, str) and isinstance(uri, str)):
        raise DeviceLoginError("the Hub device code response is incomplete", status_code=response.status_code)
    complete = body.get("verification_uri_complete")
    return DeviceCode(
        user_code=user_code,
        verification_uri=uri,
        verification_uri_complete=complete if isinstance(complete, str) else None,
        expires_in=_seconds(body.get("expires_in"), 1800.0),
        interval=_seconds(body.get("interval"), 5.0),
        device_code=device_code,
    )


def _issue_error(response: httpx.Response) -> PWSError:
    error = _error_code(response)
    if response.status_code == 429:
        return DeviceLoginError("device login is rate limited; wait a minute and retry", status_code=429)
    if error == "invalid_client":
        return DeviceLoginError("the Hub does not accept this CLI as a device client", status_code=400)
    return DeviceLoginError("the Hub refused to start device login", status_code=response.status_code)


def _poll_step(response: httpx.Response, state: _PollState) -> _Step:
    if response.status_code == 200:
        token = _json(response).get("access_token")
        if not isinstance(token, str) or not token:
            raise DeviceLoginError("the Hub approved the device but returned no session", status_code=200)
        return _Step(token=token)
    if response.status_code == 429:
        state.rate_limited += 1
        if state.rate_limited > MAX_RATE_LIMIT_RETRIES:
            raise DeviceLoginError("device login stayed rate limited; wait a minute and retry", status_code=429)
        return _Step(delay=_rate_limit_delay(response, state.interval))
    state.network_failures = 0
    error = _error_code(response)
    if error == "authorization_pending":
        return _Step(delay=state.interval)
    if error == "slow_down":
        state.interval += SLOW_DOWN_STEP
        return _Step(delay=state.interval)
    if error == "access_denied":
        raise DeviceAccessDenied(f"the device login was denied in the browser; {_RELOGIN}", status_code=400)
    if error == "expired_token":
        raise DeviceCodeExpired(f"the device code expired before it was approved; {_RELOGIN}", status_code=400)
    if error == "invalid_grant":
        raise DeviceLoginError(
            f"the device code is no longer valid (used, denied, or expired); {_RELOGIN}", status_code=400
        )
    raise DeviceLoginError("the Hub rejected the device login poll", status_code=response.status_code)


def _network_failure(state: _PollState) -> _Step:
    state.network_failures += 1
    if state.network_failures > MAX_NETWORK_RETRIES:
        raise TransportError("device login lost contact with the Hub; check the network and run `pws auth login`")
    return _Step(delay=state.interval * (2 ** min(state.network_failures, 4)))


def _rate_limit_delay(response: httpx.Response, interval: float) -> float:
    retry_after = response.headers.get("Retry-After")
    try:
        seconds = float(retry_after) if retry_after is not None else None
    except ValueError:
        seconds = None
    if seconds is not None and seconds >= 0:
        return max(seconds, interval)
    return max(RATE_LIMIT_FALLBACK, interval)


def _error_code(response: httpx.Response) -> str | None:
    error = _json(response).get("error")
    return error if isinstance(error, str) else None


def _json(response: httpx.Response) -> Mapping[str, object]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, Mapping) else {}


def _seconds(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) and value > 0 else default
