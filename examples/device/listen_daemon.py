"""Always-on device: Console capture commands and your own schedule, on one action executor per key.

    python listen_daemon.py ~/.config/pws/keys/<agent id>.key /data/capture 4024 3036 1800

``Device.listen()`` is the device's one action executor: it serves Hub capture commands on the main thread and runs
every action on one worker thread, first accepted first run. The scheduler thread here only asks that executor for a
capture with ``device.submit()``; it never calls the Hub itself, so a command and a scheduled capture never drive the
camera at once and nothing reaches the Hub after ``listen()`` signs off. Keep the schedule in this process: a second
process with the same key re-discovers and cuts this one's session. SIGTERM or SIGINT winds
``listen()`` down and exits 0; an error a restart cannot fix exits 10, which listen_daemon.service never restarts.

Needs ``pip install 'phytoworks[device]'`` and ``PWS_MQTT_URL`` (``mqtts://host:443``). ``PWS_BASE_URL`` defaults to the
production Hub; set it for any other Hub. A development Hub on another machine is reached through a tunnel (for
example SSH) at ``http://localhost:15004/api/v1``: credentials go over plain HTTP only to loopback.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from pathlib import Path
from types import FrameType

from phytoworks.device import Action, CaptureContext, Device, LocalRun
from phytoworks.errors import (
    AuthError,
    DeviceBusy,
    DeviceStopped,
    ManualModeActive,
    MqttUnavailable,
    NotServing,
    SessionTakenOver,
    SubscribeDenied,
)
from phytoworks.errors import PermissionError as KeyRefused

VIEWS = ("left", "right")
STOP_GRACE = 30.0  # listen_daemon.service's TimeoutStopSec is budgeted on this value
# Console's modality shape: each top-level key is a modality with `enable` and its `parameters`
CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "rgb": {
            "type": "object",
            "properties": {"enable": {"type": "boolean"}, "parameters": {"type": "object", "properties": {}}},
            "required": ["enable"],
        }
    },
    "additionalProperties": False,
}
SCHEDULED = {"sessionName": "Scheduled capture", "rgb": {"enable": True, "parameters": {}}}
# A revoked or refused key (CredentialRevoked is an AuthError), another process on this key, refused topics, no
# broker URL or credential, or a missing [device] extra: each needs a person, so the unit never restarts on it.
FATAL = (AuthError, KeyRefused, SessionTakenOver, SubscribeDenied, MqttUnavailable, ImportError)
EXIT_FATAL = 10  # also an unreadable or too open key file and a leftover `capture` action; the log names which

log = logging.getLogger("listen_daemon")


def shoot(folder: Path, view: str) -> tuple[Path, Path]:
    """Your camera code: move to ``view``, write the image and its thumbnail, and return both paths."""

    return folder / f"{view}.jpg", folder / f"{view}_thumb.jpg"


class Daemon:
    def __init__(self, device: Device, folder: Path, width: int, height: int, interval: float) -> None:
        self.device, self.folder, self.width, self.height, self.interval = device, folder, width, height, interval
        self.ended = threading.Event()  # set on the main thread once listen() has returned, never in a signal handler

    def actions(self) -> list[Action]:
        return [Action("device.capture", self.on_capture, action_type="CAPTURE", parameters=CAPTURE_SCHEMA)]

    def run(self) -> int:
        """Serve until a signal (0) or a fatal error (EXIT_FATAL); call after ``register(actions=self.actions())``."""

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._on_signal)
        scheduler = threading.Thread(target=self._schedule, name="capture-schedule", daemon=True)
        scheduler.start()
        try:
            self.device.listen(stop_grace=STOP_GRACE)
        except FATAL as error:
            log.error("listen() stopped: %s", type(error).__name__)
            return EXIT_FATAL
        finally:
            self.ended.set()
            scheduler.join()
        return 0

    def on_capture(self, ctx: CaptureContext) -> None:
        """A Hub command or a scheduled submit, on the executor's worker. A cancel or an error leaves the session to
        the executor, which cancels or fails it."""

        ctx.device.start(ctx.session)
        for view in VIEWS:
            ctx.check()  # stop between moves on a Console or local cancel, the deadline or a stopping daemon
            image, thumbnail = shoot(self.folder, view)
            ctx.device.upload_image(
                image,
                thumbnail=thumbnail,
                session=ctx.session,
                width=self.width,
                height=self.height,
                labels={"view": view},
            )
        ctx.check()  # a cancel or stop during the last move must not complete the session
        ctx.device.complete(ctx.session)

    def _schedule(self) -> None:
        """Ask for one capture every ``interval`` seconds. When to capture is this code's; the executor runs it."""

        last: LocalRun | None = None
        while not self.ended.wait(self.interval):
            if last is not None:
                if not last.done():  # one scheduled capture at a time: a full executor would close Console's channel
                    log.info("scheduled capture skipped: the previous one is still queued or running")
                    continue
                result = last.wait(0)
                if result.status != "SUCCESS":  # a local run leaves no Hub record but its session: log it here
                    log.warning("scheduled capture ended %s: %s", result.status, result.error)
                last = None
            try:
                last = self.device.submit("device.capture", SCHEDULED)
            except (NotServing, DeviceBusy, ManualModeActive) as error:  # not serving yet, full, or manual mode
                log.info("scheduled capture skipped: %s", type(error).__name__)
            except DeviceStopped:
                return  # listen() is winding down

    def _on_signal(self, _signum: int, _frame: FrameType | None) -> None:
        # Device.stop() only sets an attribute -- no lock, no I/O -- so a second signal landing inside this handler
        # cannot deadlock, and a stop before listen() has its loop is remembered. The rest follows listen()'s return.
        self.device.stop()


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry presigned upload URLs
    key_file, folder, width, height = argv[1], Path(argv[2]), int(argv[3]), int(argv[4])
    interval = float(argv[5]) if len(argv) > 5 else 1800.0
    try:
        device = Device(key_file)
    except (OSError, ValueError) as error:
        log.error("cannot use the key file: %s", type(error).__name__)
        return EXIT_FATAL
    with device:
        daemon = Daemon(device, folder, width, height, interval)
        try:
            device.register("camera-1", "Motorized camera", actions=daemon.actions())
        except (AuthError, KeyRefused) as error:
            log.error("the Hub refused this key: %s", type(error).__name__)
            return EXIT_FATAL
        except ValueError as error:  # an earlier SDK's `capture` action: the message names it and its cleanup
            log.error("%s", error)
            return EXIT_FATAL
        return daemon.run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
