"""The ``pws`` command: noun-verb tree over the operator SDK.

Output contract (interface contract section 3): the default is a Rich table
on a TTY, ``--json`` prints one stable JSON document, ``--jsonl`` one JSON
object per line, ``-q`` prints identifiers only (one per line, xargs-friendly).
``PWS_OUTPUT`` selects the mode when no flag is given; a non-TTY stdout
defaults to ``json``.  Progress and status text only ever go to stderr, so
stdout stays machine-readable under ``--json``/``--jsonl``/``-q``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shlex
import sys
import tempfile
import webbrowser
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, SecretStr
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn
from rich.table import Table
from typer.core import TyperGroup

from ._media_shared import _validate_path_parameter
from ._transport import Page, Pagination, Transport, _installed_version, atomic_binary_writer
from .actions import describe_action
from .config import (
    ALLOW_INSECURE_HUB_ENV,
    DEFAULT_BASE_URL,
    Config,
    _read_profile,
    credentials_path,
    device_hub,
    normalize_hub_url,
    read_agent_key_file,
    require_secure_hub,
)
from .device_auth import DeviceLogin, revoke_device_session
from .errors import (
    ActionFailed,
    ActionTimeout,
    AmbiguousAction,
    AuthError,
    NotFoundError,
    PermissionError,
    PWSError,
    RateLimitError,
    TransportError,
    UnknownAction,
)
from .facade import MAX_PAGE_SIZE, PWS, IssuedAccessKey, _prepare_download_directory
from .models import SpotStructure
from .models.generated import SpotStructureDeviceAction, SpotStructureDeviceComponentAction
from .phenos import (
    SESSION_USAGE,
    PhenosGroup,
    run_approval_read_command,
    run_approval_wait_command,
    run_session_command,
    run_wait_command,
    usage_error,
)
from .phenos_commands_generated import add_generated_commands
from .provisioning import check_provisioning


class _HintingGroup(TyperGroup):
    """Root and top-level group: a noun that lives in another group is refused with the full path, never run.

    Typer 0.27+ vendors Click, so nothing here imports ``click``; groups are told apart by their ``commands``.
    """

    def resolve_command(self, ctx: Any, args: list[str]) -> tuple[str | None, Any, list[str]]:
        root = ctx.find_root().command
        if args and isinstance(root, _HintingGroup) and self.get_command(ctx, args[0]) is None:
            path = root._grouped_nouns().get(args[0])
            if path is not None:
                ctx.fail(f"'{args[0]}' is under a group: use `pws {path}`")
        return super().resolve_command(ctx, args)

    def _grouped_nouns(self) -> dict[str, str]:
        """Noun -> its path under a top-level group, read off the registered command tree."""

        nouns: dict[str, str] = {}

        def walk(commands: Mapping[str, Any], prefix: str) -> None:
            for name, command in commands.items():
                children = getattr(command, "commands", None)
                if isinstance(children, dict):
                    nouns.setdefault(name, f"{prefix}{name}")
                    walk(children, f"{prefix}{name} ")

        for name, command in self.commands.items():
            children = getattr(command, "commands", None)
            if isinstance(children, dict):
                walk(children, f"{name} ")
        return nouns


app = typer.Typer(
    cls=_HintingGroup,
    add_completion=False,
    no_args_is_help=True,
    help="PhytoWorks operator CLI.",
    pretty_exceptions_show_locals=False,
)
_GROUPS: dict[tuple[str, ...], typer.Typer] = {}
_SUMMARY: dict[str, str] = {}


def group(*words: str, help: str | None = None, **kwargs: Any) -> typer.Typer:
    """The Typer group at ``words`` (``group("edge", "spots")``), created with any missing parent on the way.

    The same path always returns the same group, so commands attached later land beside the ones already there.
    A top-level group's help is its ``help`` text followed by the nouns registered inside it, whatever the call
    order, and it hints like the root (``pws edge captures`` names ``pws data captures``); ``kwargs`` (for
    example ``cls=``) go to ``typer.Typer`` when the group is created, and are refused with ``ValueError`` when
    the group already exists.
    """

    if kwargs and words in _GROUPS:
        raise ValueError(f"group {' '.join(words)!r} already exists; {sorted(kwargs)} would be ignored")

    parent = app
    for depth in range(1, len(words) + 1):
        path = words[:depth]
        found = _GROUPS.get(path)
        if found is None:
            defaults: dict[str, Any] = {"no_args_is_help": True}
            if depth == 1:
                defaults["cls"] = _HintingGroup
            found = typer.Typer(**{**defaults, **(kwargs if path == words else {})})
            _GROUPS[path] = found
            parent.add_typer(found, name=path[-1])
        parent = found
    if help is not None:
        parent.info.help = help
        if len(words) == 1:
            _SUMMARY[words[0]] = help.rstrip(".")
    top = _GROUPS[words[:1]]
    if nouns := ", ".join(item.name or "" for item in top.registered_groups):
        summary = _SUMMARY.get(words[0])
        top.info.help = f"{summary}: {nouns}." if summary else f"{nouns}."
    return parent


auth_app = group("auth", help="Credential setup.")
orgs_app = group("orgs", help="Workspaces you belong to (read-only).")
config_app = group("config", help="Effective non-secret command settings.")
group("edge", help="Sites and equipment")
group("data", help="Captures and photos")
spots_app = group("edge", "spots", help="Spots and their discovered structure.")
devices_app = group("edge", "devices", help="Devices and current status (read-only).")
components_app = group("edge", "components", help="Components (read-only).")
actions_app = group("edge", "actions", help="Run actions and inspect executions.")
rules_app = group("edge", "rules", help="Rules (read-only; Console owns authoring).")
telemetry_app = group("edge", "telemetry", help="Time-series telemetry (read-only).")
agents_app = group("edge", "agents", help="Device agents and their API keys.")
provisioning_app = group("edge", "provisioning", help="Advisory permission checks before provisioning.")
keys_app = group(
    "edge", "agents", "keys", help="An agent's device API keys; a secret is only ever written to a 0600 file."
)
captures_app = group("data", "captures", help="Captures (read-only).")
media_app = group("data", "media", help="Media assets, uploads, and downloads.")
phenos_app = typer.Typer(
    cls=PhenosGroup, no_args_is_help=True, help="External Phenos Tool Gateway sessions and operations."
)
phenos_sessions_app = typer.Typer(no_args_is_help=True, help="Create, inspect, and revoke an external session.")
add_generated_commands(phenos_app)
phenos_app.add_typer(phenos_sessions_app, name="session")
# `execution wait` is hand-written (not a registry operation, so the in-app model never sees it); it joins the
# generated `execution` group.
phenos_execution_app = next(
    group.typer_instance
    for group in phenos_app.registered_groups
    if group.name == "execution" and group.typer_instance is not None
)
app.add_typer(phenos_app, name="phenos")
approvals_app = typer.Typer(
    cls=PhenosGroup,
    no_args_is_help=True,
    help="Requests from this login that wait for a person's approval in Phenos.",
)
app.add_typer(approvals_app, name="approvals")


# Typed exit codes.
# The Phenos error codes pick a category; the numbers stay here.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_PERMISSION = 5
EXIT_ACTION_FAILED = 6  # a started job (action or Phenos execution) ended failed or cancelled
EXIT_ACTION_TIMEOUT = 7  # a started job's outcome is unknown: it may still be running (timed out waiting, or lost)
EXIT_PROVISIONING_DENIED = 8
EXIT_PROVISIONING_UNKNOWN = 9
# A Phenos change or delete waits for a person's approval and nothing started. 10, because 8 and 9 belong to
# `pws provisioning check`.
EXIT_APPROVAL_PENDING = 10


def exit_code_for(error: PWSError) -> int:
    if isinstance(error, UnknownAction | AmbiguousAction):
        return EXIT_USAGE
    if isinstance(error, ActionTimeout):
        return EXIT_ACTION_TIMEOUT
    if isinstance(error, ActionFailed):
        return EXIT_ACTION_FAILED
    if isinstance(error, PermissionError):
        return EXIT_PERMISSION
    if isinstance(error, NotFoundError):
        return EXIT_NOT_FOUND
    if isinstance(error, AuthError):
        return EXIT_AUTH
    return EXIT_ERROR


class OutputMode(StrEnum):
    TABLE = "table"
    JSON = "json"
    JSONL = "jsonl"
    QUIET = "quiet"


@dataclass(frozen=True, slots=True)
class CliContext:
    mode: OutputMode
    org: str | None
    base_url: str | None
    profile: str

    def client(self) -> PWS:
        try:
            return PWS(base_url=self.base_url, org=self.org, profile=self.profile)
        except PWSError as exc:
            raise typer.Exit(code=_report(exc)) from exc


def resolve_output_mode(
    *,
    json_flag: bool,
    jsonl_flag: bool,
    quiet_flag: bool,
    env: Mapping[str, str] | None = None,
    isatty: bool | None = None,
) -> OutputMode:
    """Flags win over ``PWS_OUTPUT``; without either, a TTY gets a table and a pipe gets JSON."""

    if quiet_flag:
        return OutputMode.QUIET
    if jsonl_flag:
        return OutputMode.JSONL
    if json_flag:
        return OutputMode.JSON
    configured = (env if env is not None else os.environ).get("PWS_OUTPUT", "").strip().lower()
    if configured:
        try:
            return OutputMode(configured)
        except ValueError as exc:
            raise typer.BadParameter(f"PWS_OUTPUT must be one of {[mode.value for mode in OutputMode]}") from exc
    tty = sys.stdout.isatty() if isatty is None else isatty
    return OutputMode.TABLE if tty else OutputMode.JSON


def render_json(value: object) -> str:
    """Render stable compact JSON for scripts and CI."""

    return json.dumps(_json_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, Page):
        return {"items": _json_value(value.items), "pagination": _json_value(value.pagination)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {name: _json_value(getattr(value, name)) for name in value.__dataclass_fields__}
    return value


@dataclass(frozen=True, slots=True)
class Column:
    header: str
    render: Callable[[BaseModel], str]


def _field(name: str) -> Callable[[BaseModel], str]:
    def render(model: BaseModel) -> str:
        value = getattr(model, name, None)
        if value is None:
            extra = model.model_extra or {}
            value = extra.get(name, extra.get(_camel_case(name)))
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        return "" if value is None else str(value)

    return render


def _camel_case(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _mapping_keys(name: str) -> Callable[[BaseModel], str]:
    def render(model: BaseModel) -> str:
        value = getattr(model, name, None)
        if value is None:
            extra = model.model_extra or {}
            value = extra.get(name, extra.get(_camel_case(name)))
        return ", ".join(value) if isinstance(value, Mapping) else ""

    return render


CAPTURE_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("status", _field("status")),
    Column("spot", _field("spot_id")),
    Column("media", _field("media_asset_count")),
    Column("created", _field("created_at")),
)
ORGANIZATION_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("slug", _field("slug")),
    Column("status", _field("status")),
)
USER_ORGANIZATION_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("slug", _field("slug")),
    Column("role", lambda model: str((getattr(model, "metadata", None) or {}).get("userRole", ""))),
    Column("status", _field("status")),
)
SPOT_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("slug", _field("slug")),
    Column("workspace", _field("organization_id")),
)
DEVICE_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("identifier", _field("identifier")),
    Column("spot", _field("spot_id")),
)
DEVICE_STATUS_COLUMNS = (
    Column("manualMode", _field("manual_mode")),
    Column("updatedAt", _field("updated_at")),
    Column("actions", _mapping_keys("actions")),
    Column("topics", _mapping_keys("topics")),
)
COMPONENT_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("device", _field("device_id")),
)
RULE_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("enabled", _field("enabled")),
)
EXECUTION_COLUMNS = (
    Column("execution", _field("execution_id")),
    Column("action", _field("action_def_id")),
    Column("status", _field("status")),
)
RULE_EXECUTION_COLUMNS = (
    Column("id", _field("id")),
    Column("rule", _field("rule_id")),
    Column("status", _field("status")),
    Column("started", _field("actual_start_time")),
    Column("ended", _field("actual_end_time")),
)
EXECUTION_LIST_COLUMNS = (
    Column("id", _field("id")),
    Column("definition", _field("definition_id")),
    Column("device", _field("device_id")),
    Column("status", _field("status")),
)
STRUCTURE_COLUMNS = (
    Column("spot", lambda model: _field("spot")(model)),
    Column("devices", lambda model: str(len(getattr(model, "devices", ())))),
    Column("rules", lambda model: str(len(getattr(model, "rules", ())))),
)
AGENT_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("name")),
    Column("identifier", _field("identifier")),
    Column("spot", _field("spot_id")),
)
AGENT_LIST_COLUMNS = (*AGENT_COLUMNS, Column("status", _field("status")))
ACCESS_KEY_COLUMNS = (
    Column("id", _field("id")),
    Column("name", _field("key_name")),
    Column("preview", _field("key_preview")),
    Column("usage", _field("key_usage")),
    Column("active", _field("is_active")),
    Column("recoverable", _field("recoverable")),
    Column("expires", _field("expires_at")),
)
MEDIA_COLUMNS = (
    Column("id", _field("id")),
    Column("modality", _field("modality")),
    Column("format", _field("format")),
    Column("capture", _field("capture_session_id")),
    Column("width", _field("width")),
    Column("height", _field("height")),
    Column("captured", _field("captured_at")),
)


def emit(
    context: CliContext, items: Sequence[BaseModel], *, columns: Sequence[Column], page: Page[Any] | None = None
) -> None:
    """Write a collection in the resolved output mode."""

    if context.mode is OutputMode.QUIET:
        for item in items:
            typer.echo(_field("id")(item))
        return
    if context.mode is OutputMode.JSONL:
        for item in items:
            typer.echo(render_json(item))
        return
    if context.mode is OutputMode.JSON:
        typer.echo(render_json(page if page is not None else {"items": list(items)}))
        return
    table = Table(box=None, header_style="bold")
    for column in columns:
        table.add_column(column.header)
    for item in items:
        table.add_row(*(column.render(item) for column in columns))
    _console().print(table)


def emit_listing(
    context: CliContext,
    result: Page[Any],
    *,
    columns: Sequence[Column],
    limit: int | None,
    page: int | None,
) -> None:
    """Write a listing: one explicit ``--page``, or every page up to ``--limit``.

    A result cut short by ``--limit`` is announced on stderr so stdout stays machine-clean.
    """

    if page is not None:
        emit(context, result.items, columns=columns, page=result)
        return
    items, last, cut = _walk_pages(result, limit)
    pagination = last.pagination
    if last is not result:
        # After a walk the per-page fields (page, limit, totalPages) describe only the last page
        # fetched, so report just what holds for the whole result: the total and whether rows remain.
        pagination = Pagination(total=pagination.total, has_next=cut)
    emit(context, items, columns=columns, page=replace(last, items=items, pagination=pagination))
    if cut:
        total = last.pagination.total
        of = f" of {total}" if total is not None else ""
        typer.echo(f"showing {len(items)}{of} results (cut by --limit {limit}); raise --limit to see more", err=True)


def _listing_context(ctx: typer.Context, *, page: int | None, limit: int | None) -> CliContext:
    """Refuse ``--page`` with a ``--limit`` one Hub page cannot hold instead of printing a cut page."""

    if page is not None and limit is not None and limit > MAX_PAGE_SIZE:
        message = (
            f"--limit {limit} exceeds one Hub page ({MAX_PAGE_SIZE}) with --page; "
            f"drop --page to read every result up to --limit, or keep --limit at {MAX_PAGE_SIZE} or less"
        )
        _console(stderr=True).print(f"[red]error:[/red] {escape(message)}", highlight=False, soft_wrap=True)
        raise typer.Exit(code=EXIT_USAGE)
    context: CliContext = ctx.obj
    return context


def _walk_pages(first: Page[Any], limit: int | None) -> tuple[list[Any], Page[Any], bool]:
    """Collect items across pages; the flag says whether ``limit`` left results unread."""

    items: list[Any] = []
    current: Page[Any] | None = first
    last = first
    while current is not None:
        last = current
        for item in current.items:
            if limit is not None and len(items) >= limit:
                return items, last, True
            items.append(item)
        if limit is not None and len(items) >= limit:
            return items, last, current._next is not None
        current = current._next() if current._next is not None else None
    return items, last, False


def emit_one(context: CliContext, item: BaseModel, *, columns: Sequence[Column]) -> None:
    if context.mode is OutputMode.QUIET:
        typer.echo(_field("id")(item))
    elif context.mode in (OutputMode.JSON, OutputMode.JSONL):
        typer.echo(render_json(item))
    else:
        table = Table(box=None, show_header=False)
        table.add_column("field", style="bold")
        table.add_column("value")
        for column in columns:
            table.add_row(column.header, column.render(item))
        _console().print(table)


def emit_value(context: CliContext, value: object) -> None:
    """Write an untyped object while retaining the JSON output contract."""

    if context.mode is OutputMode.QUIET:
        for identifier in _quiet_ids(value):
            typer.echo(identifier)
        return
    typer.echo(render_json(value))


def _quiet_ids(value: object) -> Iterable[str]:
    if isinstance(value, BaseModel):
        yield from _quiet_ids(value.model_dump(mode="json", by_alias=True))
        return
    if isinstance(value, Mapping):
        identifier = value.get("id") or value.get("executionId")
        if isinstance(identifier, str) and identifier:
            yield identifier
            return
        for key in ("topics", "items", "results"):
            if key in value:
                yield from _quiet_ids(value[key])
        metrics = value.get("metrics")
        if isinstance(metrics, Mapping):
            yield from (key for key in metrics if isinstance(key, str) and key)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _quiet_ids(item)


def _console(*, stderr: bool = False) -> Console:
    return Console(stderr=stderr, no_color="NO_COLOR" in os.environ)


def _report(error: PWSError) -> int:
    message = str(error)
    if error.code:
        message = f"[{error.code}] {message}"
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        message = f"{message} (retry_after={error.retry_after}s)"
    if error.request_id:
        message = f"{message} (requestId={error.request_id})"
    _console(stderr=True).print(f"[red]error:[/red] {escape(message)}", highlight=False, soft_wrap=True)
    return exit_code_for(error)


def _read_identifier(value: str) -> str:
    try:
        _validate_path_parameter("identifier", value)
    except PWSError as exc:
        raise typer.Exit(code=_report(exc)) from exc
    return value


def _run(context: CliContext, action: Callable[[PWS], None], *, needs: str | None = None) -> None:
    """Run one command; ``needs`` names the capability a provisioning command's 403 is about."""

    client = context.client()
    try:
        action(client)
    except PWSError as exc:
        if needs is not None and isinstance(exc, PermissionError) and exc.status_code == 403:
            code = _report_denied(client, exc, needs)
        else:
            code = _report(exc)
        raise typer.Exit(code=code) from exc
    finally:
        client.close()


