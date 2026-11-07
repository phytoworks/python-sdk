"""Configuration and credentials.toml handling."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import secrets
import stat
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, TextIO
from urllib.parse import urlsplit

import httpx

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no flock; writes there are best effort
    fcntl = None  # type: ignore[assignment]

from .errors import AuthError, CredentialMissingError, ValidationError

# The production Hub; any other Hub is chosen with PWS_BASE_URL or --base-url.
DEFAULT_BASE_URL = "https://api-0.phyto-works.com/api/v1"

CredentialKind = Literal["device_session", "session", "api_key"]
CredentialSource = Literal["explicit", "environment", "profile"]


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved SDK configuration."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    org: str | None = None
    timeout: float = 30.0
    profile: str = "default"
    session_token: str | None = None
    device_session_token: str | None = None
    credentials_file: Path | None = None

    def __repr__(self) -> str:
        return (
            f"Config(base_url={self.base_url!r}, org={self.org!r}, profile={self.profile!r}, "
            f"credential={self.credential_kind!r})"
        )

    @property
    def credential_kind(self) -> CredentialKind | None:
        if self.device_session_token:
            return "device_session"
        if self.session_token:
            return "session"
        return "api_key" if self.api_key else None

    @classmethod
    def resolve(
        cls,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        org: str | None = None,
        timeout: float | None = None,
        profile: str = "default",
        credentials_file: Path | None = None,
        session_token: str | None = None,
        require_credential: bool = True,
    ) -> Config:
        """Resolve the credential and settings.

        The credential comes from exactly one source, in this order: explicit
        arguments, then ``PWS_SESSION_TOKEN`` / ``PWS_API_KEY``, then the
        credentials file (a device session, then an agent key).  A device
        session and a profile agent key stay bound to the profile's recorded
        Hub; a conflicting ``PWS_BASE_URL`` or ``base_url`` is refused. A
        legacy profile agent key with no recorded Hub needs one of those Hub
        settings and never falls back to the default. Explicit and environment
        credentials use ``base_url`` before ``PWS_BASE_URL`` and do not inherit
        the profile's Hub or organization. Organization scope uses explicit
        ``org``, then ``PWS_ORG``, then the profile's org for profile
        credentials. Without a credential, profile Hub and org remain display
        defaults for ``config show``.

        A profile still holding a session from the retired ``--password-login``
        (a ``session_token`` key) is refused with an ``AuthError`` that says to
        run ``pws auth login`` (with ``--profile`` naming any profile other than
        ``default``); it is never used, and never skipped in favour of an agent
        key in the same profile.  ``require_credential=False`` treats it as no
        credential.
        """

        path = credentials_file or credentials_path()
        file_values = _read_profile(path, profile)
        kind, secret, source = _select_credential(api_key, session_token, file_values)
        if kind == "retired_session":
            if require_credential:
                raise AuthError(
                    f"profile {profile!r} in {path} holds a session from the retired `pws auth login "
                    "--password-login`; run `pws auth login` (add `--profile <name>` for a non-default profile) "
                    "to replace it. That old session stays valid on the Hub until it expires; end it from the "
                    "session list in your account settings."
                )
            kind, secret, source = None, "", None
        if require_credential and kind is None:
            raise CredentialMissingError(
                "No PhytoWorks credential found; run `pws auth login` (device login) or set PWS_SESSION_TOKEN."
            )

        requested_base_url = base_url or os.getenv("PWS_BASE_URL")
        requested_org = org or os.getenv("PWS_ORG") or None
        if kind == "device_session":
            resolved_base_url = device_hub(file_values, requested_base_url)
        elif source == "profile":
            resolved_base_url = profile_hub(file_values, requested_base_url, profile=profile, path=path)
        else:
            resolved_base_url = (
                requested_base_url or (file_values.get("base_url") if source is None else None) or DEFAULT_BASE_URL
            )
        resolved_org = requested_org
        if resolved_org is None and source in ("profile", None):
            resolved_org = file_values.get("org")
        timeout_value = os.getenv("PWS_TIMEOUT") or file_values.get("timeout") or timeout or 30.0
        return cls(
            api_key=secret if kind == "api_key" else "",
            base_url=str(resolved_base_url).rstrip("/"),
            org=str(resolved_org) if resolved_org is not None else None,
            timeout=float(timeout_value),
            profile=profile,
            session_token=secret if kind == "session" else None,
            device_session_token=secret if kind == "device_session" else None,
            credentials_file=path,
        )

    @staticmethod
    def write_credentials(
        path: Path,
        *,
        api_key: str | None = None,
        profile: str = "default",
        base_url: str | None = None,
        org: str | None = None,
        device_session_token: str | None = None,
    ) -> None:
        """Replace the selected profile and keep every other profile; mode 0600, atomic.

        Exactly one of ``api_key`` (device plane) or ``device_session_token``
        (``pws auth login`` device flow) is stored, always with the ``base_url``
        it belongs to; a password never is.
        """

        if (api_key is None) == (device_session_token is None):
            raise ValueError("write exactly one of api_key or device_session_token")
        if not base_url:
            raise ValueError("a stored credential must record the Hub it belongs to")
        values: dict[str, str] = {}
        for key, value in (
            ("api_key", api_key),
            ("device_session_token", device_session_token),
            ("base_url", base_url),
            ("org", org),
        ):
            if value is not None:
                values[key] = value
        with _locked(path):
            document = _load_document(path)
            _set_profile(document, profile, values)
            _write_private(_dump_document(document), path)

    @staticmethod
    def delete_credentials(path: Path, *, profile: str = "default") -> bool:
        """Remove the selected profile; ``False`` when it was already absent (idempotent).

        Other profiles in the file are kept; the file is removed once empty.
        """

        with _locked(path):
            document = _load_document(path)
            if not _profile_values(document, profile):
                return False
            _set_profile(document, profile, None)
            if not document:
                path.unlink(missing_ok=True)
            else:
                _write_private(_dump_document(document), path)
        return True


class DeviceJwtStore:
    """The profile's cached short-lived API JWT, kept beside the device session that minted it.

    The raw session token in the same 0600 file is strictly more powerful than
    this JWT, so caching it adds no exposure while letting consecutive CLI runs
    reuse one exchange instead of spending the Hub's exchange budget per run.
    Writes only land while the profile still holds the same device session.
    """

    def __init__(self, path: Path, profile: str, session_token: str) -> None:
        self._path = path
        self._profile = profile
        self._session_token = session_token

    def __repr__(self) -> str:
        return f"DeviceJwtStore(path={str(self._path)!r}, profile={self._profile!r})"

    def load(self) -> tuple[str, datetime] | None:
        values = _profile_values(_load_document(self._path), self._profile)
        if values.get("device_session_token") != self._session_token:
            return None
        token, expires_at = values.get("device_jwt"), values.get("device_jwt_expires_at")
        if not (isinstance(token, str) and isinstance(expires_at, str)):
            return None
        try:
            return token, datetime.fromisoformat(expires_at)
        except ValueError:
            return None

    def save(self, token: str, expires_at: datetime) -> None:
        self._update({"device_jwt": token, "device_jwt_expires_at": expires_at.isoformat()})

    def clear(self) -> None:
        """Drop a JWT the Hub rejected, so no later process reuses it."""

        self._update(None)

    def _update(self, jwt_values: dict[str, str] | None) -> None:
        # Under the lock, and only while the profile still holds this device
        # session: a concurrent logout or re-login must win over a cache write.
        with _locked(self._path):
            document = _load_document(self._path)
            values = _profile_values(document, self._profile)
            if values.get("device_session_token") != self._session_token:
                return
            values = {key: value for key, value in values.items() if key not in _JWT_KEYS}
            if jwt_values is not None:
                values.update(jwt_values)
            _set_profile(document, self._profile, values)
            _write_private(_dump_document(document), self._path)


_TOOL_GATEWAY_SESSION_KEYS = frozenset(
    {
        "tool_gateway_hub_origin",
        "tool_gateway_org",
        "tool_gateway_user_session_sha256",
        "tool_gateway_session_id",
        "tool_gateway_token",
        "tool_gateway_expires_at",
    }
)


class ToolGatewaySessionStore:
    """One profile's current external session and its narrow Gateway credential.

    The capability shares the existing 0600 credentials file and lock. It is
    bound to the Hub origin, organization, and user session that issued it;
    replacing or removing any of those credentials makes the cache unusable.
    """

    def __init__(self, path: Path, profile: str, hub_url: str, organization_id: str, user_session: str) -> None:
        if not profile or not hub_url or not organization_id or not user_session:
            raise ValueError("profile, Hub, organization, and user session are required")
        self._path = path
        self._profile = profile
        self._hub_origin = _hub_origin(hub_url)
        self._organization_id = organization_id
        self._user_session_sha256 = hashlib.sha256(user_session.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return f"ToolGatewaySessionStore(path={str(self._path)!r}, profile={self._profile!r})"

    def load(self) -> dict[str, str] | None:
        values = _profile_values(_load_document(self._path), self._profile)
        if (
            values.get("tool_gateway_hub_origin") != self._hub_origin
            or values.get("tool_gateway_org") != self._organization_id
            or values.get("tool_gateway_user_session_sha256") != self._user_session_sha256
        ):
            return None
        session_id = values.get("tool_gateway_session_id")
        token = values.get("tool_gateway_token")
        expires_at = values.get("tool_gateway_expires_at")
        if not (isinstance(session_id, str) and session_id and isinstance(token, str) and token):
            return None
        if not isinstance(expires_at, str):
            return None
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if expiry.tzinfo is None or expiry <= datetime.now(UTC):
            return None
        return {"sessionId": session_id, "token": token, "expiresAt": expiry.isoformat().replace("+00:00", "Z")}

    def save(self, session_id: str, token: str, expires_at: datetime) -> None:
        if not session_id or not token or expires_at.tzinfo is None:
            raise ValueError("a session id, token, and timezone-aware expiry are required")
        if expires_at <= datetime.now(UTC):
            raise ValueError("Gateway credential is already expired")
        with _locked(self._path):
            document = _load_document(self._path)
            values = _profile_values(document, self._profile)
            current_user_session = values.get("device_session_token")
            if (
                isinstance(current_user_session, str)
                and hashlib.sha256(current_user_session.encode("utf-8")).hexdigest() != self._user_session_sha256
            ):
                raise AuthError("the device login changed while the Gateway session was being saved")
            values = {key: value for key, value in values.items() if key not in _TOOL_GATEWAY_SESSION_KEYS}
            values.update(
                {
                    "tool_gateway_hub_origin": self._hub_origin,
                    "tool_gateway_org": self._organization_id,
                    "tool_gateway_user_session_sha256": self._user_session_sha256,
                    "tool_gateway_session_id": session_id,
                    "tool_gateway_token": token,
                    "tool_gateway_expires_at": expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                }
            )
            _set_profile(document, self._profile, values)
            _write_private(_dump_document(document), self._path)

    def clear(self, session_id: str) -> None:
        with _locked(self._path):
            document = _load_document(self._path)
            values = _profile_values(document, self._profile)
            if (
                values.get("tool_gateway_hub_origin") != self._hub_origin
                or values.get("tool_gateway_org") != self._organization_id
                or values.get("tool_gateway_user_session_sha256") != self._user_session_sha256
                or values.get("tool_gateway_session_id") != session_id
            ):
                return
            values = {key: value for key, value in values.items() if key not in _TOOL_GATEWAY_SESSION_KEYS}
            _set_profile(document, self._profile, values)
            if not document:
                self._path.unlink(missing_ok=True)
            else:
                _write_private(_dump_document(document), self._path)


def _hub_origin(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Hub URL must have an HTTP origin")
    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower()
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Hub URL has an invalid port") from exc
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    authority = host if port is None or default_port else f"{host}:{port}"
    return f"{scheme}://{authority}"


_JWT_KEYS = frozenset({"device_jwt", "device_jwt_expires_at"})
_logger = logging.getLogger(__name__)


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Serialize read-merge-rewrites of one credentials file across processes (a sibling 0600 lock file)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def credentials_path() -> Path:
    configured = os.getenv("PWS_CREDENTIALS_FILE")
    return Path(configured).expanduser() if configured else Path.home() / ".config" / "pws" / "credentials.toml"


def is_header_safe_secret(value: str) -> bool:
    """Printable ASCII without whitespace: the only shape of key or token that is safe to put in an HTTP header.

    A control byte or an undecodable byte would otherwise reach an HTTP header, whose error echoes the value, or fail
    in the UTF-8 profile writer after the old session was retired.
    """

    return bool(value) and value.isascii() and value.isprintable() and not any(c.isspace() for c in value)


def require_header_safe_secret(value: str, name: str) -> None:
    """Refuse a caller-supplied key or token with a fixed message that never contains the value."""

    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    if not is_header_safe_secret(value):
        raise ValueError(f"{name} must be printable ASCII without whitespace or control characters")


def read_agent_key_file(source: Path | TextIO) -> str:
    """One agent key from a private key file (``pws edge agents keys issue --out``) or a stream such as standard input.

    ``Device`` and ``pws auth login --api-key-file`` share these checks. On POSIX a file readable by group or others is
    refused and its content is stripped; a stream has no mode to check and loses only one trailing newline. An error
    names the source and the reason, never the key.
    """

    if isinstance(source, Path):
        if os.name == "posix" and stat.S_IMODE(source.stat().st_mode) & 0o077:
            raise PermissionError(f"{source} is readable by other users; restrict it to 0600")
        name, key = str(source), source.read_text(encoding="utf-8").strip()
    else:
        name, key = "standard input", source.read().removesuffix("\n")
    if not is_header_safe_secret(key):
        raise ValueError(f"{name} is not a DEVICE key file (write one with `pws edge agents keys issue --out`)")
    return key


def normalize_hub_url(url: str) -> str:
    return url.strip().rstrip("/")


ALLOW_INSECURE_HUB_ENV = "PWS_ALLOW_INSECURE_HUB"
_PRODUCTION_DOMAIN = "phyto-works.com"
_insecure_http_warned: set[str] = set()
_insecure_http_warned_lock = Lock()


def require_secure_hub(url: str) -> str:
    """Built-in credentials only travel over HTTPS, or plain HTTP to this machine.

    ``PWS_ALLOW_INSECURE_HUB=1`` lets development Hubs and storage endpoints use remote plain HTTP, with a warning
    once per host. It never applies to a production host.
    """

    parts = urlsplit(url)
    if _is_secure_origin(parts.scheme, parts.hostname):
        return url
    if _allow_insecure_http(
        url,
        resource="send credentials to a production Hub",
        warning_resource="Hub credentials",
        error_type=AuthError,
    ):
        return url
    raise AuthError(
        "refusing to send credentials to a remote plaintext Hub: use https (http only for localhost, "
        f"or set {ALLOW_INSECURE_HUB_ENV}=1 / --allow-insecure-hub for a development Hub)"
    )


def _wire_host(url: str) -> str:
    """The host the HTTP client will connect to: IDNA-normalized, so `。`-style dots cannot hide a production host."""

    try:
        return httpx.URL(url).raw_host.decode("ascii").rstrip(".").lower()
    except (httpx.InvalidURL, UnicodeError):
        raise AuthError("refusing to send credentials to a Hub URL that cannot be parsed") from None


def _is_production_host(host: str) -> bool:
    return host == _PRODUCTION_DOMAIN or host.endswith("." + _PRODUCTION_DOMAIN)


def _allow_insecure_http(
    url: str,
    *,
    resource: str,
    warning_resource: str,
    error_type: type[AuthError] | type[ValidationError],
) -> bool:
    """Apply the shared opt-in, production refusal, and once-per-host warning rule for remote HTTP URLs."""

    parts = urlsplit(url)
    if parts.scheme != "http" or os.getenv(ALLOW_INSECURE_HUB_ENV) != "1":
        return False
    try:
        host = _wire_host(url)
    except AuthError:
        if error_type is AuthError:
            raise
        raise ValidationError("storage URL has an invalid authority") from None
    if _is_production_host(host):
        raise error_type(f"refusing to {resource} over http, even with {ALLOW_INSECURE_HUB_ENV}=1: use https")
    _warn_insecure_http_host(host, warning_resource)
    return True


def _warn_insecure_http_host(host: str, resource: str) -> None:
    """Warn once per wire host when the explicit development switch permits plaintext HTTP."""

    with _insecure_http_warned_lock:
        if host in _insecure_http_warned:
            return
        _insecure_http_warned.add(host)
    _logger.warning(
        "using %s at %s over plain http because %s=1; use this only for development",
        resource,
        host,
        ALLOW_INSECURE_HUB_ENV,
    )


def _is_secure_origin(scheme: str, hostname: str | None) -> bool:
    """HTTPS is secure everywhere; HTTP is secure only for a verified loopback host."""

    return scheme == "https" or (scheme == "http" and _is_loopback(hostname))


def device_hub(file_values: dict[str, Any], requested: str | None) -> str:
    """The stored Hub of a device session; a different requested Hub is refused, never followed."""

    stored = file_values.get("base_url")
    if not isinstance(stored, str) or not stored:
        raise AuthError("this device session has no recorded Hub; run `pws auth login` again")
    if requested and normalize_hub_url(requested) != normalize_hub_url(stored):
        raise AuthError(
            f"this device session belongs to {normalize_hub_url(stored)}, but PWS_BASE_URL/--base-url is "
            f"{normalize_hub_url(requested)}; unset it, or run `pws auth login` against that Hub"
        )
    return require_secure_hub(normalize_hub_url(stored))


def profile_hub(file_values: dict[str, Any], requested: str | None, *, profile: str, path: Path) -> str:
    """Keep a stored profile API key on its recorded Hub; legacy keys need a requested Hub."""

    stored_value = file_values.get("base_url")
    stored = normalize_hub_url(stored_value) if isinstance(stored_value, str) and stored_value else None
    requested_hub = normalize_hub_url(requested) if requested else None

    if stored and requested_hub and stored != requested_hub:
        raise AuthError(
            f"profile {profile!r} in {path} holds an agent key that belongs to {stored}, but "
            f"the requested Hub is {requested_hub}; to use that Hub, run `pws auth login --api-key-file <key file> "
            f"--base-url {requested_hub}` (add `--profile <name>` for a non-default profile), or use the Hub "
            "recorded by this profile"
        )
    if stored:
        return stored
    if requested_hub:
        return requested_hub
    raise AuthError(
        f"profile {profile!r} in {path} holds an agent key with no recorded Hub; store it again with "
        "`pws auth login --api-key-file <key file> --base-url <hub API root>` (add `--profile <name>` for a "
        "non-default profile), or set `PWS_BASE_URL`"
    )


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _select_credential(
    api_key: str | None, session_token: str | None, file_values: dict[str, Any]
) -> tuple[CredentialKind | Literal["retired_session"] | None, str, CredentialSource | None]:
    if session_token:
        return "session", session_token, "explicit"
    if api_key:
        return "api_key", api_key, "explicit"
    if env_session := os.getenv("PWS_SESSION_TOKEN"):
        return "session", env_session, "environment"
    if env_key := os.getenv("PWS_API_KEY"):
        return "api_key", env_key, "environment"
    # ``session_token`` in the file is the retired --password-login session:
    # reported, never used.  Env/explicit ``session_token`` above stays.
    for key, kind in (
        ("device_session_token", "device_session"),
        ("session_token", "retired_session"),
        ("api_key", "api_key"),
    ):
        value = file_values.get(key)
        if isinstance(value, str) and value:
            return kind, value, "profile"  # type: ignore[return-value]
    return None, "", None


def _read_profile(path: Path, profile: str) -> dict[str, Any]:
    return _profile_values(_load_document(path), profile)


def _load_document(path: Path) -> dict[str, Any]:
    """Load the file; a hand-written flat default profile is normalized into ``[default]``."""

    if not path.is_file():
        return {}
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    flat = {key: value for key, value in document.items() if not isinstance(value, dict)}
    if flat and "default" not in document:
        document = {key: value for key, value in document.items() if isinstance(value, dict)}
        document["default"] = flat
    return document


def _profile_values(document: dict[str, Any], profile: str) -> dict[str, Any]:
    if profile == "default":
        values = document.get("default")
        if values is None:
            values = {key: value for key, value in document.items() if not isinstance(value, dict)}
    else:
        profiles = document.get("profile", {})
        values = profiles.get(profile, {}) if isinstance(profiles, dict) else {}
    return dict(values) if isinstance(values, dict) else {}


def _set_profile(document: dict[str, Any], profile: str, values: dict[str, Any] | None) -> None:
    """Replace (or with ``None`` remove) one profile in a loaded document, in place."""

    if profile == "default":
        for key in [key for key, value in document.items() if not isinstance(value, dict)]:
            del document[key]
        document.pop("default", None)
        if values:
            document["default"] = values
        return
    profiles = document.get("profile")
    if not isinstance(profiles, dict):
        profiles = {}
    profiles.pop(profile, None)
    if values:
        profiles[profile] = values
    if profiles:
        document["profile"] = profiles
    else:
        document.pop("profile", None)


def _write_private(content: str, path: Path) -> None:
    """Write via an exclusive 0600 temp file in the same directory, then replace atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    stream = open(temporary, "x", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600))
    try:
        with stream:
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def _dump_document(document: dict[str, Any]) -> str:
    """Serialize the flat credential sections, and refuse any output that does not read back identically."""

    content = _render_document(document)
    try:
        round_trip = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        round_trip = None
    if round_trip != document:
        raise ValueError("refusing to write a credentials file that would not read back unchanged")
    return content


