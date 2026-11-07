"""External Phenos Tool Gateway client used by the generated ``pws phenos`` commands."""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, Protocol, TypeGuard, cast
from urllib.parse import quote

import httpx
import typer
from jsonschema import Draft202012Validator  # type: ignore[import-untyped,unused-ignore]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped,unused-ignore]
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from rich.markup import escape
from typer.core import TyperGroup

from ._transport import TimeBudgetError, Transport
from .auth import Credential, SessionCredential
from .config import Config, ToolGatewaySessionStore, credentials_path, require_secure_hub
from .device_auth import DeviceSessionCredential
from .errors import (
    AuthError,
    NotFoundError,
    PermissionError,
    PWSError,
    RateLimitError,
    TransportError,
    ValidationError,
)
from .facade import _credential_from_config
from .models.generated import ArtifactDownload

# The only local text the CLI prints in place of a code's fixed message: it is written here, never taken from an
# exception, so it cannot carry a URL, a path or a credential.
SESSION_ALREADY_ACTIVE = (
    "A Phenos session is already active; end the active session with `pws phenos session end` before starting another."
)
# Printed by `execution wait` only when the execution's own status reads cancelled; the bare `cancelled` code does not
# prove that, so its fixed message says the outcome is unknown.
EXECUTION_CANCELLED = "The execution was cancelled; start it again if you still need the result."
SESSION_END_UNKNOWN = (
    "The session end may have reached the server but its outcome is unknown; check it with `pws phenos session show`."
)
# A login without a stored session is not a login problem: `unauthenticated` would send the user to `pws auth login`.
NO_ACTIVE_SESSION = "No Phenos session is active in this profile; start one with `pws phenos session start`."
# `session start` answers a bare `not_found` for a photo uploaded to My files as it does for an unknown id; an external
# session takes only a photo captured at a Spot.
SESSION_IMAGE_NOT_FOUND = (
    "The photo or annotation was not found for an external session: it takes only a photo captured at a Spot, not "
    "one uploaded to My files; check the ids."
)
_LOCAL_MESSAGES = frozenset({SESSION_ALREADY_ACTIVE, SESSION_END_UNKNOWN, NO_ACTIVE_SESSION, SESSION_IMAGE_NOT_FOUND})
# What a call waiting for a person tells the agent: the document's `next` field and, in every output mode, one stderr line.
APPROVAL_PENDING_GUIDANCE = (
    "A person approves this request in Phenos (External agent requests). After approval, run the same command again "
    "with the same arguments, or wait with: pws approvals wait {approval_id}"
)
# Terminal-only lines of `pws approvals wait`, on stderr so stdout stays the document.
APPROVAL_WAIT_PROGRESS = "Waiting for a person to approve or reject this in Phenos (External agent requests)..."
APPROVAL_WAIT_TIMEOUT = (
    "The last check before the time ran out saw no decision; check it with: pws approvals show {approval_id}, "
    "or wait again with: pws approvals wait {approval_id}"
)