# What each provisioning step needs (Hub ProvisioningAccessService for creates, AccessGuard for keys).
NEEDS_SPOT_CREATE = "creating a spot needs organization:MANAGE or a Workspace-wide spot:CREATE grant"
NEEDS_AGENT_CREATE = (
    "creating an agent needs organization:MANAGE, or a Workspace-wide agent:CREATE grant "
    "together with spot:UPDATE on the target spot"
)
NEEDS_AGENT_KEYS = "managing an agent's device keys needs agent:MANAGE on that agent"
GRANTED_BY = "the built-in Workspace owner and admin roles carry it"
# Config.resolve's order; explicit --org overrides the environment and profile.
SCOPE_ORDER = "the scope comes from --org, else PWS_ORG, else the profile's org"


def _report_denied(client: PWS, error: PWSError, needs: str) -> int:
    """Name the missing capability when the scope is one of the caller's organizations, else the scope.

    The Hub answers a wrong organization and a missing capability with the same 403 ``ACCESS_DENIED``, so the
    caller's memberships decide which one this is. The text is static apart from the caller's own role: nothing
    from the response is echoed (a key route's error is status-only).
    """

    org = client.config.org
    if org is None:
        return _report(error)
    try:
        memberships = client.me().organizations
    except PWSError:
        message = (
            f"{needs} ({GRANTED_BY}); your Workspaces could not be read, so also check that "
            f"the scope {org!r} names one of them ({SCOPE_ORDER})"
        )
    else:
        match = next((item for item in memberships if item.id == org), None)
        by_slug = next((item for item in memberships if item.slug == org), None)
        if by_slug is not None and match is None:
            # The Hub reads X-Organization-Id as an id, so a slug is a scope error, not a missing capability.
            message = f"Workspace scope {org!r} is a slug; set its id {by_slug.id!r} instead ({SCOPE_ORDER})"
        elif match is None:
            message = (
                f"Workspace scope {org!r} is not one of your Workspaces ({SCOPE_ORDER}; `pws auth whoami` lists yours)"
            )
        else:
            role = (match.metadata or {}).get("userRole") or "unknown"
            message = (
                f"{needs}; your role in {org!r} is {role} and {GRANTED_BY}. Ask a Workspace owner or "
                "admin for that grant, or run this as an account that has it"
            )
    denied = PermissionError(
        f"access denied (HTTP {error.status_code}): {message}",
        status_code=error.status_code,
        request_id=error.request_id,
        code=error.code,
    )
    return _report(denied)


