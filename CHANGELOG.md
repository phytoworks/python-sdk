# Changelog

All notable changes to `phytoworks` (the Python SDK and the `pws` command line tool) are listed here, newest first.

## Version policy while the major version is 0

- A change that can break existing code or scripts raises the second number (0.1.x to 0.2.0).
- A fix raises the third number (0.1.2 to 0.1.3).
- While the major version is 0, commands and the Python API can change between releases. Pin an exact version when you
  install, for example `pip install phytoworks==0.1.3`, and read this file before you move to a new one.
- CPython 3.12 or newer is required. Linux and macOS are supported; native Windows works but is not yet officially
  verified. On a Raspberry Pi OS image that ships Python 3.11, install a newer interpreter with
  `uv python install 3.12`.

## 0.1.3

### Fixed

- `pws edge actions run` now exits with code 7 (outcome unknown) instead of 1 when the reply to a sent action is lost,
  because the action may still run on the device. The error line prints an `executionId`; run the command again with
  the same arguments and `--execution-id <id>` and Hub replays that run instead of starting the action a second time.
  The exit code table in the README says the same.
- `pws data media download` no longer stops at the first asset whose request or server reply fails. Every asset is
  still tried, the files already saved stay, and the command exits with the code of the first failure. With `--json`
  each failed asset appears as `{"id", "error"}` in `items`; with `--jsonl` each asset prints one line as soon as it
  finishes. A local file error, such as a destination that cannot be written, still stops the command.
- Downloading all media of one capture (`--capture`) skips the extra metadata request for every asset.
- The message for a missing login now says only to run `pws auth login`. `PWS_SESSION_TOKEN` stays supported for
  automation but is no longer suggested to people.
- `Device(key_file=...)` expands a leading `~`, so a service manager can pass `~/.config/pws/keys/<id>.key` as written.

### Changed

- The `pws phenos` and `pws approvals` groups are not public yet and no longer appear in `pws --help`. They still run
  when named directly and may move before they are documented.
