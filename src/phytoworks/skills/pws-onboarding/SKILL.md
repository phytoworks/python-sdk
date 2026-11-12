---
name: pws-onboarding
description: Install the phytoworks SDK and pws CLI, sign in with device login, connect a device to a PhytoWorks spot and agent, and run the pilot examples. Use when someone asks to set up, log in to, or connect a device with PhytoWorks.
license: MIT
compatibility: Requires CPython 3.12 or newer, uv, and network access to PyPI; runtime acceptance is recorded separately for Claude Code and Codex.
user-invocable: true
---

# PWS Pilot Onboarding

This guide installs the `phytoworks` SDK and `pws` CLI from a pinned PyPI release. It also covers Hub sign-in and the existing pilot examples. Use only an SDK source and Hub approved for your account.

## Prerequisites

- CPython 3.12 or newer.
- `uv` installed.
- Network access to PyPI.
- The account owner has given you the approved Hub and organization, and the SDK version to install. Keep these values for upgrades and rollback.

Set the exact version you intend to install:

```bash
SDK_VERSION=0.1.3
```

## Find this skill

Install the exact `SDK_VERSION` from PyPI. If the PyPI probe fails or the version is absent, stop and
report that the source is unknown. After installing the CLI, locate the packaged copy with the Python interpreter in the tool environment:

```bash
"$(uv tool dir)/phytoworks/bin/python" -c 'import pathlib, phytoworks; print(pathlib.Path(phytoworks.__file__).parent / "skills/pws-onboarding/SKILL.md")'
```

On Windows, use the tool environment's `Scripts\python.exe` instead of `bin/python`.

## Select and install the source

Probe PyPI for the exact pinned version:

```bash
python -m pip index versions phytoworks --index-url https://pypi.org/simple/
```

When the command succeeds and the exact `SDK_VERSION` appears in `Available versions`, install it:

```bash
uv tool install "phytoworks==${SDK_VERSION}"
pws --version
```

If the command succeeds but the exact version is absent, or the probe exits non-zero and its result is
unknown, stop and report that there is no verified install source. Never install an unpinned
`phytoworks` package or `pws` package.

### Verify the installed CLI

After installing, set `SDK_PY` and verify the installed package:

```bash
SDK_PY="$(uv tool dir)/phytoworks/bin/python"
"$SDK_PY" -c 'import phytoworks'
"$SDK_PY" -c 'import pathlib, phytoworks; print(pathlib.Path(phytoworks.__file__).parent / "skills/pws-onboarding/SKILL.md")'
SDK_EXAMPLES="$("$SDK_PY" -c 'import pathlib, phytoworks; print(pathlib.Path(phytoworks.__file__).parent / "examples")')"
ls "$SDK_EXAMPLES" "$SDK_EXAMPLES/device"
```

On Windows, use the tool environment's `Scripts\python.exe` instead of `bin/python`.

`SDK_EXAMPLES` is the folder of runnable examples that ships inside the package (`pip install phytoworks` has it too, at `phytoworks/examples` in site-packages). Every later step that names an example reads it from there, so no step needs a source checkout. Copy a file out of it before you edit it; the tool environment is not yours to modify.

### Verify the installed version

Confirm the installed distribution version matches `SDK_VERSION`:

```bash
"$SDK_PY" -c 'import importlib.metadata as m; print(m.version("phytoworks"))'
```

### Configure the pws-console skill

For read-only Console queries, use the [`pws-console` skill](../pws-console/SKILL.md). Copy its full folder, including the Codex sidecar, rules file, and query reference, into both agent skill roots. Install the rules separately in Codex's user `rules/` directory (`~/.codex/rules/` by default, or `$CODEX_HOME/rules/`), which [Codex loads at startup](https://developers.openai.com/codex/rules). Record the selected PyPI version and the copied-file hashes; repeat the copy after each SDK upgrade and restart Codex. The rules file makes Codex ask for approval before every `pws` command and lets `pws-console-read` run without asking, so approve the `pws` commands this skill has shown the person and nothing else:

```bash
SDK_PY="$(uv tool dir)/phytoworks/bin/python"
SDK_SKILLS="$("$SDK_PY" -c 'import pathlib, phytoworks; print(pathlib.Path(phytoworks.__file__).parent / "skills")')"
mkdir -p "$HOME/.claude/skills" "$HOME/.agents/skills" "${CODEX_HOME:-$HOME/.codex}/rules"
cp -R "$SDK_SKILLS/pws-console" "$HOME/.claude/skills/"
cp -R "$SDK_SKILLS/pws-console" "$HOME/.agents/skills/"
cp "$SDK_SKILLS/pws-console/agents/codex.rules" "${CODEX_HOME:-$HOME/.codex}/rules/pws-console.rules"
pws --version
find "$HOME/.claude/skills/pws-console" "$HOME/.agents/skills/pws-console" "${CODEX_HOME:-$HOME/.codex}/rules/pws-console.rules" -type f -print0 | xargs -0 shasum -a 256 | sort
```

## Use the CLI and project library in separate environments

`uv tool install` installs `pws` for command-line use. For a Python application, create or enter the application's own project and pin the same version there:

```bash
cd ..
uv init my-pws-project
cd my-pws-project
uv add "phytoworks==${SDK_VERSION}"
```

The existing examples call `PWS()` and use the `default` credential profile. The setup below signs in to that same profile. For a named profile in your own project code, construct `PWS(profile="pilot")`; for CLI commands, select the profile with `--profile pilot`.

### Optional dependencies

Add only the needed extra, at the same pinned version as the base package:

```bash
uv add "phytoworks[zarr]==${SDK_VERSION}"
uv add "phytoworks[pandas]==${SDK_VERSION}"
uv add "phytoworks[device]==${SDK_VERSION}"
```

## Select the Hub, profile, and organization

The default Hub is production. Use the Hub supplied by the pilot owner; an override must be HTTPS, except HTTP to localhost for a local development Hub. A credential profile stays bound to the Hub that issued it. Set `PWS_HUB` to the approved API root; use the production URL below only when that is the approved Hub:

```bash
PWS_HUB=https://api-0.phyto-works.com/api/v1
```

Start device-code login for the default profile and the approved Hub. `--no-browser` prints the approval URL and code when you need to open the browser yourself:

```bash
pws --profile default auth login --base-url "$PWS_HUB" --no-browser
```

Open the displayed URL in a human-controlled browser and approve only the code from the login you just started. Complete any Hub-required verification in that browser. The CLI stores this device's session, never a password. To use the production default, omit `--base-url`; to use another approved Hub, supply its HTTPS API root.

Check the signed-in identity, Hub, profile, and organization memberships:

```bash
pws --profile default auth whoami
```

In the project environment, confirm that the SDK can read the same signed-in default profile:

```bash
uv run python -c 'from phytoworks import PWS; print(PWS().me().user_id)'
```

Choose an organization **ID** from that output. Copy it into `ORG_ID`, then pass it on commands with `--org "$ORG_ID"` or export it as `PWS_ORG`. Do not use a slug where an ID is required. For example:

```bash
ORG_ID='paste-the-organization-id-from-whoami'
export PWS_ORG="$ORG_ID"
pws --profile default --org "$ORG_ID" --json edge spots list
```

Use `--json` or `--jsonl` for machine-readable output. The existing `-q` mode prints simple values such as IDs and paths. The pilot uses Hub request records for usage measurement; the SDK does not send separate client usage telemetry or write a local usage file.

## Connect a device

Start from values the person confirmed once: Hub, organization ID, spot slug and name, agent identifier and name, key file location. Before every write, show the target and the exact command, and wait for a yes. Reuse what exists before creating anything: this skill is meant to be run twice. It moves nothing physical and never opens a shell on the device.