def _progress(context: CliContext, label: str) -> Progress | None:
    if context.mode is OutputMode.QUIET or not sys.stderr.isatty():
        return None
    return Progress(
        TextColumn(label),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=_console(stderr=True),
        transient=True,
    )


# ---------------------------------------------------------------------------
# root
# ---------------------------------------------------------------------------


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"phytoworks {_installed_version()}")
        raise typer.Exit()


@app.callback()
def root_options(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_show_version, is_eager=True, help="Show version and exit."),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print one stable JSON document.")] = False,
    jsonl: Annotated[bool, typer.Option("--jsonl", help="Print one JSON object per line.")] = False,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Print identifiers only (one per line).")] = False,
    org: Annotated[
        str | None, typer.Option("--org", help="Workspace id, overrides PWS_ORG and the profile's Workspace.")
    ] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Hub API base URL.")] = None,
    profile: Annotated[str, typer.Option("--profile", help="Credentials profile.")] = "default",
    allow_insecure_hub: Annotated[
        bool,
        typer.Option(
            "--allow-insecure-hub",
            help=f"Allow remote http:// development Hub and storage URLs (as {ALLOW_INSECURE_HUB_ENV}=1); "
            "never for production hosts.",
        ),
    ] = False,
) -> None:
    if allow_insecure_hub:
        # The one switch every credential path reads; restored when this command ends.
        previous = os.environ.get(ALLOW_INSECURE_HUB_ENV)
        os.environ[ALLOW_INSECURE_HUB_ENV] = "1"

        def restore_switch() -> None:
            if previous is None:
                os.environ.pop(ALLOW_INSECURE_HUB_ENV, None)
            else:
                os.environ[ALLOW_INSECURE_HUB_ENV] = previous

        ctx.call_on_close(restore_switch)
    ctx.obj = CliContext(
        mode=resolve_output_mode(json_flag=json_output, jsonl_flag=jsonl, quiet_flag=quiet),
        org=org,
        base_url=base_url,
        profile=profile,
    )
    # A rate-limit wait is one stderr line for this command only; no propagation, so an embedding root handler
    # does not print it twice. The handler is made here so it writes to the stderr this command runs with.
    logger = logging.getLogger("phytoworks._transport")
    handler, propagate = logging.StreamHandler(), logger.propagate
    logger.addHandler(handler)
    logger.propagate = False

    def restore() -> None:
        logger.removeHandler(handler)
        logger.propagate = propagate

    ctx.call_on_close(restore)


def _external_reference(value: str, *, image: bool) -> dict[str, object]:
    identifier, separator, revision = value.partition(":")
    reference: dict[str, object] = {"id": identifier}
    if separator:
        if not revision:
            raise typer.BadParameter("a reference revision after ':' must not be empty")
        if image:
            reference["revision"] = revision
        else:
            try:
                reference["revision"] = int(revision)
            except ValueError:
                raise typer.BadParameter("an annotation revision after ':' must be a non-negative integer") from None
    return reference


@phenos_sessions_app.command("start", help="Start a scoped external execution session.")
def phenos_session_start(
    ctx: typer.Context,
    image: Annotated[str, typer.Option("--image", help="Image id, optionally followed by :revision.")],
    annotation: Annotated[
        list[str] | None,
        typer.Option("--annotation", help="Annotation id, repeat up to three times; optionally id:revision."),
    ] = None,
    client: Annotated[str, typer.Option("--client", help="Client label stored with the session.")] = "pws-cli",
    ttl: Annotated[int | None, typer.Option("--ttl", help="Session lifetime in seconds.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the session as JSON.")] = False,
) -> None:
    try:
        references = {
            "image": _external_reference(image, image=True),
            "annotations": [_external_reference(item, image=False) for item in annotation or []],
        }
    except typer.BadParameter as exc:
        usage_error(ctx.obj, exc.message, usage=SESSION_USAGE["start"], json_output=json_output)
    request: dict[str, object] = {"clientName": client, "references": references}
    if ttl is not None:
        request["ttlSeconds"] = ttl
    run_session_command(ctx.obj, "start", request=request, json_output=json_output)


@phenos_sessions_app.command("show", help="Read the active external session.")
def phenos_session_show(
    ctx: typer.Context,
    session_id: Annotated[str | None, typer.Option("--session", help="Use this stored external session.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the session as JSON.")] = False,
) -> None:
    run_session_command(ctx.obj, "show", session_id=session_id, json_output=json_output)


@phenos_sessions_app.command("end", help="Revoke the active external session.")
def phenos_session_end(
    ctx: typer.Context,
    session_id: Annotated[str | None, typer.Option("--session", help="Use this stored external session.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the revoked session as JSON.")] = False,
) -> None:
    run_session_command(ctx.obj, "end", session_id=session_id, json_output=json_output)


@phenos_execution_app.command(
    "wait",
    help="Wait until an execution succeeds, fails or is cancelled. Exit 0 on success, 6 on failure or cancel, "
    "7 when the deadline passes first (it may still be running).",
)
def phenos_execution_wait(
    ctx: typer.Context,
    execution: Annotated[str, typer.Argument(help="Execution id to wait for.")],
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            min=0,
            help="Seconds to wait, not a hard stop (the first check always runs and a check under way is not cut off); "
            "default is the rest of the stored session's lifetime.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the execution as JSON.")] = False,
    session_id: Annotated[str | None, typer.Option("--session", help="Use this stored external session.")] = None,
) -> None:
    run_wait_command(ctx.obj, execution, timeout=timeout, json_output=json_output, session_id=session_id)


ApprovalIdArg = Annotated[str, typer.Argument(help="Approval id, as the change or delete command printed it.")]
ApprovalJsonOption = Annotated[bool, typer.Option("--json", help="Print the approval as JSON.")]