class PhenosGateway:
    """Thin transport for Gateway sessions; admission and retry decisions stay on Hub."""

    def __init__(
        self,
        transport: Transport,
        *,
        organization_id: str | None,
        user_credential: Credential,
        session_store: ToolGatewaySessionStore,
    ) -> None:
        self._transport = transport
        self._organization_id = organization_id
        self._user_credential = user_credential
        self._session_store = session_store
        # True once a POST may have reached the Hub; stays False when nothing was sent (no session, bad arguments,
        # a failure to connect), which is when a resend needs no idempotency care.
        self.request_sent = False

    def __repr__(self) -> str:
        return "PhenosGateway()"

    def close(self) -> None:
        self._transport.close()

    def start_session(self, request: Mapping[str, object]) -> dict[str, object]:
        self._require_start_session()
        request_schema = _schema("sessionRequest")
        body = _validated_json(request, request_schema, code="invalid_arguments")
        headers = self._user_headers()
        self.request_sent = True
        try:
            payload = self._transport.request("POST", _routes()["createSession"], headers=headers, json_body=body)
        except PWSError as exc:
            self.request_sent = not _is_connect_failure(exc)
            raise _safe_gateway_error(exc, post=True) from None
        return self._store_created_session(payload)

    def _require_start_session(self) -> None:
        if not isinstance(self._user_credential, (DeviceSessionCredential, SessionCredential)):
            raise AuthError(
                "pws phenos session start requires `pws auth login` and a live user session",
                code="unauthenticated",
            )
        if not self._organization_id:
            raise AuthError("set --org or PWS_ORG before starting a Phenos session", code="forbidden")
        if self._session_store.load() is not None:
            raise ValidationError(SESSION_ALREADY_ACTIVE, code="invalid_arguments")

    def _user_headers(self) -> dict[str, str]:
        if not isinstance(self._user_credential, (DeviceSessionCredential, SessionCredential)):
            raise AuthError("a live user session is required to start a Phenos session", code="unauthenticated")
        try:
            self._user_credential.refresh(self._transport)
        except TimeBudgetError:
            raise
        except PWSError as exc:
            raise _safe_auth_error(exc) from None
        headers = dict(self._user_credential.headers())
        if not headers.get("Authorization", "").startswith("Bearer "):
            raise AuthError("a live user session is required to start a Phenos session", code="unauthenticated")
        headers["X-Organization-Id"] = cast(str, self._organization_id)
        return headers

    def _store_created_session(self, payload: object) -> dict[str, object]:
        response = _validated_json(payload, _schema("sessionResponse"), code="internal")
        session = cast(dict[str, object], response["session"])
        credential = cast(dict[str, object], response["credential"])
        if session.get("organizationId") != self._organization_id:
            raise ValidationError("Hub returned a session for another organization", code="internal")
        expires_at = _parse_expiry(cast(str, credential["expiresAt"]))
        session_expires_at = _parse_expiry(cast(str, session["expiresAt"]))
        if expires_at > session_expires_at:
            raise ValidationError("Gateway credential outlives its session", code="internal")
        try:
            self._session_store.save(cast(str, session["sessionId"]), cast(str, credential["token"]), expires_at)
        except OSError:
            raise TransportError("could not save the external session credential") from None
        except ValueError:
            raise ValidationError("could not save the external session credential", code="internal") from None
        return session

    def call(
        self,
        call: Mapping[str, object],
        *,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        ask_again: bool = False,
    ) -> dict[str, object]:
        """Send one call; ``timeout`` caps this request's transport timeout (a wait passes the time it has left).

        ``ask_again`` sends the ask-again header, which Hub reads on a change or delete only: it asks a person again
        when the same request ended without a rejection.
        """

        if not idempotency_key:
            raise ValidationError("Idempotency-Key is required", code="invalid_arguments")
        if len(idempotency_key) > 128:
            raise ValidationError("Idempotency-Key exceeds its 128-character limit", code="invalid_arguments")
        # A header value goes out as ASCII; anything else would fail inside the transport after nothing was sent.
        if not all("!" <= character <= "~" for character in idempotency_key):
            raise ValidationError("Idempotency-Key must be visible ASCII", code="invalid_arguments")
        operation_id = call.get("operation")
        spec = _operation(str(operation_id))
        if call.get("version") != spec.get("version"):
            raise ValidationError("the Tool Gateway operation version does not match", code="tool_contract_mismatch")
        args_schema = spec.get("argsSchema")
        body = _validated_json(call, _call_schema(cast(dict[str, object], args_schema)), code="invalid_arguments")
        active = self.active_session(session_id)
        headers = self._call_headers(active, idempotency_key, ask_again=ask_again)
        path = _routes()["sessionCall"].replace(":sessionId", quote(active["sessionId"], safe=""))
        self.request_sent = True
        configured = self._transport.timeout
        if timeout is not None and isinstance(configured, (int, float)):
            self._transport.timeout = min(configured, timeout)
        try:
            payload = self._transport.request("POST", path, headers=headers, json_body=body)
        except PWSError as exc:
            self.request_sent = not _is_connect_failure(exc)
            raise _safe_gateway_error(exc, post=True) from None
        finally:
            self._transport.timeout = configured
        execution = spec.get("external") == "execution" or operation_id in {
            "phenos_execution_status",
            "phenos_execution_cancel",
        }
        try:
            _check_result_size(payload, str(operation_id), execution=execution)
            if execution:
                return _validated_execution(payload)
            return _validated_json(payload, cast(dict[str, object], spec["resultSchema"]), code="internal")
        except ValidationError as exc:
            # The call was sent and answered, but the answer does not say what happened. Only a call Hub repeats
            # unchanged is a plain error then; any other call may have started work, so its outcome is unknown.
            if exc.code == "internal" and spec.get("gatewayRetry") != "repeat":
                raise ValidationError(_message_for("tool_outcome_unknown"), code="tool_outcome_unknown") from None
            raise

    def _call_headers(self, active: Mapping[str, str], idempotency_key: str, *, ask_again: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {active['token']}",
            "X-Organization-Id": self._organization_id or "",
            "Idempotency-Key": idempotency_key,
        }
        if ask_again:
            name, value = _ask_again_header()
            headers[name] = value
        return headers

    def approval(self, approval_id: str, *, time_left: Callable[[], float] | None = None) -> dict[str, object]:
        """One approval of this login's connection, in whatever state it is.

        ``time_left`` caps each network wait of the read (JWT exchange and attempts) at the time left and keeps retries
        and back-off inside it; an attempt or pause that cannot start inside it raises ``TimeBudgetError``. It does
        not cut off an answer already arriving, so a slow read can finish a little after the time is up.
        """

        path = _routes()["approval"].replace(":approvalId", quote(approval_id, safe=""))
        self._transport.time_left = time_left
        try:
            payload = self._login_get(path)
        except PWSError as exc:
            if isinstance(exc, TimeBudgetError) or (time_left is not None and time_left() <= 0):
                raise TimeBudgetError("the time to wait ended before Hub answered") from None
            raise
        finally:
            self._transport.time_left = None
        return _validated_json(payload, _schema("externalApproval"), code="internal")

    def approvals(self) -> dict[str, object]:
        """The open approvals of this login's connection."""

        return _validated_json(
            self._login_get(_routes()["approvals"]), _schema("externalApprovalList"), code="internal"
        )

    def _login_get(self, path: str) -> object:
        """GET with the device login's own JWT, refreshed per read: the connection is that login, and an external
        session's credential (15 to 60 minutes) could not outlast a person's 8 hours.

        A 401 drops the JWT and, for a device login that can mint another, reads once more with a fresh one, as the
        facade's reads do; a second 401 stands.
        """

        for attempt in range(2):
            headers = self._user_headers()
            try:
                return self._transport.request("GET", path, headers=headers)
            except TimeBudgetError:
                raise
            except PWSError as exc:
                if exc.status_code == 401 and isinstance(self._user_credential, DeviceSessionCredential):
                    self._user_credential.invalidate()
                    if attempt == 0:
                        continue
                raise _safe_gateway_error(exc) from None
        raise AssertionError("unreachable")

    def download_data_file(self, artifact_uri: str, target: Path, *, sha256: str, max_bytes: int) -> None:
        """Write the data file an external session's answer names (its artifact) to ``target``.

        The artifact is opened with the person's own session, the way any of their results is, and read once from its
        short-lived link into a sibling of ``target``. Only bytes whose SHA-256 is the answer's replace ``target``, in
        one rename; on any failure the sibling is removed and whatever was at ``target`` stays.
        """

        prefix = "phenos-artifact://"
        if not artifact_uri.startswith(prefix):
            raise ValidationError("Hub answered a data file that is not an artifact", code="internal")
        path = f"/artifacts/{quote(artifact_uri[len(prefix) :], safe='')}/open"
        staged = target.with_name(f".{target.name}.{secrets.token_hex(8)}.verify")
        try:
            try:
                opened = ArtifactDownload.model_validate(
                    self._transport.request("POST", path, headers=self._user_headers(), json_body={})
                )
                self._transport.download(
                    opened.download_url, staged, max_bytes=max_bytes, expected_content_type="application/json"
                )
            except PWSError as exc:
                raise _safe_gateway_error(exc, post=True) from None
            if f"sha256:{hashlib.sha256(staged.read_bytes()).hexdigest()}" != sha256:
                raise ValidationError("the downloaded data file is not the one Hub answered", code="integrity_failed")
            os.replace(staged, target)
        finally:
            staged.unlink(missing_ok=True)

    def _lifecycle_session(self, session_id: str | None) -> dict[str, str]:
        """The session `show` and `end` act on; with none stored they say so rather than send the user to log in."""

        if self._session_store.load() is None:
            raise NotFoundError(NO_ACTIVE_SESSION, code="not_found")
        return self.active_session(session_id)

    def get_session(self, *, session_id: str | None = None) -> dict[str, object]:
        active = self._lifecycle_session(session_id)
        path = _routes()["session"].replace(":sessionId", quote(active["sessionId"], safe=""))
        try:
            payload = self._transport.request("GET", path, headers=self._gateway_headers(active))
        except PWSError as exc:
            raise _safe_gateway_error(exc) from None
        return _validated_json(payload, _schema("session"), code="internal")

    def end_session(self, *, session_id: str | None = None) -> dict[str, object]:
        """Revoke the session. The transport retries a DELETE like a GET, which is safe: revoking twice is a no-op.

        Unlike a read, the DELETE revokes the session and stops its work, so a reply lost after it was sent (or an
        unreadable one) leaves the outcome unknown, and the stored session is kept for `session show` to check.
        """

        active = self._lifecycle_session(session_id)
        path = _routes()["session"].replace(":sessionId", quote(active["sessionId"], safe=""))
        try:
            payload = self._transport.request("DELETE", path, headers=self._gateway_headers(active))
            result = _validated_json(payload, _schema("session"), code="internal")
        except PWSError as exc:
            lost = isinstance(exc, TransportError) and not exc.code and not _is_connect_failure(exc)
            if lost or (isinstance(exc, ValidationError) and exc.code == "internal"):
                raise TransportError(SESSION_END_UNKNOWN, code="tool_outcome_unknown") from None
            raise _safe_gateway_error(exc) from None
        self._session_store.clear(active["sessionId"])
        return result

    def active_session(self, requested_id: str | None = None) -> dict[str, str]:
        """The stored session for this profile, or the selected one; never printed, since it holds the token."""

        active = self._session_store.load()
        if active is None:
            raise AuthError("no active Phenos session; run `pws phenos session start`", code="unauthenticated")
        if requested_id is not None and requested_id != active["sessionId"]:
            raise AuthError("the selected Phenos session is not stored for this profile", code="unauthenticated")
        return active

    def _gateway_headers(self, active: Mapping[str, str]) -> dict[str, str]:
        if not self._organization_id:
            raise AuthError("set --org or PWS_ORG before using a Phenos session", code="forbidden")
        return {
            "Authorization": f"Bearer {active['token']}",
            "X-Organization-Id": self._organization_id,
        }


