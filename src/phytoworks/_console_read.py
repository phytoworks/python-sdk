"""Read-only, explicitly scoped subset of the ``pws`` CLI for console skills."""

from __future__ import annotations

import os
from typing import Annotated, NoReturn

import typer

from . import cli
from .cli import EXIT_USAGE, CliContext, OutputMode
from .config import Config
from .errors import PWSError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Read-only PWS Console queries.",
    pretty_exceptions_show_locals=False,
)
auth_app = typer.Typer(no_args_is_help=True, help="Current identity.")
config_app = typer.Typer(no_args_is_help=True, help="Effective non-secret settings.")
edge_app = typer.Typer(
    no_args_is_help=True,
    help="Sites and equipment: spots, devices, components, rules.",
)
spots_app = typer.Typer(no_args_is_help=True, help="Spots and discovered structure.")
devices_app = typer.Typer(no_args_is_help=True, help="Devices and current status.")
components_app = typer.Typer(no_args_is_help=True, help="Components.")
rules_app = typer.Typer(no_args_is_help=True, help="Rules and their latest executions.")


def _usage_error(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=EXIT_USAGE)


@app.callback()
def root_options(
    ctx: typer.Context,
    profile: Annotated[str | None, typer.Option("--profile", help="Credentials profile.")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Optional Hub API root override.")] = None,
    org: Annotated[str | None, typer.Option("--org", help="Workspace id for domain reads.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    for name in ("PWS_SESSION_TOKEN", "PWS_API_KEY", "PWS_BASE_URL"):
        if name in os.environ:
            _usage_error(f"{name} must be unset; use the selected profile")
    if not profile:
        _usage_error("--profile is required")
    if not json_output:
        _usage_error("--json is required")
    if org is not None and not org.strip():
        _usage_error("--org must not be blank")
    try:
        config = Config.resolve(base_url=base_url, org=org, profile=profile)
    except PWSError as exc:
        raise typer.Exit(code=cli._report(exc)) from exc
    if config.credential_kind != "device_session":
        _usage_error("The selected profile requires a device session; run `pws auth login --profile <name>`")
    ctx.obj = CliContext(mode=OutputMode.JSON, org=org, base_url=base_url, profile=profile)


def _require_org(ctx: typer.Context) -> None:
    root = ctx.find_root()
    if ctx.invoked_subcommand is not None and isinstance(root.obj, CliContext) and not root.obj.org:
        _usage_error("--org is required for domain reads")


for group in (spots_app, devices_app, components_app, rules_app):
    group.callback()(_require_org)

app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(edge_app, name="edge")
edge_app.add_typer(spots_app, name="spots")
edge_app.add_typer(devices_app, name="devices")
edge_app.add_typer(components_app, name="components")
edge_app.add_typer(rules_app, name="rules")

auth_app.command("whoami")(cli.auth_whoami)
config_app.command("show")(cli.config_show)
spots_app.command("list")(cli.spots_list)
spots_app.command("get")(cli.spots_get)
spots_app.command("structure")(cli.spots_structure)
devices_app.command("list")(cli.devices_list)
devices_app.command("get")(cli.devices_get)
devices_app.command("status")(cli.devices_status)
components_app.command("list")(cli.components_list)
rules_app.command("list")(cli.rules_list)
rules_app.command("get")(cli.rules_get)
rules_app.command("executions")(cli.rules_executions)


def main() -> None:
    app()