@approvals_app.command(
    "wait",
    help="Wait until a person decides. Exit 0 when approved (run the same command again to use it), 10 when the time "
    "runs out first, 1 when it was rejected, expired, invalidated or cancelled.",
)
def approvals_wait(
    ctx: typer.Context,
    approval_id: ApprovalIdArg,
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            min=0,
            help="Seconds to wait, not a hard stop (the first check always runs and a check under way is not cut off); "
            "default is until the request expires.",
        ),
    ] = None,
    json_output: ApprovalJsonOption = False,
) -> None:
    run_approval_wait_command(ctx.obj, approval_id, timeout=timeout, json_output=json_output)


@approvals_app.command("show", help="Read one request and its state. Exit 0 whatever the state.")
def approvals_show(ctx: typer.Context, approval_id: ApprovalIdArg, json_output: ApprovalJsonOption = False) -> None:
    run_approval_read_command(ctx.obj, approval_id, json_output=json_output)


@approvals_app.command("list", help="List this login's requests that are still open.")
def approvals_list(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Print the requests as JSON.")] = False,
) -> None:
    run_approval_read_command(ctx.obj, None, json_output=json_output)


# ---------------------------------------------------------------------------
# read-only resources
# ---------------------------------------------------------------------------


@provisioning_app.command(
    "check",
    help=(
        "Check visible permissions for spot creation, agent creation, and device-key issuance. "
        "Exit 0 means all are allowed, 8 means at least one is denied, and 9 means none are denied "
        "but at least one is unknown. Results are advisory; Hub checks every write. "
        "Conditional grants are not evaluated."
    ),
)
def provisioning_check(ctx: typer.Context) -> None:
    """Report the selected Workspace's visible provisioning permissions."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        access_info = client.access_info()
        checks = check_provisioning(access_info)
        document = {"organization": client.config.org, "checks": checks}

        if context.mode is OutputMode.TABLE:
            table = Table(title=f"Provisioning permission check for {client.config.org}")
            table.add_column("Operation", style="bold")
            table.add_column("Result")
            table.add_column("Current role")
            table.add_column("Required permissions")
            for check in checks:
                groups = check["requiredPermissions"]
                required = " OR ".join(" AND ".join(group) for group in groups)
                table.add_row(check["operation"], check["result"], check["currentRole"] or "—", required)
            _console().print(table)
        else:
            emit_value(context, document)

        results = [check["result"] for check in checks]
        if any(result == "denied" for result in results):
            raise typer.Exit(code=EXIT_PROVISIONING_DENIED)
        if any(result == "unknown" for result in results):
            raise typer.Exit(code=EXIT_PROVISIONING_UNKNOWN)

    _run(context, action)


def _action_params(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("--params must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--params must be a JSON object")
    return parsed


def _emit_execution(context: CliContext, item: BaseModel) -> None:
    if context.mode is OutputMode.TABLE:
        root = getattr(item, "root", item)
        emit_one(context, root if isinstance(root, BaseModel) else item, columns=EXECUTION_COLUMNS)
    else:
        emit_value(context, item)


@actions_app.command("run")
def actions_run(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Discovered action name or id.")],
    spot: Annotated[str, typer.Option("--spot", help="Spot id or slug.")],
    params: Annotated[str, typer.Option("--params", help="JSON object of action parameters.")] = "{}",
    device: Annotated[str | None, typer.Option("--device", help="Device id or identifier.")] = None,
    component: Annotated[str | None, typer.Option("--component", help="Component id or identifier.")] = None,
    wait: Annotated[bool, typer.Option("--wait", help="Wait for a terminal execution status.")] = False,
) -> None:
    """Run a spot's action on its device, optionally waiting for the result."""

    context: CliContext = ctx.obj
    arguments = _action_params(params)

    def action(client: PWS) -> None:
        execution = client.spots.get(spot).actions.run(name, arguments, device=device, component=component, wait=wait)
        _emit_execution(context, execution.result if wait and execution.result is not None else execution.model)

    _run(context, action)


@actions_app.command("describe")
def actions_describe(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Discovered action name or id.")],
    spot: Annotated[str, typer.Option("--spot", help="Spot id or slug.")],
    device: Annotated[str | None, typer.Option("--device", help="Device id or identifier.")] = None,
    component: Annotated[str | None, typer.Option("--component", help="Component id or identifier.")] = None,
) -> None:
    """Show what an action accepts before running it: declared params schema, UI placement and the shortcut key.

    Read-only: it fetches the spot structure that `edge actions run` resolves against.
    """

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        described = describe_action(client.spots.get(spot).structure(), name, device=device, component=component)
        if context.mode is OutputMode.TABLE:
            table = Table(box=None, show_header=False)
            table.add_column("field", style="bold")
            table.add_column("value")
            for key, value in described.items():
                shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
                table.add_row(key, escape(shown))
            _console().print(table)
        else:
            emit_value(context, described)

    _run(context, action)


@actions_app.command("get")
def actions_get(ctx: typer.Context, execution: Annotated[str, typer.Argument(help="Execution id.")]) -> None:
    """Show one action execution and its status."""

    context: CliContext = ctx.obj
    _run(context, lambda client: _emit_execution(context, client.actions.get(execution)))


@actions_app.command("wait")
def actions_wait(
    ctx: typer.Context,
    execution: Annotated[str, typer.Argument(help="Execution id.")],
    timeout: Annotated[float | None, typer.Option("--timeout", min=0, help="Maximum wait in seconds.")] = None,
) -> None:
    """Wait until an action execution reaches a final status."""

    context: CliContext = ctx.obj
    _run(context, lambda client: _emit_execution(context, client.actions.wait(execution, timeout=timeout)))


@actions_app.command("executions")
def actions_executions(
    ctx: typer.Context,
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """List action executions of the Workspace, newest first."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        result = client.actions.list(page=page, limit=limit)
        if context.mode is OutputMode.TABLE:
            emit(context, result.items, columns=EXECUTION_LIST_COLUMNS)
        else:
            emit_value(context, result)

    _run(context, action)


@orgs_app.command("list")
def orgs_list(ctx: typer.Context) -> None:
    """List the Workspaces you belong to."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_listing(context, client.my_organizations(), columns=ORGANIZATION_COLUMNS, limit=None, page=None)

    _run(context, action)


@orgs_app.command("get")
def orgs_get(ctx: typer.Context, org: Annotated[str, typer.Argument(help="Workspace id or slug.")]) -> None:
    """Show one Workspace."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.organizations.get(org), columns=ORGANIZATION_COLUMNS)

    _run(context, action)


@spots_app.command("list")
def spots_list(
    ctx: typer.Context,
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """List the spots of the Workspace."""

    context = _listing_context(ctx, page=page, limit=limit)

    def action(client: PWS) -> None:
        result = client.spots.list(page=page, limit=limit)
        emit_listing(context, result, columns=SPOT_COLUMNS, limit=limit, page=page)

    _run(context, action)


@spots_app.command("get")
def spots_get(
    ctx: typer.Context, spot: Annotated[str, typer.Argument(help="Spot id or slug.", callback=_read_identifier)]
) -> None:
    """Show one spot."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.spots.get(spot).model, columns=SPOT_COLUMNS)

    _run(context, action)


@spots_app.command("create")
def spots_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Spot name.")],
    slug: Annotated[str, typer.Option("--slug", help="URL slug (lowercase letters, digits, hyphens).")],
    description: Annotated[str | None, typer.Option("--description")] = None,
) -> None:
    """Create a spot in the Workspace."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.spots.create(name, slug=slug, description=description), columns=SPOT_COLUMNS)

    _run(context, action, needs=NEEDS_SPOT_CREATE)


def _structure_document(structure: SpotStructure) -> dict[str, Any]:
    """The usual projection, except each action's free-form ``metadata`` holds only the keys the Hub sent.

    Its ``ui`` defaults would otherwise print as nulls the Hub never declared; explicit Hub nulls stay.
    """

    document = structure.model_dump(mode="json", by_alias=True)
    for device, dumped in zip(structure.devices, document["devices"], strict=True):
        pairs: list[tuple[SpotStructureDeviceAction | SpotStructureDeviceComponentAction, dict[str, Any]]]
        pairs = list(zip(device.actions, dumped["actions"], strict=True))
        for component, dumped_component in zip(device.components, dumped["components"], strict=True):
            pairs += zip(component.actions, dumped_component["actions"], strict=True)
        for action, out in pairs:
            if action.metadata is not None:
                out["metadata"] = action.metadata.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return document


@spots_app.command("structure")
def spots_structure(
    ctx: typer.Context, spot: Annotated[str, typer.Argument(help="Spot id or slug.", callback=_read_identifier)]
) -> None:
    """Show a spot's devices, components, actions and rules."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        structure = client.spots.get(spot).structure()
        if context.mode in (OutputMode.JSON, OutputMode.JSONL):
            typer.echo(render_json(_structure_document(structure)))
        else:
            emit_one(context, structure, columns=STRUCTURE_COLUMNS)

    _run(context, action)