def gateway_from_cli_context(context: object) -> PhenosGateway:
    """Resolve the existing profile login without turning an agent key into a Gateway credential."""

    config = Config.resolve(
        base_url=getattr(context, "base_url", None),
        org=getattr(context, "org", None),
        profile=cast(str, getattr(context, "profile", "default")),
    )
    credential = _credential_from_config(config)
    session_secret = _session_secret(credential)
    if credential is None or session_secret is None:
        raise AuthError("pws phenos requires `pws auth login` with a live user session", code="unauthenticated")
    if not config.org:
        raise AuthError("set --org or PWS_ORG before using Phenos", code="forbidden")
    path = config.credentials_file or credentials_path()
    store = ToolGatewaySessionStore(path, config.profile, config.base_url, config.org or "", session_secret)
    require_secure_hub(config.base_url)
    return PhenosGateway(
        Transport(config.base_url, timeout=config.timeout),
        organization_id=config.org,
        user_credential=credential,
        session_store=store,
    )


def _output_mode(context: object, json_output: bool) -> str:
    """The context's mode; a per-command ``--json`` forces JSON whatever the root mode says."""

    from .cli import OutputMode

    mode = getattr(context, "mode", OutputMode.JSON)
    return OutputMode.JSON.value if json_output else str(mode)


def _json_mode(mode: str) -> bool:
    return mode in ("json", "jsonl")


@dataclass(frozen=True, slots=True)
class _Failure:
    """One failed command as it is reported: a fixed message, never the Hub's text."""

    code: str
    message: str
    retryable: bool
    exit_code: int
    request_id: str | None = None
    execution_id: str | None = None
    idempotency_key: str | None = None
    usage: str | None = None
    hint: bool = False

    def document(self) -> dict[str, object]:
        detail: dict[str, object] = {"code": self.code, "message": self.message, "retryable": self.retryable}
        for key, value in (
            ("requestId", self.request_id),
            ("executionId", self.execution_id),
            ("idempotencyKey", self.idempotency_key),
            ("usage", self.usage),
        ):
            if value:
                detail[key] = value
        return {"error": detail}


def _failure_from(
    error: PWSError,
    *,
    usage: str | None = None,
    execution_id: str | None = None,
    idempotency_key: str | None = None,
    user_key: bool = False,
    sent: bool = False,
) -> _Failure:
    from .phenos_commands_generated import PWS_ERROR_RETRYABLE, PWS_EXIT_CODES, TOOL_GATEWAY_APPROVAL_ERRORS

    code = _normalized_code(error)
    return _Failure(
        code=code,
        message=str(error) if str(error) in _LOCAL_MESSAGES else _message_for(code),
        retryable=PWS_ERROR_RETRYABLE[code],
        exit_code=exit_number(PWS_EXIT_CODES[code]),
        request_id=error.request_id,
        # An id the arguments check refused is the caller's raw input, never printed back.
        execution_id=None if code == "invalid_arguments" else execution_id or error.execution_id,
        idempotency_key=idempotency_key if sent else None,
        usage=usage if code == "invalid_arguments" else None,
        # A refusal Hub answered (bad arguments, auth, not found, permission, an approval refusal) ran nothing, so it
        # needs no resend care.
        hint=sent
        and idempotency_key is not None
        and not user_key
        and PWS_EXIT_CODES[code] not in {"usage", "auth", "not_found", "permission"}
        and code not in TOOL_GATEWAY_APPROVAL_ERRORS,
    )


def _report_failure(context: object, failure: _Failure, *, json_output: bool) -> NoReturn:
    """Write the failure to stderr only, then exit with its category's number."""

    from .cli import _console

    if _json_mode(_output_mode(context, json_output)):
        typer.echo(_render_json(failure.document()), err=True)
    else:
        details = [
            f"{label}={value}"
            for label, value in (
                ("requestId", failure.request_id),
                ("executionId", failure.execution_id),
                ("idempotencyKey", failure.idempotency_key),
            )
            if value
        ]
        line = f"[{failure.code}] {failure.message}" + "".join(f" ({detail})" for detail in details)
        console = _console(stderr=True)
        console.print(f"[red]error:[/red] {escape(line)}", highlight=False, soft_wrap=True)
        if failure.usage:
            console.print(f"usage: {escape(failure.usage)}", highlight=False, soft_wrap=True)
        if failure.hint:
            console.print(
                "hint: the call may have been sent; do not resend it blindly. Check `pws phenos execution status` "
                f"first and resend only with --idempotency-key {escape(cast(str, failure.idempotency_key))}",
                highlight=False,
                soft_wrap=True,
            )
    raise typer.Exit(code=failure.exit_code)


