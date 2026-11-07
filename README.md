# PhytoWorks operator SDK

`phytoworks` is a Python SDK for the PhytoWorks Hub API. The same distribution
provides the `pws` command line tool. It supports CPython 3.12 and newer; CI
checks Python 3.12, 3.13, and 3.14. Native Windows works but is not yet
officially verified.

## Install

Install the Python package or the CLI:

```bash
pip install phytoworks==0.1.2
uv tool install phytoworks==0.1.2
```

Optional features are installed as extras:

```bash
pip install 'phytoworks[pandas]==0.1.2'  # telemetry DataFrames
pip install 'phytoworks[zarr]==0.1.2'     # array and Zarr media
pip install 'phytoworks[device]==0.1.2'   # Device.listen() MQTT receive loop
```

For a Python project managed by uv, add the base package or the needed extras
with `uv add`, for example `uv add 'phytoworks[zarr]==0.1.2'`.

## Quickstart

```python
from phytoworks import PWS

pws = PWS()
for spot in pws.spots.list():
    print(spot.name)
```

`PWS` and `AsyncPWS` expose Hub organizations, spots, devices, telemetry,
rules, captures, media, and actions. Reads use the authenticated operator's
organization scope. Media downloads stream from storage; image and array uploads
create Hub media records. Action runs can change equipment state, so confirm the
spot, device, and parameters before running them.

## Authentication and organization scope

Run `pws auth login` to start Hub device-code login. The CLI prints a short code
and approval link; approve only a login you started. It stores the device
session in `~/.config/pws/credentials.toml` with mode `0600`, never a password.
The SDK exchanges the session for short-lived JWTs and refreshes them when needed.

Use `pws auth whoami` to see your user and organization memberships. Choose an
organization by ID with `--org <organization-id>` or set `PWS_ORG`. The CLI
uses the production Hub by default. To use another Hub, pass `--base-url` or set
`PWS_BASE_URL` (the URL ends in `/api/v1`, for example
`PWS_BASE_URL=https://hub.example.test/api/v1 pws auth login`); credentials are
bound to the Hub that issued them. Hub
credentials are sent only over HTTPS, except for localhost development.

Operator sessions and API keys have different roles. An operator session
accesses operator routes. An agent or DEVICE key is for the device plane and
cannot authenticate operator requests.

## CLI examples

```bash
pws auth login --no-browser
pws auth whoami
pws --json edge spots list
pws data captures list --spot <spot-id> --since 7d
pws data media download <asset-id> --dest ./downloads
pws edge actions describe <action-name> --spot <spot-id>
pws edge actions run <action-name> --spot <spot-id> --params '{"duration":120}' --device <device-id>
```

The top level holds `auth`, `orgs`, `config`, `doctor`, `phenos` and `approvals`.
Everything else lives in a group: `pws edge` for sites and equipment (spots,
devices, components, actions, rules, telemetry, agents, provisioning) and
`pws data` for captures and media. `pws phenos` works on one photo in a scoped
session (annotations, inference, executions), and `pws approvals` follows the
requests that wait for a person to approve them in Phenos.
Typing a noun outside its group, such as `pws spots list`, stops with the full
path to use. A scope is an option (`--spot`, `--device`, `--agent`, `--capture`);
the thing you act on is the positional argument.

On a terminal, commands show readable tables. Use `--json` or `--jsonl` for
machine-readable output, or `-q` for identifiers and download paths. Rule
editing stays in the PhytoWorks Console.

`pws phenos inference start` returns an execution id. The outlines it finds are
added to the photo when `pws phenos execution status ID` reads the execution, so
read it again until it finishes; `pws phenos execution wait ID` does that for you.

Sign in with an organization (`pws auth login --org <ORG_ID>`), then start a session for one photo and run an operation in it:

```bash
pws phenos session start --image <image-id>
pws phenos inference start --model sam3 --image <image-id> --prompt plant
pws phenos execution wait <execution-id>
```

A change or delete of annotations waits for a person to approve it in Phenos: the
command exits 10 and prints an approval id. `pws approvals wait` only reads; once
it exits 0, run the same command again to use the approval.

```bash
pws phenos annotation delete --image <image-id> --annotation <annotation-id>
pws approvals wait <approval-id>
pws phenos annotation delete --image <image-id> --annotation <annotation-id>
```

`--timeout` on `execution wait` and `approvals wait` is not a hard stop: the first
check always runs, no new check starts once the time is up, and a check already
under way is not cut off.

## Exit codes

| Code | Name | Meaning |
| --- | --- | --- |
| 0 | ok | Done. |
| 1 | error | Any other failure, including a server that cannot be reached. |
| 2 | usage | The arguments were rejected. |
| 3 | auth | The login or Phenos session is missing or has expired. |
| 4 | not_found | The thing asked for does not exist in this scope. |
| 5 | permission | The login may not do this. |
| 6 | action_failed | A started action or Phenos execution ended failed or cancelled. |
| 7 | action_timeout | The outcome is unknown; a started job may still be running. |
| 8 | provisioning_denied | `pws edge provisioning check` was denied. |
| 9 | provisioning_unknown | `pws edge provisioning check` could not decide. |
| 10 | approval_pending | A person must approve the request in Phenos; nothing started. |

## Device integrations

`phytoworks.device.Device` is a separate device persona. It takes a DEVICE key
file, not the operator's session, and supports discovery, registration, capture
sessions, image and array uploads, and telemetry. Install the `device` extra to
use `Device.listen()`, which explicitly starts the optional MQTT receive loop
and action worker; importing the module does not connect to a broker or start a
thread.

Issue a DEVICE key with `pws edge agents keys issue --agent <agent-id>` and keep it in a file with
mode `0600`. A key is intended for one running process. A remote action can
move hardware, so keep physical safety controls in the device program and
verify the action configuration with the responsible operator.

## Agent skills

The package ships two agent skills under `phytoworks/skills`: `pws-onboarding`
(install, sign in, connect a device, run the pilot examples) and `pws-console`
(read-only Console queries through `pws-console-read`). Both are ordinary skill
folders with a `SKILL.md` and `name`, `description`, `license`, `compatibility`
and `user-invocable` frontmatter. Copy a whole folder into `~/.claude/skills/`
or `~/.agents/skills/` to use it, and invoke it by name, `/pws-onboarding` or
`/pws-console`. `pws-console` also ships a Codex rules file that
`pws-onboarding` installs.

To install both skills for Claude Code and Codex without copying folders by hand:

```bash
npx skills add phytoworks/python-sdk#v0.1.2
```

## Documentation

The [SDK and CLI quickstart](https://docs.phyto-works.com/guides/sdk-cli/quickstart)
has setup, authentication, Device, and workflow guides. Visit the
[PhytoWorks homepage](https://phyto-works.com) for product information.