@devices_app.command("list")
def devices_list(
    ctx: typer.Context,
    spot: Annotated[str, typer.Option("--spot", help="Spot id.", callback=_read_identifier)],
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """List the devices of a spot."""

    context = _listing_context(ctx, page=page, limit=limit)

    def action(client: PWS) -> None:
        result = client.devices.list(spot, page=page, limit=limit)
        emit_listing(context, result, columns=DEVICE_COLUMNS, limit=limit, page=page)

    _run(context, action)


@devices_app.command("get")
def devices_get(
    ctx: typer.Context, device: Annotated[str, typer.Argument(help="Device id.", callback=_read_identifier)]
) -> None:
    """Show one device."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.devices.get(device), columns=DEVICE_COLUMNS)

    _run(context, action)


@devices_app.command("status")
def devices_status(
    ctx: typer.Context, device: Annotated[str, typer.Argument(help="Device id.", callback=_read_identifier)]
) -> None:
    """Show a device's current status and the actions and topics it reports."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.devices.status(device), columns=DEVICE_STATUS_COLUMNS)

    _run(context, action)


# ---------------------------------------------------------------------------
# agent device keys: the secret goes to a 0600 file, never to stdout/stderr
# ---------------------------------------------------------------------------

AgentOption = Annotated[str, typer.Option("--agent", help="Agent id (`pws edge agents list` lists them).")]
KeyArg = Annotated[str, typer.Argument(help="Access key id.")]
OutOption = Annotated[
    Path | None,
    typer.Option("--out", help="File for the secret (default: keys/<agent id>.key next to the credentials file)."),
]
ForceOption = Annotated[bool, typer.Option("--force", help="Replace an existing key file.")]
ExpiresOption = Annotated[
    str | None, typer.Option("--expires-at", help="Expiry, ISO 8601 UTC (e.g. 2027-01-01T00:00:00Z).")
]


@dataclass(frozen=True, slots=True)
class _KeyFile:
    """A 0600 temporary file reserved beside the target before the Hub acts."""

    target: Path
    temporary: Path
    descriptor: int
    force: bool


def _key_file(agent_id: str, out: Path | None, *, force: bool) -> _KeyFile:
    """Reserve the secret's file before any Hub call, so a rotate never kills the old key and then cannot save the new one.

    ``mkstemp`` creates the temporary file with ``O_EXCL`` and mode 0600, which also proves the directory is writable.
    """

    target = out if out is not None else credentials_path().parent / "keys" / f"{agent_id}.key"
    if target.is_dir():
        message = f"{target} is a directory; pass --out with a file path"
    elif not force and (target.exists() or target.is_symlink()):
        message = f"{target} already exists; pass --force to replace it or --out to choose another file"
    else:
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        except OSError as exc:
            message = f"cannot create a key file in {target.parent}: {exc.strerror or exc}"
        else:
            return _KeyFile(target, Path(temporary), descriptor, force)
    _console(stderr=True).print(f"[red]error:[/red] {escape(message)}", highlight=False, soft_wrap=True)
    raise typer.Exit(code=EXIT_USAGE)


def _publish(key_file: _KeyFile, secret: SecretStr, agent_id: str, key_id: object) -> None:
    """Write, fsync, then publish without clobbering (``--force`` replaces).

    A failed write may leave a partial key, so that file is deleted and the user is told how to fetch the key again;
    only a fully written file that cannot be published is kept (0600) as the recovery copy.
    """

    try:
        with os.fdopen(key_file.descriptor, "w", encoding="utf-8") as stream:
            stream.write(secret.get_secret_value())
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        cleanup_status = f"the incomplete file may remain at {key_file.temporary}"
        with contextlib.suppress(OSError):
            key_file.temporary.unlink(missing_ok=True)
            cleanup_status = "the incomplete file was deleted"
        message = (
            f"the Hub returned key {key_id} (a rotated key's predecessor no longer works) but writing it to "
            f"{key_file.target.parent} failed ({exc.strerror or exc}); {cleanup_status}, and the key "
            f"is NOT saved. Free space, then run `pws edge agents keys download {key_id} --agent {agent_id} "
            f"--out {shlex.quote(str(key_file.target))}` if the key is recoverable, or rotate it"
        )
        _console(stderr=True).print(f"[red]error:[/red] {escape(message)}", highlight=False, soft_wrap=True)
        raise typer.Exit(code=EXIT_ERROR) from None
    try:
        if key_file.force:
            os.replace(key_file.temporary, key_file.target)
        else:
            os.link(key_file.temporary, key_file.target)
            key_file.temporary.unlink()
    except OSError as exc:
        message = (
            f"the Hub issued the key but it could not be saved to {key_file.target} ({exc.strerror or exc}); "
            f"it is in {key_file.temporary} (mode 0600): move it into place"
        )
        _console(stderr=True).print(f"[red]error:[/red] {escape(message)}", highlight=False, soft_wrap=True)
        raise typer.Exit(code=EXIT_ERROR) from None


def _run_secret(
    context: CliContext,
    agent_id: str,
    out: Path | None,
    force: bool,
    fetch: Callable[[PWS], tuple[Mapping[str, object], SecretStr]],
) -> None:
    key_file = _key_file(agent_id, out, force=force)
    received = False

    def action(client: PWS) -> None:
        nonlocal received
        metadata, secret = fetch(client)
        received = True
        _publish(key_file, secret, agent_id, metadata.get("id"))
        emit_value(context, {**metadata, "keyFile": str(key_file.target)})
        typer.echo(f"wrote the key to {key_file.target} (mode 0600)", err=True)

    try:
        _run(context, action, needs=NEEDS_AGENT_KEYS)
    finally:
        if not received:  # no secret arrived: the reserved file is empty
            os.close(key_file.descriptor)
            key_file.temporary.unlink(missing_ok=True)


def _issued_metadata(issued: IssuedAccessKey) -> tuple[Mapping[str, object], SecretStr]:
    return issued.key.model_dump(mode="json", by_alias=True), issued.secret


@agents_app.command("list")
def agents_list(
    ctx: typer.Context,
    spot: Annotated[str | None, typer.Option("--spot", help="Only this spot's agents (spot id).")] = None,
    identifier: Annotated[
        str | None, typer.Option("--identifier", help="Only the agent with exactly this identifier.")
    ] = None,
) -> None:
    """List every agent of the Workspace (all pages)."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        agents = client.agents.list(spot=spot)
        if identifier is not None:  # the Hub's `search` matches substrings; an identifier must match whole
            agents = [agent for agent in agents if _field("identifier")(agent) == identifier]
        emit(context, agents, columns=AGENT_LIST_COLUMNS)

    _run(context, action)


@agents_app.command("create")
def agents_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Agent name.")],
    identifier: Annotated[str, typer.Option("--identifier", help="Agent identifier, unique in the Workspace.")],
    spot: Annotated[str, typer.Option("--spot", help="Spot id.")],
) -> None:
    """Create a device agent in a spot; issue its key with `pws edge agents keys issue`."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.agents.create(name, identifier=identifier, spot=spot), columns=AGENT_COLUMNS)

    _run(context, action, needs=NEEDS_AGENT_CREATE)


@keys_app.command("list")
def keys_list(ctx: typer.Context, agent: AgentOption) -> None:
    """List key metadata (never the secret)."""

    context: CliContext = ctx.obj
    _run(context, lambda client: emit(context, client.access_keys.list(agent), columns=ACCESS_KEY_COLUMNS))


@keys_app.command("issue")
def keys_issue(
    ctx: typer.Context,
    agent: AgentOption,
    name: Annotated[str, typer.Option("--name", help="Key name.")],
    description: Annotated[str | None, typer.Option("--description")] = None,
    expires_at: ExpiresOption = None,
    out: OutOption = None,
    force: ForceOption = False,
) -> None:
    """Issue a new device key and write it to a 0600 file."""

    _run_secret(
        ctx.obj,
        agent,
        out,
        force,
        lambda client: _issued_metadata(
            client.access_keys.issue(agent, name, description=description, expires_at=expires_at)
        ),
    )


@keys_app.command("rotate")
def keys_rotate(
    ctx: typer.Context,
    agent: AgentOption,
    key: KeyArg,
    expires_at: ExpiresOption = None,
    out: OutOption = None,
    force: ForceOption = False,
) -> None:
    """Replace an active key: the old key and its sessions stop working at once."""

    _run_secret(
        ctx.obj,
        agent,
        out,
        force,
        lambda client: _issued_metadata(client.access_keys.rotate(agent, key, expires_at=expires_at)),
    )


@keys_app.command("reissue")
def keys_reissue(
    ctx: typer.Context,
    agent: AgentOption,
    key: KeyArg,
    expires_at: ExpiresOption = None,
    out: OutOption = None,
    force: ForceOption = False,
) -> None:
    """Issue a replacement for a revoked or expired key."""

    _run_secret(
        ctx.obj,
        agent,
        out,
        force,
        lambda client: _issued_metadata(client.access_keys.reissue(agent, key, expires_at=expires_at)),
    )


@keys_app.command("download")
def keys_download(
    ctx: typer.Context, agent: AgentOption, key: KeyArg, out: OutOption = None, force: ForceOption = False
) -> None:
    """Write a recoverable key's secret to a 0600 file again."""

    def fetch(client: PWS) -> tuple[Mapping[str, object], SecretStr]:
        secret = client.access_keys.plain_key(agent, key)
        if secret is None:
            raise TransportError(f"key {key} has no recoverable copy; rotate or reissue it")
        return {"id": key}, secret

    _run_secret(ctx.obj, agent, out, force, fetch)


@keys_app.command("revoke")
def keys_revoke(
    ctx: typer.Context,
    agent: AgentOption,
    key: KeyArg,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Revoke a key: devices using it stop authenticating."""

    context: CliContext = ctx.obj
    if not yes:
        # typer>=0.26 (vendored click) writes the prompt's last character to stdout via input(); keep stdout for results.
        with contextlib.redirect_stdout(sys.stderr):
            typer.confirm(
                f"Revoke key {key} of agent {agent}? Devices using it stop authenticating.", abort=True, err=True
            )

    def action(client: PWS) -> None:
        client.access_keys.revoke(agent, key)
        emit_value(context, {"id": key, "revoked": True})

    _run(context, action, needs=NEEDS_AGENT_KEYS)


# ---------------------------------------------------------------------------
# telemetry
# ---------------------------------------------------------------------------


def _topic_ids(value: str) -> tuple[str, ...]:
    topics = tuple(item.strip() for item in value.split(",") if item.strip())
    if not topics:
        raise typer.BadParameter("pass at least one topic id")
    return topics


@telemetry_app.command("topics")
def telemetry_topics(ctx: typer.Context, device: Annotated[str, typer.Option("--device", help="Device id.")]) -> None:
    """List the telemetry topics a device reports."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_value(context, client.telemetry.topics(device))

    _run(context, action)


@telemetry_app.command("query")
def telemetry_query(
    ctx: typer.Context,
    device: Annotated[str, typer.Option("--device", help="Device id.")],
    topic: Annotated[str, typer.Option("--topic", help="Topic id.")],
    since: Annotated[str, typer.Option("--since", help='Window such as "7d" or an ISO timestamp.')],
    step: Annotated[str | None, typer.Option("--step", help='Aggregation step such as "1m" or "1h".')] = None,
) -> None:
    """Read one topic's time series over a window."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_value(context, client.telemetry.query(device, topic, since, step=step))

    _run(context, action)


@telemetry_app.command("export")
def telemetry_export(
    ctx: typer.Context,
    device: Annotated[str, typer.Option("--device", help="Device id.")],
    topics: Annotated[str, typer.Option("--topics", help="Comma-separated topic ids.")],
    since: Annotated[str, typer.Option("--since", help='Window such as "7d" or an ISO timestamp.')],
    dest: Annotated[Path, typer.Option("--dest", help="Target CSV path.", dir_okay=False)] = Path("telemetry.csv"),
    aggregation: Annotated[str, typer.Option("--aggregation", help="rollup or raw.")] = "rollup",
    sample_interval: Annotated[str, typer.Option("--sample-interval", help='Sensor interval such as "15s".')] = "15s",
) -> None:
    """Save the time series of one or more topics to a CSV file."""

    context: CliContext = ctx.obj
    topic_ids = _topic_ids(topics)

    def action(client: PWS) -> None:
        path = client.telemetry.export(
            device,
            topic_ids,
            since,
            dest,
            aggregation=aggregation,
            sample_interval=sample_interval,
        )
        _emit_downloads(context, [{"id": device, "path": str(path), "bytes": path.stat().st_size}])

    _run(context, action)


@components_app.command("list")
def components_list(
    ctx: typer.Context,
    device: Annotated[str, typer.Option("--device", help="Device id.", callback=_read_identifier)],
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """List the components of a device."""

    context = _listing_context(ctx, page=page, limit=limit)

    def action(client: PWS) -> None:
        result = client.components.list(device, page=page, limit=limit)
        emit_listing(context, result, columns=COMPONENT_COLUMNS, limit=limit, page=page)

    _run(context, action)


@rules_app.command("list")
def rules_list(
    ctx: typer.Context,
    spot: Annotated[str, typer.Option("--spot", help="Spot id or slug.", callback=_read_identifier)],
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """List the rules of a spot."""

    context = _listing_context(ctx, page=page, limit=limit)

    def action(client: PWS) -> None:
        result = client.spots.get(spot).rules.list(page=page, limit=limit)
        emit_listing(context, result, columns=RULE_COLUMNS, limit=limit, page=page)

    _run(context, action)


@rules_app.command("get")
def rules_get(
    ctx: typer.Context,
    rule: Annotated[str, typer.Argument(help="Rule id.", callback=_read_identifier)],
    spot: Annotated[str, typer.Option("--spot", help="Spot id or slug.", callback=_read_identifier)],
) -> None:
    """Show one rule of a spot."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.spots.get(spot).rules.get(rule), columns=RULE_COLUMNS)

    _run(context, action)


@rules_app.command("executions")
def rules_executions(
    ctx: typer.Context,
    rule: Annotated[str, typer.Argument(help="Rule id.", callback=_read_identifier)],
    spot: Annotated[str, typer.Option("--spot", help="Spot id or slug.", callback=_read_identifier)],
) -> None:
    """Show the ten most recent executions for a rule in a spot."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        result = client.spots.get(spot).rules.executions(rule)
        emit(context, result, columns=RULE_EXECUTION_COLUMNS)

    _run(context, action)


# ---------------------------------------------------------------------------
# local configuration
# ---------------------------------------------------------------------------


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show effective non-secret command inputs without opening a network connection."""

    context: CliContext = ctx.obj
    try:
        config = Config.resolve(
            base_url=context.base_url,
            org=context.org,
            profile=context.profile,
            require_credential=False,
        )
    except PWSError as exc:
        raise typer.Exit(code=_report(exc)) from exc
    settings = {
        "base_url": config.base_url,
        "org": config.org,
        "profile": config.profile,
    }
    if context.mode is OutputMode.TABLE:
        table = Table(box=None, show_header=False)
        table.add_column("field", style="bold")
        table.add_column("value")
        for key, value in settings.items():
            table.add_row(key, "" if value is None else value)
        _console().print(table)
    elif context.mode is not OutputMode.QUIET:
        typer.echo(render_json(settings))


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def _resolve_auth_option(
    ctx: typer.Context,
    option: str,
    command_value: str | None,
    root_value: str | None,
) -> str | None:
    root_context = ctx.find_root()
    root_source = root_context.get_parameter_source(option.replace("-", "_"))
    if (
        command_value is not None
        and getattr(root_source, "name", None) == "COMMANDLINE"
        and command_value != root_value
    ):
        command = ctx.info_name or "auth command"
        raise typer.BadParameter(
            f"conflicting values for root --{option} {root_value!r} and auth {command} --{option} {command_value!r}"
        )
    return command_value if command_value is not None else root_value


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    api_key_file: Annotated[
        str | None,
        typer.Option(
            "--api-key-file",
            metavar="PATH",
            help="File holding a device-plane agent key (agents/* routes only), mode 0600; `-` reads standard input.",
        ),
    ] = None,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Print the approval URL and code without opening a browser.")
    ] = False,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            help=(
                "Hub API base URL; if omitted, uses root --base-url, PWS_BASE_URL, then the production Hub. "
                "If repeated at the root, values must match."
            ),
        ),
    ] = None,
    org: Annotated[str | None, typer.Option("--org")] = None,
) -> None:
    """Sign in and store this device's session with mode 0600.

    By default this runs device login: approve the printed code in a browser
    (opened for you when one is available); the CLI stores only this device's
    session, never a password.  ``--api-key-file`` stores a device-plane key
    read from a 0600 file or standard input, never from the command line.
    Either replaces the whole profile, including a session left by the
    retired ``--password-login``.
    """

    context: CliContext = ctx.obj
    resolved_profile = _resolve_auth_option(ctx, "profile", profile, context.profile)
    profile = resolved_profile if resolved_profile is not None else "default"
    base_url = _resolve_auth_option(ctx, "base-url", base_url, context.base_url)
    org = _resolve_auth_option(ctx, "org", org, context.org)
    api_key: str | None = None
    if api_key_file is not None:
        try:
            api_key = read_agent_key_file(sys.stdin if api_key_file == "-" else Path(api_key_file))
        except (OSError, ValueError) as exc:
            # An OS error gives only its reason, not the argument: a key pasted in place of the path is never echoed.
            reason = getattr(exc, "strerror", None) or str(exc)
            raise typer.BadParameter(reason, param_hint="--api-key-file") from None

    path = credentials_path()
    hub = normalize_hub_url(base_url or os.getenv("PWS_BASE_URL") or DEFAULT_BASE_URL)
    if api_key is not None:
        try:
            require_secure_hub(hub)  # before the old session is retired or the profile replaced
        except PWSError as exc:
            raise typer.Exit(code=_report(exc)) from exc
        _retire_device_session(path, profile)
        # A stored key is bound to the Hub it was stored for, as a device session is.
        Config.write_credentials(path, api_key=api_key, profile=profile, base_url=hub, org=org)
        typer.echo(render_json({"profile": profile, "credentials_file": str(path), "credential": "api_key"}))
        return
    device_token = _device_login(hub, open_browser=not no_browser)
    _retire_device_session(path, profile)
    # The session is bound to the Hub that issued it: always record that Hub.
    Config.write_credentials(path, device_session_token=device_token, profile=profile, base_url=hub, org=org)
    typer.echo(render_json({"profile": profile, "credentials_file": str(path), "credential": "device_session"}))