def run_generated_command(
    context: object,
    operation_id: str,
    args: Mapping[str, object],
    *,
    json_output: bool,
    session_id: str | None,
    idempotency_key: str | None,
    ask_again: bool = False,
    out: str | None = None,
) -> None:
    """Run one generated registry operation: the result alone on stdout, a failure alone on stderr.

    A command whose answer names a data file in an external session (an artifact) downloads it to ``out`` (default
    ``annotations/<image>.json`` in the working folder) and answers that local path in ``file``.
    """

    key = idempotency_key or str(uuid.uuid4())
    gateway: PhenosGateway | None = None
    try:
        gateway = gateway_from_cli_context(context)
        result = gateway.call(
            {"operation": operation_id, "version": _operation(operation_id)["version"], "args": dict(args)},
            session_id=session_id,
            idempotency_key=key,
            ask_again=ask_again,
        )
        if operation_id in _data_file_operations():
            result = _with_local_data_file(gateway, result, out)
    except PWSError as exc:
        execution = args.get("execution") if operation_id.startswith("phenos_execution_") else None
        failure = _failure_from(
            exc,
            usage=_usage(operation_id),
            execution_id=execution if isinstance(execution, str) else None,
            idempotency_key=key,
            user_key=idempotency_key is not None,
            sent=gateway is not None and gateway.request_sent,
        )
        _report_failure(context, failure, json_output=json_output)
    finally:
        if gateway is not None:
            gateway.close()
    approval = _approval_document(operation_id, result)
    if approval is None:
        _emit_result(context, result, json_output=json_output)
        return
    # The terminal gets the same words once, on stderr; the document carries them only where stdout is the whole answer.
    _emit_result(
        context,
        approval
        if _json_mode(_output_mode(context, json_output))
        else {k: v for k, v in approval.items() if k != "next"},
        json_output=json_output,
    )
    from .cli import _console

    _console(stderr=True).print(escape(cast(str, approval["next"])), highlight=False, soft_wrap=True)
    raise typer.Exit(code=exit_number("pending"))


def _terminal_note(context: object, line: str) -> None:
    """One guidance line on stderr in the terminal (table) mode only; JSON and ``-q`` output stay the result alone."""

    from .cli import OutputMode, _console

    if getattr(context, "mode", None) is OutputMode.TABLE:
        _console(stderr=True).print(escape(line), highlight=False, soft_wrap=True)


def _approval_document(operation_id: str, result: Mapping[str, object]) -> dict[str, object] | None:
    """The approval document of a call that waits for a person: ``{approvalId, tool, next}``, else None.

    The result already passed the operation's registered schema, so an awaiting answer carries exactly its
    ``pendingId``; a broken one never gets here (it is the call's unknown outcome). The approval shares that id.
    """

    pending = result.get("pendingId")
    if result.get("status") != "awaiting_approval" or not isinstance(pending, str):
        return None
    return {
        "approvalId": pending,
        "tool": operation_id,
        "next": APPROVAL_PENDING_GUIDANCE.format(approval_id=pending),
    }


def run_session_command(
    context: object,
    action: str,
    *,
    request: Mapping[str, object] | None = None,
    session_id: str | None = None,
    json_output: bool = False,
) -> None:
    """Run the explicit session lifecycle commands without ever serializing its token."""

    gateway: PhenosGateway | None = None
    try:
        gateway = gateway_from_cli_context(context)
        if action == "start":
            if request is None:
                raise ValidationError("session references are required", code="invalid_arguments")
            try:
                result = gateway.start_session(request)
            except PWSError as exc:
                if _normalized_code(exc) == "not_found":
                    raise NotFoundError(SESSION_IMAGE_NOT_FOUND, code="not_found") from None
                raise
        elif action == "show":
            result = gateway.get_session(session_id=session_id)
        elif action == "end":
            result = gateway.end_session(session_id=session_id)
        else:
            raise ValidationError("session action is not supported", code="invalid_arguments")
    except PWSError as exc:
        failure = _failure_from(exc, usage=SESSION_USAGE.get(action), sent=False)
        _report_failure(context, failure, json_output=json_output)
    finally:
        if gateway is not None:
            gateway.close()
    _emit_result(context, result, json_output=json_output)


SESSION_USAGE = {
    "start": "pws phenos session start --image ID[:REVISION] [--annotation ID[:REVISION]]... [--client NAME] [--ttl SECONDS]",
    "show": "pws phenos session show [--session ID]",
    "end": "pws phenos session end [--session ID]",
}

# The poll cadence of ``actions.wait`` (facade.py): 2 s, growing by 1.3x up to 5 s.
WAIT_FIRST_INTERVAL = 2.0
WAIT_INTERVAL_GROWTH = 1.3
WAIT_MAX_INTERVAL = 5.0
# A poll started with almost no time left still gets this long to answer.
WAIT_MIN_POLL_SECONDS = 0.1
# Tests replace these two so a wait never sleeps for real.
_monotonic: Callable[[], float] = time.monotonic
_sleep: Callable[[float], None] = time.sleep


def run_wait_command(
    context: object,
    execution_id: str,
    *,
    timeout: float | None,
    json_output: bool,
    session_id: str | None,
) -> None:
    """Poll ``phenos_execution_status`` until the execution ends or the deadline passes.

    The deadline is ``timeout`` capped by the stored session's expiry (Hub refuses every poll after it), and it is
    checked before each poll after the first. Each poll's network waits are capped at the time left; a poll already
    under way is not cut off, so the wait can end after the deadline.
    """

    if timeout is not None and not math.isfinite(timeout):
        usage_error(context, "--timeout must be a finite number of seconds", usage=WAIT_USAGE, json_output=json_output)
    gateway: PhenosGateway | None = None
    try:
        gateway = gateway_from_cli_context(context)
        execution, outcome = _poll_until_done(gateway, execution_id, timeout=timeout, session_id=session_id)
    except PWSError as exc:
        outcome = _failure_from(exc, usage=WAIT_USAGE, execution_id=execution_id)
    finally:
        if gateway is not None:
            gateway.close()
    if outcome is not None:
        _report_failure(context, outcome, json_output=json_output)
    _emit_result(context, execution, json_output=json_output)