1. **Permission.** `pws --json edge provisioning check` (re-run after login and after the person changes a role). Exit 8: stop before any write and offer an Owner/Admin account, a role grant, or a switch of account that the person performs. Exit 9: ask the person, or stop at the first write's 403.
2. **Spot.** `pws --json edge spots get <slug>`. Reuse it; if it does not exist, `pws edge spots create "<name>" --slug <slug>` after confirmation.
3. **Agent.** `pws --json edge agents list --identifier <identifier>` searches the whole organization, because an identifier is unique there, not per spot. Same spot: reuse. Another spot: stop and tell the person; moving an agent is out of scope. None: `pws edge agents create "<name>" --identifier <identifier> --spot <spot-id>` after confirmation. A 403 here means no organization read access: ask the person for the agent ID instead.
4. **Key.** The default file is `<credentials folder>/keys/<agent-id>.key`. The credentials folder is the directory of `$PWS_CREDENTIALS_FILE` when that is set, else `~/.config/pws`; it need not exist. If the key file is missing, `pws edge agents keys issue` creates `keys/` (0700) and the 0600 file itself, so never create either by hand. `--out <path>` overrides the location. If it exists, its mode must be 0600 (anything looser: tell the person, `chmod 600` only on their yes), then find the agent's entry in `agents[]` of `pws --json edge spots get <slug>`. `realtimeStatus.isOnline: true` means its device is running on a live key now: reuse the file and do not sign in with it, because any sign-in with the same key takes over the running device's session. `isOnline: false` means offline: check the file against the confirmed Hub. `realtimeStatus: null` means the status is unknown (no heartbeat for five minutes, or the Hub could not read it): ask the person whether the device program is running, and check only if it is not. `Device` does not read the operator profile: it takes `PWS_BASE_URL`, else the production default, so a bare check would send the key to production. If `PWS_BASE_URL` is already set to anything other than `$PWS_HUB`, stop and ask, because the variable wins. Otherwise run, with `SDK_PY` from the install section:

   ```bash
   PWS_BASE_URL="$PWS_HUB" "$SDK_PY" -c 'import sys; from phytoworks.device import Device; print(Device(sys.argv[1]).discover())' <key-file>
   ```

   The check signs in with the key, so a device that is running after all loses its session until its next call signs in again; say so before running it. The agent ID in the answer matches: reuse. An authentication error: report it and propose `pws edge agents keys reissue <key-id> --agent <agent-id> --force` (revoked or expired key; take `<key-id>` from `pws --json edge agents keys list --agent <agent-id>`; `--force` is needed to write over the existing file, or give another path with `--out`). If there is no file, run `pws --json edge agents keys list --agent <agent-id>` and show the person the keys: some may belong to a device that is gone (revoking is their call). In `items[]`, a key can be recovered only when all four hold: `isActive: true`, `expiresAt` is omitted, `null`, or later than the current UTC time (`isActive` does not reflect expiry, and an expired key recovers but cannot sign in), `keyUsage: DEVICE` (an `INTEGRATION` key cannot register a device), and `recoverable: true` (the Hub keeps a recovery copy). For such a key, offer to download the same key again, which changes nothing on the Hub and leaves a running device untouched: `pws edge agents keys download <key-id> --agent <agent-id> --out <key-file>` after confirmation (the file must not exist yet; it is written 0600). If several keys qualify, ask which one the device uses. With no key that passes all four checks, or when `download` reports no recoverable copy, issue a new key with `pws edge agents keys issue --agent <agent-id> --name "<name>"` after confirmation. Use `rotate` only when asked; it cuts the old key at once. One key serves one process.