def _device_login(hub: str, *, open_browser: bool) -> str:
    """Run the device grant, prove the session by exchanging it once, and return the raw session token."""

    exit_code: int | None = None
    token = ""
    try:
        require_secure_hub(hub)
    except PWSError as exc:
        exit_code = _report(exc)
    if exit_code is not None:
        raise typer.Exit(code=exit_code)
    transport = Transport(hub)
    try:
        token = _run_device_grant(transport, open_browser=open_browser)
    except PWSError as exc:
        exit_code = _report(exc)
    finally:
        transport.close()
    # Raised outside the handler so no exception context outlives this call.
    if exit_code is not None:
        raise typer.Exit(code=exit_code)
    return token


def _run_device_grant(transport: Transport, *, open_browser: bool) -> str:
    login = DeviceLogin(transport)
    code = login.start()
    typer.echo(f"To sign in, open {code.verification_uri} and enter the code {code.user_code}", err=True)
    if code.verification_uri_complete:
        typer.echo(f"or open {code.verification_uri_complete}", err=True)
    typer.echo("Approve only if you started this login yourself.", err=True)
    if open_browser and _gui_browser_available():
        try:
            webbrowser.open(code.verification_uri_complete or code.verification_uri)
        except webbrowser.Error:
            pass
    typer.echo("Waiting for approval in the browser...", err=True)
    credential = login.wait(code)
    credential.refresh(transport)
    return credential.session_token


