# PWS Console query notes

Use only `pws-console-read`. The user must invoke the skill explicitly and
select the profile, Hub, and organization for the requested observation.

## Resolve scope and IDs

```bash
pws-console-read --profile PROFILE --json config show
pws-console-read --profile PROFILE --json auth whoami
pws-console-read --profile PROFILE --org ORG_ID --json edge spots list --limit 100
```

Choose an organization ID from `auth whoami`. `config show` reports effective
non-secret settings; it does not authenticate or contact the Hub. The Hub
decides permissions when a read runs. Keep the profile's bound Hub unless the
user selected another compatible Hub and supplied `--base-url`.

Resolve a spot by its Hub ID or slug, then retain the canonical ID in later
commands:

```bash
pws-console-read --profile PROFILE --org ORG_ID --json edge spots get SPOT_ID_OR_SLUG
pws-console-read --profile PROFILE --org ORG_ID --json edge spots structure SPOT_ID_OR_SLUG
pws-console-read --profile PROFILE --org ORG_ID --json edge devices list --spot SPOT_ID --limit 100
pws-console-read --profile PROFILE --org ORG_ID --json edge components list --device DEVICE_ID --limit 100
pws-console-read --profile PROFILE --org ORG_ID --json edge devices status DEVICE_ID
```

Use Hub IDs from the returned objects. Do not derive an identifier from a
hostname, display name, or device number. An absent status field is unknown.

## Rules and recent executions

```bash
pws-console-read --profile PROFILE --org ORG_ID --json edge rules list --spot SPOT_ID_OR_SLUG --limit 100
pws-console-read --profile PROFILE --org ORG_ID --json edge rules get RULE_ID --spot SPOT_ID_OR_SLUG
pws-console-read --profile PROFILE --org ORG_ID --json edge rules executions RULE_ID --spot SPOT_ID_OR_SLUG
```

Rule list commands support `--page` and `--limit`. Without `--page`, `--limit`
caps the total collected rows; with `--page`, only that page is returned. The
executions command uses the Hub's default window of 10 and cannot request more.
Describe it as recent executions, not the full history. Preserve Hub rule IDs.

## Output and completeness

- JSON stdout is the machine-readable result; keep stderr visible for retry
  notices, truncation, and sanitized errors.
- A valid empty list is zero rows for that query. Empty rule executions do not
  establish that the rule never ran.
- A `--limit` may leave additional rows unread. Report `limited` when the CLI
  announces a cap; report completeness as `unknown` when paging metadata or
  output is missing or invalid.
- An explicit `--page` is one page, even if more pages exist.
- Several reads can observe different moments. Include the UTC start/end and
  avoid describing the result as an atomic snapshot.
- Preserve unknown response fields and topic keys. Do not fill absent values
  with guessed defaults.

## Failure handling

Keep the helper's exit status and stderr. Exit 3 means authentication failed;
exit 5 is a permission denial; exit 4 is not found; final rate limiting is exit
1 after the SDK's bounded retries. Never change scope or retry with an
unrestricted CLI to work around a failure. The skill does not log in, mutate
rules, execute actions, provision devices, reveal keys, or access media.