def _render_document(document: dict[str, Any]) -> str:
    lines: list[str] = []
    for name, values in document.items():
        if name == "profile" and isinstance(values, dict):
            for profile_name, profile_values in values.items():
                lines.append(f"[profile.{_toml_string(profile_name)}]")
                lines.extend(_dump_values(profile_values))
                lines.append("")
        elif isinstance(values, dict):
            lines.append(f"[{_toml_key(name)}]")
            lines.extend(_dump_values(values))
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _dump_values(values: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, str):
            rendered = _toml_string(value)
        elif isinstance(value, (int, float)):
            rendered = repr(value)
        else:
            raise ValueError(f"cannot write credential key {key!r}: only strings, numbers and booleans are kept")
        lines.append(f"{_toml_key(key)} = {rendered}")
    return lines


_BARE_KEY_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def _toml_string(value: str) -> str:
    """A TOML basic string: escape only quote, backslash and control characters; keep other text as UTF-8."""

    escaped: list[str] = []
    for char in value:
        if char == '"':
            escaped.append('\\"')
        elif char == "\\":
            escaped.append("\\\\")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            escaped.append(f"\\u{ord(char):04x}")
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


def _toml_key(key: str) -> str:
    return key if key and all(char in _BARE_KEY_CHARS for char in key) else _toml_string(key)