_CONSOLE_BROWSERS = frozenset({"lynx", "w3m", "links", "elinks", "www-browser", "browsh", "links2"})


def _gui_browser_available() -> bool:
    """Open a browser only in a graphical session, and never a console browser that would take over the terminal."""

    if os.getenv("CI") or os.getenv("SSH_CONNECTION") or os.getenv("SSH_TTY"):
        return False
    if sys.platform.startswith("linux") and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        return False
    try:
        controller = webbrowser.get()
    except webbrowser.Error:
        return False
    name = os.path.basename(str(getattr(controller, "name", "") or ""))
    # Console browsers are registered as foreground GenericBrowser; GUI ones as BackgroundBrowser or subclasses.
    return name not in _CONSOLE_BROWSERS and type(controller) is not webbrowser.GenericBrowser


def _retire_device_session(path: Path, profile: str) -> None:
    """Best effort: revoke the device session a re-login in this profile is about to replace."""

    values = _read_profile(path, profile)
    old_token = values.get("device_session_token")
    old_hub = values.get("base_url")
    if not (isinstance(old_token, str) and old_token and isinstance(old_hub, str) and old_hub):
        return
    outcome = "failed"
    try:
        transport = Transport(require_secure_hub(normalize_hub_url(old_hub)))
        try:
            outcome = revoke_device_session(transport, old_token)
        finally:
            transport.close()
    except (PWSError, ValueError):  # ValueError: a stored token that is not header-safe; its message omits the value
        outcome = "failed"
    if outcome == "failed":
        typer.echo(
            "could not revoke the previous device session of this profile; revoke it from your devices page",
            err=True,
        )
    else:
        typer.echo("revoked the previous device session of this profile", err=True)


@auth_app.command("logout")
def auth_logout(ctx: typer.Context, profile: Annotated[str | None, typer.Option("--profile")] = None) -> None:
    """Revoke this device's session on the Hub (no other device) and delete the local credential.

    Safe to repeat.  A session the Hub no longer knows (revoked elsewhere or
    expired) still has its local credential removed; if the Hub cannot be
    reached the local credential is kept so the command can be retried.  The
    session is only ever sent to the Hub that issued it.
    """

    context: CliContext = ctx.obj
    resolved_profile = _resolve_auth_option(ctx, "profile", profile, context.profile)
    profile = resolved_profile if resolved_profile is not None else "default"

    path = credentials_path()
    values = _read_profile(path, profile)
    device_token = values.get("device_session_token")
    server_session = "not_applicable"
    exit_code: int | None = None
    if isinstance(device_token, str) and device_token:
        hub: str | None = None
        try:
            hub = device_hub(values, context.base_url or os.getenv("PWS_BASE_URL"))
        except PWSError as exc:
            if not values.get("base_url"):
                typer.echo(
                    "this device session has no recorded Hub, so it was not revoked there; "
                    "revoke it from your devices page",
                    err=True,
                )
                server_session = "not_revoked"
            else:
                typer.echo("the local credential was kept", err=True)
                exit_code = _report(exc)
        if hub is not None:
            transport = Transport(hub)
            try:
                server_session = revoke_device_session(transport, device_token)
            except ValueError:
                # A stored token that is not header-safe cannot be a live session: nothing to revoke, so the
                # local credential goes. The message omits the value, and nothing keeps the exception.
                typer.echo(
                    "the stored device session token is malformed, so it was not revoked on the Hub; "
                    "removing the local credential",
                    err=True,
                )
                server_session = "not_revoked"
            except PWSError as exc:
                typer.echo("the local credential was kept; run `pws auth logout` again to retry", err=True)
                exit_code = _report(exc)
            finally:
                transport.close()
        if exit_code is not None:
            raise typer.Exit(code=exit_code)
        if server_session == "already_revoked":
            typer.echo("the Hub had already ended this device session; removing the local credential", err=True)
    removed = Config.delete_credentials(path, profile=profile)
    typer.echo(
        render_json(
            {
                "profile": profile,
                "credentials_file": str(path),
                "server_session": server_session,
                "local_credential": "removed" if removed else "absent",
            }
        )
    )


@auth_app.command("whoami")
def auth_whoami(ctx: typer.Context) -> None:
    """Show the signed-in user, the Hub and profile in use, and every Workspace they belong to (id, slug, role)."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        me = client.me()
        if context.mode is OutputMode.JSON:
            expires = me.token_expires_at
            document = {
                "user": {"id": me.user_id, "email": me.email},
                "base_url": client.config.base_url,
                "profile": client.config.profile,
                "org": client.config.org,
                "token_expires_at": expires.isoformat(timespec="seconds") if expires is not None else None,
                "organizations": me.organizations,
            }
            typer.echo(render_json(document))
            return
        if context.mode is OutputMode.TABLE:
            typer.echo(f"user  {me.user_id}  {me.email or ''}".rstrip())
            typer.echo(f"hub  {client.config.base_url}  profile  {client.config.profile}")
        emit(context, me.organizations, columns=USER_ORGANIZATION_COLUMNS)
        if not me.organizations:
            typer.echo("no Workspaces yet; ask a Workspace owner to invite you", err=True)

    _run(context, action)


@app.command("doctor")
def doctor(ctx: typer.Context) -> None:
    """Check the configured credential of the root --profile without issuing an API request."""

    context: CliContext = ctx.obj
    path = credentials_path()
    try:
        config = Config.resolve(
            base_url=context.base_url, org=context.org, profile=context.profile, credentials_file=path
        )
    except PWSError as exc:
        raise typer.Exit(code=_report(exc)) from exc
    except (OSError, ValueError) as exc:  # an unreadable or malformed credentials file (tomllib errors are ValueError)
        message = f"cannot read the credentials file {path}: {exc}"
        _console(stderr=True).print(f"[red]error:[/red] {escape(message)}", highlight=False, soft_wrap=True)
        raise typer.Exit(code=EXIT_AUTH) from exc
    credential = config.credential_kind
    typer.echo(
        render_json(
            {"profile": config.profile, "base_url": config.base_url, "org": config.org, "credential": credential}
        )
    )


# ---------------------------------------------------------------------------
# captures
# ---------------------------------------------------------------------------


@captures_app.command("list")
def captures_list(
    ctx: typer.Context,
    spot: Annotated[str | None, typer.Option("--spot", help="Spot id.")] = None,
    device: Annotated[str | None, typer.Option("--device", help="Device id.")] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="PLANNED|IN_PROGRESS|COMPLETED|FAILED|CANCELLED")
    ] = None,
    since: Annotated[
        str | None, typer.Option("--since", help='Window such as "30d", "12h", or an ISO timestamp.')
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
) -> None:
    """List captures, optionally by spot, device, status or time window."""

    context = _listing_context(ctx, page=page, limit=limit)

    def action(client: PWS) -> None:
        result = client.captures.list(spot=spot, device=device, status=status, since=since, limit=limit, page=page)
        emit_listing(context, result, columns=CAPTURE_COLUMNS, limit=limit, page=page)

    _run(context, action)


@captures_app.command("get")
def captures_get(ctx: typer.Context, capture: Annotated[str, typer.Argument(help="Capture id.")]) -> None:
    """Show one capture."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.captures.get(capture).model, columns=CAPTURE_COLUMNS)

    _run(context, action)