def _poll_until_done(
    gateway: PhenosGateway, execution_id: str, *, timeout: float | None, session_id: str | None
) -> tuple[dict[str, object] | None, _Failure | None]:
    """The succeeded execution, or the failure to report: the execution's own end, or the deadline."""

    from .cli import EXIT_ACTION_TIMEOUT

    active = gateway.active_session(session_id)
    session_left = _remaining_seconds(active)
    budget = session_left if timeout is None else min(timeout, session_left)
    deadline = _monotonic() + budget

    def left() -> float:
        return min(deadline - _monotonic(), _remaining_seconds(active))

    timed_out = _Failure(
        code="timeout",
        message=(
            f"Execution {execution_id} did not finish within {budget:g} seconds; it may still be "
            f"running. Check with `pws phenos execution status {execution_id}`."
        ),
        retryable=True,
        exit_code=EXIT_ACTION_TIMEOUT,
        execution_id=execution_id,
    )
    interval = WAIT_FIRST_INTERVAL
    while True:
        try:
            polled = gateway.call(
                {
                    "operation": "phenos_execution_status",
                    "version": _operation("phenos_execution_status")["version"],
                    "args": {"execution": execution_id},
                },
                session_id=session_id,
                idempotency_key=str(uuid.uuid4()),
                timeout=max(left(), WAIT_MIN_POLL_SECONDS),
            )
        except PWSError:
            if left() <= 0:
                return None, timed_out
            raise
        if polled.get("status") == "succeeded":
            return polled, None
        if polled.get("status") in ("failed", "cancelled"):
            return None, _ended_failure(polled, execution_id)
        remaining = left()
        if remaining > 0:
            _sleep(min(interval, remaining))
            interval = min(interval * WAIT_INTERVAL_GROWTH, WAIT_MAX_INTERVAL)
            remaining = left()
        if remaining <= 0:
            return None, timed_out


def _ended_failure(execution: Mapping[str, object], execution_id: str) -> _Failure:
    """Exit 6 for an execution whose own status reads failed or cancelled."""

    from .cli import EXIT_ACTION_FAILED

    failure = execution.get("failure")
    detail = cast(dict[str, object], failure) if isinstance(failure, dict) else {}
    cancelled = execution.get("status") == "cancelled"
    code = "cancelled" if cancelled else str(detail.get("code", "internal"))
    return _Failure(
        code=code,
        message=EXECUTION_CANCELLED if cancelled else _message_for(code),
        retryable=bool(detail.get("retryable", False)),
        exit_code=EXIT_ACTION_FAILED,
        execution_id=execution_id,
    )


WAIT_USAGE = "pws phenos execution wait ID [--timeout SECONDS] [--session ID]"


def _remaining_seconds(active: Mapping[str, str]) -> float:
    """Seconds left on the stored external session; the Hub ends the execution's work with it."""

    return _seconds_until(active["expiresAt"])


def _seconds_until(expires_at: str) -> float:
    moment = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return max(0.0, (moment - datetime.now(UTC)).total_seconds())


APPROVALS_USAGE = {
    "wait": "pws approvals wait APPROVAL_ID [--timeout SECONDS]",
    "show": "pws approvals show APPROVAL_ID",
    "list": "pws approvals list",
}


def run_approval_read_command(context: object, approval_id: str | None, *, json_output: bool) -> None:
    """``pws approvals show`` (one approval) or ``list`` (the open ones): a state read, exit 0 whatever the state."""

    gateway: PhenosGateway | None = None
    try:
        gateway = gateway_from_cli_context(context)
        result = gateway.approvals() if approval_id is None else gateway.approval(approval_id)
    except PWSError as exc:
        usage = APPROVALS_USAGE["list" if approval_id is None else "show"]
        _report_failure(context, _failure_from(exc, usage=usage), json_output=json_output)
    finally:
        if gateway is not None:
            gateway.close()
    _emit_result(context, result, json_output=json_output)


def run_approval_wait_command(context: object, approval_id: str, *, timeout: float | None, json_output: bool) -> None:
    """Poll one approval until a person decides or the deadline passes. It reads only; it never uses the approval.

    Exit 0 when it reads approved or consumed (the repeated command gives the result), the pending exit when the
    deadline passes first, and 1 with the refusal's code when it reads rejected, expired, invalidated or cancelled.
    """

    from .phenos_commands_generated import APPROVAL_WAIT_REFUSALS

    if timeout is not None and not math.isfinite(timeout):
        usage_error(
            context,
            "--timeout must be a finite number of seconds",
            usage=APPROVALS_USAGE["wait"],
            json_output=json_output,
        )
    gateway: PhenosGateway | None = None
    try:
        gateway = gateway_from_cli_context(context)
        approval = _poll_approval(
            gateway, approval_id, timeout=timeout, on_wait=lambda: _terminal_note(context, APPROVAL_WAIT_PROGRESS)
        )
    except PWSError as exc:
        _report_failure(context, _failure_from(exc, usage=APPROVALS_USAGE["wait"]), json_output=json_output)
    finally:
        if gateway is not None:
            gateway.close()
    status = str(approval["status"])
    refusal = APPROVAL_WAIT_REFUSALS.get(status)
    if refusal is not None:
        _report_failure(context, _failure_from(PWSError(_message_for(refusal), code=refusal)), json_output=json_output)
    _emit_result(context, approval, json_output=json_output)
    if status == "pending":
        _terminal_note(context, APPROVAL_WAIT_TIMEOUT.format(approval_id=approval_id))
        raise typer.Exit(code=exit_number("pending"))


def _poll_approval(
    gateway: PhenosGateway, approval_id: str, *, timeout: float | None, on_wait: Callable[[], None]
) -> dict[str, object]:
    """The approval once it leaves pending, or as the last read before the deadline saw it.

    The deadline is ``timeout``, set before the first read, else the approval's own expiry once it is read. Every
    read's network waits are capped at the time left and no read starts after the deadline; a read already under way
    is not cut off. When the deadline ends a later read, the last pending read is the answer; when it ends the
    first one, the wait fails (no pending is made up). The stored external session plays no part: the reads
    use the login's JWT, so its lifetime is not a deadline here. The cadence is ``execution wait``'s.
    """

    deadline = math.inf if timeout is None else _monotonic() + timeout

    def time_left() -> float:
        return deadline - _monotonic()

    approval = gateway.approval(approval_id, time_left=time_left)
    if timeout is None:
        deadline = _monotonic() + _seconds_until(str(approval["expiresAt"]))
    if approval["status"] == "pending" and time_left() > 0:
        on_wait()
    interval = WAIT_FIRST_INTERVAL
    while approval["status"] == "pending" and time_left() > 0:
        _sleep(min(interval, time_left()))
        interval = min(interval * WAIT_INTERVAL_GROWTH, WAIT_MAX_INTERVAL)
        if time_left() <= 0:
            break
        try:
            approval = gateway.approval(approval_id, time_left=time_left)
        except TimeBudgetError:
            break
    return approval