5. **Device program.** Installing on the box belongs to the person. Point to the Device section of the package README and to `$SDK_EXAMPLES/device/` (`cron_capture.py` for one capture per run from your own scheduler, `listen_daemon.py` and `listen_daemon.service` for an always-on device; `SDK_EXAMPLES` is set in the install section), and give four rules: send the complete component list every time, give each action `metadata.ui.displayContext` so Console can place it, register an action that moves hardware only behind the device's own opt-in switch, and run the program and its service against the same Hub (`PWS_BASE_URL`, as `listen_daemon.service` shows) and from the environment reference below.
6. **Verify.** `pws --json edge spots get <slug>` (the agent's `agents[].realtimeStatus.isOnline` is `true`), `pws --json edge telemetry topics --device <device-id>`, and one recent value with `pws --json edge telemetry query --device <device-id> --topic <topic-id> --since 10m`, where `<topic-id>` is a `topics[].id` from the list, not a topic name. The Console sensor tab and overview card are for the person to look at and answer.
7. **Report** one table: Hub, organization, spot, agent (reused or created, with IDs); key (reused, reissued, new or rotated, with key ID and file path, never the secret); online or not, the topics seen, whether the person confirmed Console. For a failure, name the step it stopped at and the exact next command.

Environment notes live in [references/environments/](references/environments/README.md); read the one that matches the device only when you reach step 5.

## Run the five pilot workflows

Use the example files installed with the package, in `$SDK_EXAMPLES` (set in the install section); each is a few lines, so read its source before running it. Copy one out of that folder to run or change it. Set the environment variables named in each item below, and use the `default` profile because the examples construct `PWS()` without a profile argument.

1. **W1 — capture download:** `$SDK_EXAMPLES/w1_capture_download.py` lists the latest capture and downloads it when one exists. This is a read/download workflow; downloaded objects come from storage after the Hub issues a URL.
2. **W2 — image upload:** `$SDK_EXAMPLES/w2_image_upload.py` (reads `PWS_IMAGE_FILE`, `PWS_THUMBNAIL_FILE`, `PWS_CAPTURE_SESSION`, `PWS_IMAGE_WIDTH`, `PWS_IMAGE_HEIGHT`) uploads an image and thumbnail and completes a MediaAsset record. This writes production data and uploads files. Confirm the organization, capture, images, and dimensions with the pilot owner before running it. This workflow has no dry-run or confirmation flag.
3. **W3 — action run:** `$SDK_EXAMPLES/w3_action_run.py` (reads `PWS_SPOT`, `PWS_DEVICE`, `PWS_DURATION`) runs the named action for the selected spot and device. An action can move equipment or change its state. Inspect the action first with `pws --profile default --json edge actions describe pump.timed --spot "$PWS_SPOT"` and verify the spot, device, and parameters with the responsible operator. `edge actions run` has no dry-run or confirmation flag; `--wait` only waits for the result.
4. **W4 — sensor-conditioned actuation:** `$SDK_EXAMPLES/w4_sensor_actuation.py` (reads `PWS_SPOT`, `PWS_DEVICE`, `PWS_DURATION`, `PWS_SENSOR_TOPIC`, `PWS_THRESHOLD`) reads a device topic's latest telemetry point and runs the action only when a point from the last five minutes is below the configured threshold. It can move equipment or change its state when the condition is met. Verify the topic, threshold, device, spot, and action with the responsible operator. The example has no dry-run or confirmation flag.
5. **W5 — telemetry history:** `$SDK_EXAMPLES/w5_telemetry_pandas.py` (reads `PWS_DEVICE`, `PWS_TOPIC`, and optionally `PWS_SINCE`, default `24h`) reads telemetry history into a pandas DataFrame. Install the `pandas` extra using the [optional-dependency instructions](#optional-dependencies); this workflow reads data.

W2, W3, and W4 may be part of real pilot work only when the pilot owner has authorized the exact target and inputs. The SDK does not add a safety switch to these existing examples.

## Logout and sign in again

Log out of only the selected profile, then start a fresh device-code login and approve the new code in the browser:

```bash
pws --profile default auth logout
pws --profile default auth login --base-url "$PWS_HUB" --no-browser
pws --profile default auth whoami
```

Use the same approved Hub for re-login. Logging in again replaces the session in that profile; other profiles and browser sessions are not logged out.

## Upgrade or roll back

Upgrade to a newly approved pinned PyPI version and repeat the source checks from the install section.

To roll back, set `SDK_VERSION` to the known-good version and reinstall the CLI and project
dependency from PyPI:

```bash
SDK_VERSION=<known-good version>
uv tool install --reinstall "phytoworks==${SDK_VERSION}"
pws --version
uv add "phytoworks==${SDK_VERSION}"
```

Confirm `pws --version` shows the known-good version. Do not move or force-update a published tag. Run the project's normal checks after changing
its dependency.

## Report a failure

Capture the command that failed, the exact `pws --version` output, the error/status, and the Hub request ID if the response includes one. Include the selected version, Hub, profile, and organization ID when relevant. Remove access tokens, cookies, API keys, device codes, image contents, and other private data from the report.
