# Raspberry Pi 4B (aarch64)

Verified on a Raspberry Pi 4B (aarch64, Python 3.13.5) in October 2026:

- `Device.listen()` ran and the agent showed online.
- After a key rotation the old key was refused (401).
- A clean stop (SIGTERM) took the agent offline.
- After a reboot, systemd retried and the device recovered. The network was late at boot, the first connection failed, and `Restart=on-failure` brought it back.

Not verified yet: sensor telemetry on the Pi. It arrived after this test, so do not promise sensor values there before running it.

## Python version

The SDK needs CPython 3.12 or newer, and a Raspberry Pi OS image can ship an older Python (3.11). When `python3 --version` is below 3.12, run `uv python install 3.12`, then create the virtual environment with it (`uv venv --python 3.12 <venv-dir>`) and install the pinned `SDK_VERSION` into that environment with `uv pip install --python <venv-dir>/bin/python`.

## Run it as a service

Copy `listen_daemon.service` from the examples that ship in the package (the `device/` folder under `$SDK_EXAMPLES`, set in the onboarding skill's install section; `listen_daemon.py` is beside it) to `/etc/systemd/system/` and adjust `User=`, the interpreter and key paths in `ExecStart=`, and the `Environment=` lines for your Hub and broker. Keep `Restart=on-failure`. One unit per device key.

If another service already drives the hardware (camera, relays), call that service from your actions instead of opening the pins yourself.