def read_stdin_args(context: object, operation_id: str, *, stdin: bool, json_output: bool) -> dict[str, object]:
    """Read a ``--stdin`` command's JSON arguments; a bad input is a usage error in either output mode."""

    problem = None if stdin else "--stdin is required"
    args: object = None
    if problem is None:
        try:
            args = json.load(sys.stdin)
        except (json.JSONDecodeError, UnicodeDecodeError):
            problem = "stdin must contain one JSON object"
        else:
            if not isinstance(args, dict):
                problem = "stdin must contain one JSON object"
    if problem is not None:
        usage_error(context, problem, usage=_usage(operation_id), json_output=json_output)
    return cast(dict[str, object], args)


def usage_error(context: object, problem: str, *, usage: str | None, json_output: bool) -> NoReturn:
    """Human mode keeps click's own usage error; JSON mode gets the error document (never the rejected input)."""

    from .cli import EXIT_USAGE

    if _json_mode(_output_mode(context, json_output)):
        failure = _Failure(
            code="invalid_arguments",
            message=_message_for("invalid_arguments"),
            retryable=False,
            exit_code=EXIT_USAGE,
            usage=usage,
        )
        _report_failure(context, failure, json_output=json_output)
    raise typer.BadParameter(problem)


class PhenosGroup(TyperGroup):
    """The ``pws phenos`` and ``pws approvals`` groups: under JSON output a command line that does not parse is the
    usage error document.

    Click raises a parse failure before any command body runs, so its usage panel (which repeats the rejected value)
    would bypass the output rule. That covers this group's own options (``parse_args``) and every command under it
    (``invoke``). The mode comes from the root options or a ``--json`` among this group's own arguments, which were
    not parsed; human output keeps Click's own panel. The context is typed ``Any``: Typer 0.27+ vendors Click, so the
    base class's ``Context`` is a different class by Typer version and this package does not import ``click``.
    """

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        ctx.meta["phenos_json_flag"] = "--json" in args[: args.index("--")] if "--" in args else "--json" in args
        try:
            return super().parse_args(ctx, args)
        except Exception as exc:
            if not _is_click_usage_error(exc):
                raise
            _json_usage_failure(ctx, exc)
            raise

    def invoke(self, ctx: Any) -> object:
        try:
            return super().invoke(ctx)
        except Exception as exc:
            if not _is_click_usage_error(exc):
                raise
            _json_usage_failure(ctx, exc)
            raise


class _ClickUsageError(Protocol):
    @property
    def ctx(self) -> object | None: ...

    def format_message(self) -> str: ...


def _is_click_usage_error(error: Exception) -> TypeGuard[_ClickUsageError]:
    """Recognize Click errors from both Click and the copy bundled by recent Typer releases."""

    return any(base.__name__ == "UsageError" for base in type(error).__mro__)


def _is_no_args_is_help_error(error: object) -> bool:
    return any(base.__name__ == "NoArgsIsHelpError" for base in type(error).__mro__)


def _json_usage_failure(ctx: typer.Context, exc: _ClickUsageError) -> None:
    """Under JSON output, report a parse failure as the usage error document (which exits); otherwise return."""

    json_output = bool(ctx.meta.get("phenos_json_flag"))
    if _is_no_args_is_help_error(exc) or not _json_mode(_output_mode(ctx.obj, json_output)):
        return
    command_path = getattr(exc.ctx, "command_path", None)
    failed = command_path.split()[1:] if isinstance(command_path, str) else []
    usage_error(ctx.obj, exc.format_message(), usage=_usage_for_words(failed), json_output=json_output)


def _usage_for_words(words: Sequence[str]) -> str | None:
    """The expected form of the command these words name, hand-written or generated."""

    from .phenos_commands_generated import OPERATION_SPECS

    line = " ".join(words)
    hand_written = {f"phenos session {action}": usage for action, usage in SESSION_USAGE.items()}
    hand_written["phenos execution wait"] = WAIT_USAGE
    hand_written.update({f"approvals {action}": usage for action, usage in APPROVALS_USAGE.items()})
    if line in hand_written:
        return hand_written[line]
    for spec in OPERATION_SPECS:
        command = cast(dict[str, Sequence[str]], spec["command"])
        if " ".join(command["words"]) == line:
            return _usage(cast(str, spec["id"]))
    return None


def _usage(operation_id: str) -> str | None:
    """The expected command line from the registry, with a placeholder per argument and none of the given values."""

    try:
        spec = _operation(operation_id)
    except PWSError:
        return None
    command = cast(dict[str, object], spec["command"])
    parts = ["pws", *cast(Sequence[str], command["words"])]
    if command.get("stdinArgs") is True:
        return " ".join([*parts, "--stdin"]) + "  (arguments as one JSON object on stdin)"
    properties = cast(dict[str, dict[str, object]], cast(dict[str, object], spec["argsSchema"]).get("properties", {}))

    def placeholder(field: str) -> str:
        kind = properties.get(field, {}).get("type")
        return "N" if kind == "integer" else ("ID" if field in {"image", "roi", "execution"} else field.upper())

    # A positional follows the command words, before any flag; an optional argument is shown in brackets.
    for positional in cast(Sequence[Mapping[str, object]], command.get("positionals", [])):
        text = placeholder(cast(str, positional["field"]))
        parts.append(f"[{text}]" if positional.get("optional") is True else text)
    for flag in cast(Sequence[Mapping[str, object]], command["flags"]):
        text = f"{flag['flag']} {placeholder(cast(str, flag['field']))}"
        parts.append(f"[{text}]" if flag.get("optional") is True else text)
    return " ".join(parts)


def _emit_result(context: object, data: object, *, json_output: bool) -> None:
    """Success: the ``data`` object alone on stdout, shaped by the output mode."""

    from .cli import _console

    mode = _output_mode(context, json_output)
    if _json_mode(mode):
        typer.echo(_render_json(data))
    elif mode == "quiet":
        for identifier in _identifiers(data):
            typer.echo(identifier)
    else:
        for renderable in _tables(data):
            _console().print(renderable)


