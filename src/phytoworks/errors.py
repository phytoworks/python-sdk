"""Public error hierarchy for the operator SDK."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import ActionExecutionStatus


class PWSError(Exception):
    """Base error with optional HTTP context."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        details: Mapping[str, Any] | None = None,
        code: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.details = dict(details or {})
        self.code = code
        self.execution_id = execution_id


class AuthError(PWSError):
    """Authentication or credential exchange failure."""


class CredentialMissingError(AuthError):
    """No usable SDK credential was configured."""


class NotFoundError(PWSError):
    """The requested resource does not exist in the current scope."""


class PermissionError(PWSError):
    """The current credential cannot access the requested resource."""


class OrganizationScopeError(PermissionError):
    """The Hub rejected the request because the organization scope is missing or wrong."""

    @classmethod
    def from_response(cls, original: PWSError, *, org: str | None) -> OrganizationScopeError:
        if org is None:
            hint = "no organization scope is set; check the scope: --org/org=, else PWS_ORG, else the profile's org"
        else:
            hint = (
                f"organization scope {org!r} does not grant access to this resource; "
                "check the scope: --org/org=, else PWS_ORG, else the profile's org "
                "(an organization this account belongs to), and the identifier"
            )
        message = f"{original} ({hint})"
        return cls(
            message,
            status_code=original.status_code,
            request_id=original.request_id,
            details=original.details,
            code=original.code,
        )


class RateLimitError(PWSError):
    """The server kept rejecting a request after bounded retries."""

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class TransportError(PWSError):
    """Network, timeout, or unexpected HTTP failure."""


class ValidationError(PWSError):
    """The Hub rejected the request's input (HTTP 400), or a response did not satisfy the SDK wire model."""


class ActionFailed(PWSError):  # noqa: N818
    """An action reached a terminal failed state."""

    def __init__(self, message: str, *, status: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.status = status


class ActionTimeout(PWSError):  # noqa: N818
    """The Hub or SDK stopped waiting without a device result."""

    def __init__(
        self,
        message: str,
        *,
        status: str | None = None,
        results: Mapping[str, ActionExecutionStatus] | None = None,
        pending: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.status = status
        self.results = dict(results or {})
        self.pending = pending


class AmbiguousAction(PWSError):  # noqa: N818
    """An action name matched more than one discovered device."""


class UnknownAction(PWSError):  # noqa: N818
    """An action is absent from the current structure or has no named mapping."""


class ActionPreviewUnavailable(NotFoundError):  # noqa: N818
    """The connected Hub has no dedicated, fail-closed action preview route."""


class SessionFenced(PWSError):  # noqa: N818
    """A device capture session was settled by the receive loop; the handler that owned it may not write to it."""


class MqttUnavailable(PWSError):  # noqa: N818
    """The device has no usable broker endpoint or credential: no ``mqtts://`` URL, or the Hub issued no slot."""


class CredentialRevoked(AuthError):  # noqa: N818
    """The broker refused the device and re-discovery with its key was refused too (HTTP 401): the key is gone."""


class SessionTakenOver(PWSError):  # noqa: N818
    """Another connection with this device's client id took the broker session twice in a row; one process per key."""


class SubscribeDenied(PWSError):  # noqa: N818
    """The broker refused one of this device's own topics: a subscribe (SUBACK) or a results publish (PUBACK)."""


class ActionCancelled(PWSError):  # noqa: N818
    """Raised by :meth:`phytoworks.device.ActionContext.check` once the run was cancelled or ran out of time."""


class DeviceStopped(PWSError):  # noqa: N818
    """The device's executor is closing or retired: a :class:`~phytoworks.device.Device` that served ``listen()`` is
    single-use, so every later call is refused without a request (make a new ``Device`` in a new process)."""


class NotServing(PWSError):  # noqa: N818
    """:meth:`~phytoworks.device.Device.submit` came before ``listen()`` started its worker."""


class DeviceBusy(PWSError):  # noqa: N818
    """:meth:`~phytoworks.device.Device.submit` found the executor full (``OUTBOX_LIMIT`` items, Hub commands
    included); whether to skip this run is the caller's schedule."""


class ManualModeActive(PWSError):  # noqa: N818
    """:meth:`~phytoworks.device.Device.submit` was refused because the Hub reports this device in manual mode."""


def error_from_http(
    status_code: int,
    payload: object,
    *,
    retry_after: float | None = None,
    request_id: str | None = None,
) -> PWSError:
    """Map the stable HTTP classes into the public SDK hierarchy.

    The Hub error envelope is ``{"success": false, "error": {"code", "message",
    "category", "details", ...}, "meta": {"requestId", ...}}``; a validation 400
    carries ``details.summary`` (one ``path: message`` line per issue).
    """

    message = "Hub request failed"
    code: str | None = None
    details: Mapping[str, Any] | None = None
    validation = False
    if isinstance(payload, Mapping):
        details = payload
        error = payload.get("error")
        if isinstance(error, Mapping):
            code = _text(error.get("code"))
            message = _text(error.get("message")) or message
            error_details = error.get("details")
            validation = error.get("category") == "validation" or (
                isinstance(error_details, Mapping) and error_details.get("type") == "validation"
            )
            summary = error_details.get("summary") if isinstance(error_details, Mapping) else None
            if isinstance(summary, list) and (lines := [line for line in summary if isinstance(line, str)]):
                message = f"{message}: {'; '.join(lines)}"
        else:
            message = _text(payload.get("message")) or _text(error) or message
        meta = payload.get("meta")
        if request_id is None and isinstance(meta, Mapping):
            request_id = _text(meta.get("requestId"))
    elif isinstance(payload, str) and payload:
        message = payload

    context: dict[str, Any] = {"status_code": status_code, "request_id": request_id, "details": details, "code": code}
    if status_code in (401, 403):
        error_type = AuthError if status_code == 401 else PermissionError
        return error_type(message, **context)
    if status_code == 404:
        return NotFoundError(message, **context)
    if status_code == 429:
        return RateLimitError(message, retry_after=retry_after, **context)
    if status_code == 400 or validation:
        return ValidationError(message, **context)
    return TransportError(message, **context)


def _status_only(error: PWSError, what: str) -> PWSError:
    """``error``'s class and HTTP status only: a body, code, request id or cause may echo a secret.

    Raise the result outside the ``except`` block so the original is not kept as ``__context__`` either.
    """

    status = error.status_code
    message = f"{what} failed" + (f" (HTTP {status})" if status is not None else "")
    if isinstance(error, RateLimitError):
        return RateLimitError(message, status_code=status, retry_after=error.retry_after)
    return type(error)(message, status_code=status)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
