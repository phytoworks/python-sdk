---
name: pws-console
description: Explicitly invoke to read PWS spots, device structure and status, components, rules, and recent rule executions through the Python CLI; report in the user's language. Use onboarding for installation or login.
license: MIT
compatibility: Requires the matching phytoworks SDK release and pws-console-read; runtime acceptance is recorded separately for Claude Code and Codex.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash(pws-console-read *)
---

# PWS Console

## Hard rules

- Stop and ask for explicit invocation unless the user typed `/pws-console` or
  `$pws-console` themselves. Being asked to invoke it yourself or discovering
  this file through a search does not count.
- Run only `pws-console-read`, exactly one invocation per shell command.
  Never use `;`, `&&`, `|`, redirection, or substitution.
- Never run `pws`, `curl`, a browser, or login/logout, even on request.
  Refuse that part and suggest an allowed read below.

## Who can run this

Any signed-in user may request a read; the Hub decides access for each query.
An earlier read does not prove permission for another resource.

Claude Code is supported as packaged. For Codex, keep approvals on (default
`on-request`), install `agents/codex.rules` via onboarding, and never use this
skill with approvals disabled. The rules file makes every `pws` command ask the
user for approval and lets `pws-console-read` run, so an unattended agent cannot
change anything. The signed-in account's Hub role is the real limit on what can
change.

## Before querying

1. Run `config show` to confirm the effective profile and non-secret Hub API
   root. Never print, open, or search credentials or environment files.
2. Run `auth whoami` and ask the user to select the organization by its Hub ID.
   Do not infer an organization from a name, host, or device number.
3. Keep the selected profile, Hub, and organization consistent. Without optional
   `--base-url`, the profile's bound Hub is used; conflicting Hubs are refused.
4. Domain reads require an explicit `--org`. Use IDs or slugs returned by an
   allowed Hub read; preserve IDs and opaque SRNs exactly.

## Allowed commands

Put root options first. Require `--profile` and `--json`; add `--base-url HUB` only for the user-selected Hub and `--org ORG_ID` on every domain read.

```text
pws-console-read --profile PROFILE [--base-url HUB] --json config show
pws-console-read --profile PROFILE [--base-url HUB] --json auth whoami
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge spots list [--page N] [--limit N]
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge spots get SPOT_ID_OR_SLUG
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge spots structure SPOT_ID_OR_SLUG
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge devices list --spot SPOT_ID [--page N] [--limit N]
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge devices get DEVICE_ID
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge devices status DEVICE_ID
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge components list --device DEVICE_ID [--page N] [--limit N]
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge rules list --spot SPOT_ID_OR_SLUG [--page N] [--limit N]
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge rules get RULE_ID --spot SPOT_ID_OR_SLUG
pws-console-read --profile PROFILE [--base-url HUB] --org ORG_ID --json edge rules executions RULE_ID --spot SPOT_ID_OR_SLUG
```

Resolve ambiguous spots with `edge spots list`; inventory uses `edge devices list --spot`
and `edge components list --device`. Structure actions are information only.
`edge rules executions` returns the latest 10 rows, without paging or full history.

## Query and report

Quote IDs containing shell metacharacters as literal arguments. Never use raw HTTP or SDK code or invent IDs, defaults, missing fields, or scope.

Read tool-captured JSON stdout as one document, with stderr separate. Preserve
unknown fields; missing values are unknown. Report returned rows and paging scope;
several requests are not one atomic snapshot. See `references/queries.md`.

Report in the language the user writes in, defaulting to English: Hub root, profile,
organization and queried IDs, UTC observation start/end, sources, row count,
completeness, and limitations. Hub status and cached observations do not confirm
physical light, water, or equipment effects.

```text
Queried: Hub <API root>, profile <profile>, organization <ID>, spot <ID>, device <ID>
Observed: <UTC start>–<UTC end>; several requests are not one atomic snapshot
Configuration/status: <fields checked>; missing values are unknown
Rules: <ID>; latest 10 executions at most; full execution history not checked
Scope: <rows returned>, <complete / one page / limited / unknown>
Limits: Hub status and cached observations; physical equipment effects not checked
```

## Failures

| Result | Required response |
|---|---|
| Missing/expired session or final 401 (exit 3) | Stop. Point to onboarding login for this profile and Hub; this skill never logs in or out. Count normal SDK exchange/refresh separately from domain reads. |
| 403 (exit 5) | Stop that query. Preserve the sanitized code and request ID; ask the responsible owner for access. Do not infer a role from another read. |
| 404 (exit 4) | Report the requested ID and Hub. Do not guess a replacement or silently change scope. |
| Final 429 (exit 1) | Keep bounded SDK retry notices on stderr. Do not add a retry loop. |
| Valid empty array or list | Report zero rows within that query and window. Empty execution history does not mean a rule never ran. |
| Empty stdout, invalid JSON, nonzero exit, or missing expected field | Report failure or unknown observation, never zero or success. Keep stderr separate; show HTTP status only when provided. |
| Paging or limits | Without `--page`, the CLI walks pages up to `--limit`; `--limit` is a total cap. With `--page`, it reads one page. Report truncation or unknown completeness and preserve page-size errors. |

Stop after a refused or failed read. Do not change target, organization, Hub, command, or output mode to retry.