def _identifiers(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    for key in ("executionId", "sessionId", "approvalId"):
        if isinstance(data.get(key), str):
            return [cast(str, data[key])]
    ids: list[str] = []
    for key, field in (("annotations", "id"), ("rows", "roiId"), ("items", "approvalId")):
        rows = data.get(key)
        if isinstance(rows, list):
            ids.extend(row[field] for row in rows if isinstance(row, dict) and isinstance(row.get(field), str))
    return ids


def _cell(value: object) -> str:
    return escape(value if isinstance(value, str) else _render_json(value))


def _tables(data: object) -> list[object]:
    from rich.table import Table

    if not isinstance(data, dict):
        return [escape(_render_json(data))]
    row_lists = {
        key: value
        for key, value in data.items()
        if isinstance(value, list) and value and all(isinstance(row, dict) for row in value)
    }
    tables: list[object] = []
    fields = Table(box=None, show_header=False, pad_edge=False)
    fields.add_column("field", style="bold")
    fields.add_column("value")
    for key, value in data.items():
        if key not in row_lists:
            fields.add_row(escape(key), _cell(value))
    if fields.row_count:
        tables.append(fields)
    for key, rows in row_lists.items():
        columns = list(dict.fromkeys(name for row in rows for name in row))
        grid = Table(box=None, pad_edge=False)
        for name in columns:
            grid.add_column(escape(name), style="bold" if name == columns[0] else None)
        for row in rows:
            grid.add_row(*(_cell(row.get(name, "")) for name in columns))
        tables.extend([f"[bold]{escape(key)}[/bold]", grid])
    return tables


def _render_json(value: object) -> str:
    from .cli import render_json

    return render_json(value)


def _session_secret(credential: Credential | None) -> str | None:
    if isinstance(credential, (DeviceSessionCredential, SessionCredential)):
        return credential.session_token
    return None


def _data_file_operations() -> set[str]:
    from .phenos_commands_generated import PWS_DATA_FILE

    return set(cast(list[str], PWS_DATA_FILE["operations"]))


def _with_local_data_file(gateway: PhenosGateway, answer: dict[str, object], out: str | None) -> dict[str, object]:
    """The answer with its data file downloaded and named by its local path; a run's own path is left as it is."""

    from .phenos_commands_generated import PWS_DATA_FILE

    file, sha256, image = answer.get("file"), answer.get("fileSha256"), answer.get("image")
    if not isinstance(file, str) or not file.startswith("phenos-artifact://") or not isinstance(sha256, str):
        return answer
    image_id = cast(dict[str, object], image).get("id") if isinstance(image, dict) else None
    if out is None and not isinstance(image_id, str):
        raise ValidationError("Hub answered a data file without its image", code="internal")
    target = Path(out) if out is not None else Path("annotations") / f"{image_id}.json"
    gateway.download_data_file(file, target, sha256=sha256, max_bytes=cast(int, PWS_DATA_FILE["maxBytes"]))
    return {**answer, "file": str(target)}


def _routes() -> dict[str, str]:
    from .phenos_commands_generated import TOOL_GATEWAY_ROUTES

    return TOOL_GATEWAY_ROUTES


def _ask_again_header() -> tuple[str, str]:
    from .phenos_commands_generated import PWS_ASK_AGAIN

    return str(PWS_ASK_AGAIN["header"]), str(PWS_ASK_AGAIN["value"])


def _operation(operation_id: str) -> dict[str, object]:
    from .phenos_commands_generated import OPERATION_SPECS

    for spec in OPERATION_SPECS:
        if spec.get("id") == operation_id:
            return spec
    raise ValidationError("operation is not registered in the Tool Gateway", code="invalid_arguments")


def _schema(name: str) -> dict[str, object]:
    from .phenos_commands_generated import TOOL_GATEWAY_SCHEMAS

    return TOOL_GATEWAY_SCHEMAS[name]


def _limits() -> dict[str, object]:
    from .phenos_commands_generated import TOOL_GATEWAY_LIMITS

    return cast(dict[str, object], TOOL_GATEWAY_LIMITS)


def _call_schema(args_schema: dict[str, object]) -> dict[str, object]:
    operation_props = {"operation": {"type": "string"}, "version": {"type": "integer", "minimum": 1}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {**operation_props, "args": args_schema},
        "required": ["operation", "version", "args"],
        "additionalProperties": False,
    }


def _validated_json(value: object, schema: dict[str, object], *, code: str) -> dict[str, object]:
    try:
        Draft202012Validator(schema).validate(value)
    except (SchemaError, JsonSchemaValidationError):
        message = (
            "Tool Gateway request does not match the registered contract"
            if code == "invalid_arguments"
            else "Hub returned data outside the Tool Gateway contract"
        )
        raise ValidationError(message, code=code) from None
    return cast(dict[str, object], _project_json(value, schema, schema))


def _check_result_size(value: object, operation: str, *, execution: bool) -> None:
    # Count unprojected metadata, including unknown keys and artifact references.
    metadata = value
    output = value
    sandbox_operation: object = operation
    if execution and isinstance(value, dict):
        sandbox_operation = value.get("operation")
        output = value.get("output")
    try:
        if isinstance(output, dict):
            field = (
                "output"
                if sandbox_operation == "sandbox_bash"
                else ("text" if sandbox_operation == "sandbox_read" and output.get("kind") == "text" else None)
            )
            text = output.get(field) if field is not None else None
            if field is not None and isinstance(text, str):
                if len(text.encode("utf-8")) > cast(int, _limits()["textOutputBytes"]) + cast(
                    int, _limits()["cutMarkerBytes"]
                ):
                    raise ValueError
                bounded = {**output, field: ""}
                metadata = {**cast(dict[str, object], value), "output": bounded} if execution else bounded
        encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > cast(int, _limits()["structuredResultBytes"]):
            raise ValueError
    except (TypeError, ValueError, UnicodeError):
        raise ValidationError(
            "Tool Gateway result exceeds its JSON or text size limit", code="tool_output_limit"
        ) from None


def _validated_execution(value: object) -> dict[str, object]:
    # JSON Schema drops Zod's CheckedToolExecutionSchema transform; apply its
    # operation-specific output validation and projection at this reader too.
    schema = _schema("execution")
    execution = _validated_json(_project_json(value, schema, schema), schema, code="internal")
    spec = _operation(cast(str, execution["operation"]))
    if execution["status"] == "succeeded" and execution["operation"] == "phenos_inference_start":
        # What the inference's auto-annotate step wrote: the TS contract's explicit inference case.
        output_schema = _schema("inferenceOutput")
        output = _project_json(execution["output"], output_schema, output_schema)
        execution["output"] = _validated_json(output, output_schema, code="internal")
        # The TS schema's refinement, which JSON Schema cannot express: annotationIds names the first created
        # annotations, at most the schema's cap on that list.
        written = cast(dict[str, object], execution["output"])
        properties = cast(dict[str, dict[str, object]], output_schema["properties"])
        named_rows = cast(int, properties["annotationIds"]["maxItems"])
        if len(cast(list[object], written["annotationIds"])) != min(cast(int, written["created"]), named_rows):
            raise ValidationError(
                "Hub returned an inference output that does not count its annotations", code="internal"
            )
    elif spec["piTool"] != "pws" and execution["status"] == "succeeded":
        output_schema = cast(dict[str, object], spec["resultSchema"])
        output = _project_json(execution["output"], output_schema, output_schema)
        execution["output"] = _validated_json(output, output_schema, code="internal")
        if execution["artifacts"] != cast(dict[str, object], execution["output"]).get("artifacts", []):
            raise ValidationError("Hub returned artifacts outside the output preview", code="internal")
    elif execution["output"] is not None:
        raise ValidationError("Hub returned data outside the Tool Gateway execution contract", code="internal")
    return execution


def _project_json(value: object, schema: dict[str, object], root: dict[str, object]) -> object:
    target = _resolve_schema_ref(schema, root)
    if target is not None:
        return _project_json(value, target, root)
    branch = _matching_schema_branch(value, schema, root)
    if branch is not None:
        return _project_json(value, branch, root)
    if isinstance(value, dict):
        return _project_object(value, schema, root)
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [_project_json(item, cast(dict[str, object], schema["items"]), root) for item in value]
    return value


def _resolve_schema_ref(schema: Mapping[str, object], root: dict[str, object]) -> dict[str, object] | None:
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    target: object = root
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        target = target.get(key) if isinstance(target, dict) else None
    return cast(dict[str, object] | None, target) if isinstance(target, dict) else None


def _matching_schema_branch(
    value: object,
    schema: dict[str, object],
    root: dict[str, object],
) -> dict[str, object] | None:
    branches = schema.get("anyOf", schema.get("oneOf"))
    if not isinstance(branches, list):
        return None
    root_validator = Draft202012Validator(root)
    for branch in branches:
        if isinstance(branch, dict) and root_validator.evolve(schema=branch).is_valid(
            _project_json(value, branch, root)
        ):
            return branch
    return None


def _project_object(
    value: dict[str, object], schema: Mapping[str, object], root: dict[str, object]
) -> dict[str, object]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return value
    additional = schema.get("additionalProperties")
    projected: dict[str, object] = {}
    for key, item in value.items():
        child = properties.get(key)
        if isinstance(child, dict):
            projected[key] = _project_json(item, child, root)
        elif isinstance(additional, dict):
            projected[key] = _project_json(item, additional, root)
        elif additional is True:
            projected[key] = item
    return projected


def _parse_expiry(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("Hub returned an invalid Gateway credential expiry", code="internal") from None
    if parsed.tzinfo is None:
        raise ValidationError("Hub returned an invalid Gateway credential expiry", code="internal")
    return parsed.astimezone(UTC)


def _safe_auth_error(error: PWSError) -> PWSError:
    return AuthError(
        "the user session could not be exchanged",
        status_code=error.status_code,
        request_id=error.request_id,
        code="unauthenticated",
    )


def _is_connect_failure(error: PWSError) -> bool:
    """True when the transport failed before any request bytes could have been sent."""

    return isinstance(error, TransportError) and isinstance(
        error.__cause__, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
    )


def _message_for(code: str) -> str:
    from .phenos_commands_generated import PWS_ERROR_MESSAGES

    return PWS_ERROR_MESSAGES[code]


def _normalized_code(error: PWSError) -> str:
    """A ``PwsErrorCode`` for any error: the Hub's own code, else its HTTP status, else the SDK error class."""

    from .phenos_commands_generated import PWS_EXIT_CODES

    code = error.code or ""
    if code in PWS_EXIT_CODES:
        return code
    by_status = {
        400: "invalid_arguments",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        409: "internal",
        429: "rate_limited",
    }
    if error.status_code in by_status:
        return by_status[error.status_code]
    by_class: tuple[tuple[type[PWSError], str], ...] = (
        (AuthError, "unauthenticated"),
        (PermissionError, "forbidden"),
        (NotFoundError, "not_found"),
        (RateLimitError, "rate_limited"),
        (ValidationError, "invalid_arguments"),
        (TransportError, "tool_unavailable"),
    )
    return next((name for kind, name in by_class if isinstance(error, kind)), "internal")


def _safe_gateway_error(error: PWSError, *, post: bool = False) -> PWSError:
    """The Hub's error with our fixed message for its code; the Hub's own text never leaves the SDK.

    A POST that failed at the network level after connecting may have been processed, so its outcome is unknown.
    """

    status_code = error.status_code
    request_id = error.request_id
    if post and isinstance(error, TransportError) and not error.code:
        code = "tool_unavailable" if _is_connect_failure(error) else "tool_outcome_unknown"
    else:
        code = _normalized_code(error)
    safe_message = _message_for(code)
    if isinstance(error, AuthError):
        return AuthError(safe_message, status_code=status_code, request_id=request_id, code=code)
    if isinstance(error, PermissionError):
        return PermissionError(safe_message, status_code=status_code, request_id=request_id, code=code)
    if isinstance(error, NotFoundError):
        return NotFoundError(safe_message, status_code=status_code, request_id=request_id, code=code)
    if isinstance(error, RateLimitError):
        return RateLimitError(
            safe_message, retry_after=error.retry_after, status_code=status_code, request_id=request_id, code=code
        )
    if isinstance(error, TransportError):
        return TransportError(safe_message, status_code=status_code, request_id=request_id, code=code)
    return PWSError(safe_message, status_code=status_code, request_id=request_id, code=code)


def exit_number(category: str) -> int:
    """Resolve a shared exit category to this CLI's number; the numbers live only in ``cli.py``."""

    from . import cli

    numbers = {
        "error": cli.EXIT_ERROR,
        "usage": cli.EXIT_USAGE,
        "auth": cli.EXIT_AUTH,
        "not_found": cli.EXIT_NOT_FOUND,
        "permission": cli.EXIT_PERMISSION,
        "failed": cli.EXIT_ACTION_FAILED,
        "unknown": cli.EXIT_ACTION_TIMEOUT,
        "pending": cli.EXIT_APPROVAL_PENDING,
    }
    return numbers[category]