@captures_app.command("latest")
def captures_latest(
    ctx: typer.Context,
    spot: Annotated[str | None, typer.Option("--spot", help="Spot id.")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
) -> None:
    """Show the most recent capture, optionally of one spot."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        handle = client.captures.latest(spot=spot, status=status)
        if handle is None:
            raise NotFoundError("no capture matches", status_code=404)
        emit_one(context, handle.model, columns=CAPTURE_COLUMNS)

    _run(context, action)


# ---------------------------------------------------------------------------
# media
# ---------------------------------------------------------------------------


@media_app.command("list")
def media_list(
    ctx: typer.Context,
    capture: Annotated[str | None, typer.Option("--capture", help="Capture id.")] = None,
    spot: Annotated[str | None, typer.Option("--spot", help="Spot id.")] = None,
    device: Annotated[str | None, typer.Option("--device", help="Device id.")] = None,
    modality: Annotated[str | None, typer.Option("--modality", help="RGB|THERMAL|FLUORESCENCE|NIR")] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
) -> None:
    """List media assets, optionally of one capture, spot, device or modality."""

    context = _listing_context(ctx, page=page, limit=limit)

    def action(client: PWS) -> None:
        result = client.media.list(capture=capture, spot=spot, device=device, modality=modality, limit=limit, page=page)
        emit_listing(context, result, columns=MEDIA_COLUMNS, limit=limit, page=page)

    _run(context, action)


@media_app.command("get")
def media_get(ctx: typer.Context, asset: Annotated[str, typer.Argument(help="Media asset id.")]) -> None:
    """Show one media asset."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        emit_one(context, client.media.get(asset), columns=MEDIA_COLUMNS)

    _run(context, action)


@media_app.command("upload")
def media_upload(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)],
    thumbnail: Annotated[Path, typer.Option("--thumbnail", exists=True, file_okay=True, dir_okay=False, readable=True)],
    capture: Annotated[str, typer.Option("--capture", help="Capture id.")],
    width: Annotated[int, typer.Option("--width", min=1)],
    height: Annotated[int, typer.Option("--height", min=1)],
    modality: Annotated[str, typer.Option("--modality")] = "RGB",
    spot: Annotated[str | None, typer.Option("--spot")] = None,
    device: Annotated[str | None, typer.Option("--device")] = None,
) -> None:
    """Upload an image and thumbnail, then finalize the media asset."""

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        result = client.media.upload(
            file,
            thumbnail=thumbnail,
            capture=capture,
            width=width,
            height=height,
            modality=modality,
            spot=spot,
            device=device,
        )
        if context.mode in (OutputMode.QUIET, OutputMode.TABLE):
            typer.echo(result.media_asset_id)
        else:
            emit_value(context, result)

    _run(context, action)


@media_app.command("download")
def media_download(
    ctx: typer.Context,
    asset: Annotated[list[str] | None, typer.Argument(help="Media asset ids (omit with --capture).")] = None,
    capture: Annotated[str | None, typer.Option("--capture", help="Download every asset of a capture.")] = None,
    dest: Annotated[
        Path, typer.Option("--dest", help="Target directory; created when missing.", file_okay=False)
    ] = Path("."),
) -> None:
    """Download assets; prints ``{"id","path","bytes"}`` per asset under --json/--jsonl, paths under -q."""

    context: CliContext = ctx.obj
    if not asset and capture is None:
        raise typer.BadParameter("pass at least one asset id or --capture")

    def action(client: PWS) -> None:
        directory = _prepare_download_directory(dest)
        targets: list[str] = list(asset or [])
        if capture is not None:
            targets.extend(item.id for item in client.captures.get(capture).media)
        results = [_download_one(client, context, identifier, directory) for identifier in targets]
        _emit_downloads(context, results)

    _run(context, action)


@media_app.command("upload-array")
def media_upload_array(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)],
    modality: Annotated[str, typer.Option("--modality", help="Array modality, e.g. DEPTH.")],
    capture: Annotated[str, typer.Option("--capture", help="Capture id.")],
    unit: Annotated[str | None, typer.Option("--unit", help="Physical distance unit (m or mm).")] = None,
    scale: Annotated[float | None, typer.Option("--scale", help="Physical = raw * scale + offset.")] = None,
    offset: Annotated[float | None, typer.Option("--offset")] = None,
    no_data: Annotated[float | None, typer.Option("--no-data", help="Raw no-data value.")] = None,
    display_range: Annotated[
        tuple[float, float] | None, typer.Option("--display-range", help="Physical min max.")
    ] = None,
    colormap: Annotated[str | None, typer.Option("--colormap")] = None,
    intrinsics: Annotated[str | None, typer.Option("--intrinsics", help="Camera intrinsics JSON object.")] = None,
    source_sensor: Annotated[str | None, typer.Option("--source-sensor")] = None,
) -> None:
    """Upload a 2D NumPy array as one modality of an existing capture.

    Hub decides which modalities accept arrays; the modality must be enabled on Hub before this works.
    """

    if file.suffix.lower() != ".npy":
        raise typer.BadParameter("FILE must be a .npy array")
    try:
        import numpy as np
    except ImportError as exc:
        raise typer.BadParameter("array uploads require the phytoworks[zarr] extra") from exc
    camera: dict[str, float] | None = None
    if intrinsics is not None:
        try:
            parsed = json.loads(intrinsics)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter("--intrinsics must be a JSON object") from exc
        if not isinstance(parsed, dict):
            raise typer.BadParameter("--intrinsics must be a JSON object")
        if not all(
            isinstance(key, str) and isinstance(value, int | float) and not isinstance(value, bool)
            for key, value in parsed.items()
        ):
            raise typer.BadParameter("--intrinsics values must be numbers")
        camera = {key: float(value) for key, value in parsed.items()}
    try:
        array = np.load(file, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError, EOFError) as exc:
        raise typer.BadParameter("FILE must be a readable .npy array") from exc

    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        result = client.media.upload_array(
            modality,
            array,
            capture=capture,
            unit=unit,
            scale=scale,
            offset=offset,
            no_data=no_data,
            display_range=display_range,
            colormap=colormap,
            intrinsics=camera,
            source_sensor=source_sensor,
        )
        if context.mode in (OutputMode.QUIET, OutputMode.TABLE):
            typer.echo(result.media_asset_id)
        else:
            emit_value(context, {"mediaAssetId": result.media_asset_id})

    _run(context, action)


@media_app.command("download-array")
def media_download_array(
    ctx: typer.Context,
    asset: Annotated[str, typer.Argument(help="Array media asset id.")],
    dest: Annotated[Path, typer.Option("--dest", help="Target .npy file.", file_okay=True, dir_okay=False)],
) -> None:
    """Download an array asset as a .npy file and emit its stored descriptor.

    The asset's modality picks the reader; the modality must be enabled on Hub before this works (today DEPTH).
    """

    if dest.suffix.lower() != ".npy":
        raise typer.BadParameter("--dest must name a .npy file")
    try:
        import numpy as np
    except ImportError as exc:
        raise typer.BadParameter("array downloads require the phytoworks[zarr] extra") from exc
    context: CliContext = ctx.obj

    def action(client: PWS) -> None:
        modality = _field("modality")(client.media.get(asset))
        if modality != "DEPTH":
            raise typer.BadParameter(f"no array reader for {modality or 'unknown'} media; only DEPTH is supported")
        array, descriptor = client.media.download_depth(asset)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with atomic_binary_writer(dest) as target:
            np.save(target, array, allow_pickle=False)
        _emit_downloads(
            context,
            [{"id": asset, "path": str(dest), "bytes": dest.stat().st_size, "descriptor": descriptor}],
        )

    _run(context, action)


def _download_one(client: PWS, context: CliContext, identifier: str, dest: Path) -> dict[str, object]:
    progress = _progress(context, identifier)
    if progress is None:
        path = client.media.download(identifier, dest)
    else:
        with progress:
            task = progress.add_task("download", total=None)

            def on_progress(done: int, total: int | None) -> None:
                progress.update(task, completed=done, total=total)

            path = client.media.download(identifier, dest, on_progress=on_progress)
    size = (
        sum(file.stat().st_size for file in path.rglob("*") if file.is_file()) if path.is_dir() else path.stat().st_size
    )
    return {"id": identifier, "path": str(path), "bytes": size}


def _emit_downloads(context: CliContext, results: Iterable[dict[str, object]]) -> None:
    rows = list(results)
    if context.mode is OutputMode.QUIET:
        for row in rows:
            typer.echo(str(row["path"]))
    elif context.mode is OutputMode.JSONL:
        for row in rows:
            typer.echo(render_json(row))
    elif context.mode is OutputMode.JSON:
        typer.echo(render_json({"items": rows}))
    else:
        for row in rows:
            _console(stderr=True).print(f"saved {row['path']} ({row['bytes']} bytes)", highlight=False)
            typer.echo(str(row["path"]))


def main() -> None:
    app()
