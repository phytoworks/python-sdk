"""Device action executor (M5a-3, L1, L2, L4d): Hub commands, cancels and manual-mode syncs in, action results out, and
local :meth:`~phytoworks.device.Device.submit` items on the same queue, all run from one action table. A local run of
an action declared to the Hub leaves a device action record (HTTP) and its current value (``results/batch``).

The thread that calls :meth:`phytoworks.device.Device.listen` is the supervisor and the only one that
touches the broker connection; one worker thread runs each item's action handler for both doors, first
accepted first run. Liveness stays the HTTP heartbeat (no MQTT ``status`` or ``shutdown`` is ever published),
and the heartbeat drops ``commandChannel: "none"`` only while the subscription stands. Design and the facts
behind each rule: docs/plan/2026-08-06-sdk-cli-skills/field-capture-modalities/2026-10-07-m5a3-mqtt-loop-redesign.md
and 2026-10-11-device-action-executor-design.md in the same folder; records, current values and the declaration:
2026-10-12-device-action-l4-design.md §2-§4.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import islice
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from .errors import (
    ActionCancelled,
    AuthError,
    CredentialRevoked,
    DeviceBusy,
    DeviceStopped,
    ManualModeActive,
    MqttUnavailable,
    NotServing,
    PWSError,
    RateLimitError,
    SessionTakenOver,
    SubscribeDenied,
    ValidationError,
)

if TYPE_CHECKING:
    from .device import Device, MqttEndpoint, MqttSlot, _ScopedDevice

_logger = logging.getLogger("phytoworks.device")

CONNECT_TIMEOUT = 10.0
CONNACK_DEADLINE = 10.0
SUBACK_DEADLINE = 10.0
KEEPALIVE = 60
LOOP_STEP = 1.0
BACKOFF_MAX = 60.0
REDISCOVERY_COOLDOWN = 300.0
TAKEOVER_WINDOW = 30.0
RESULT_RETENTION = 60.0
OUTBOX_LIMIT = 8  # items held at once, both doors (queued, running, or a Hub result awaiting PUBACK or retention)
FLUSH_DEADLINE = 10.0
# Local action records (L4 design §2): held for the Hub oldest first, sent one request per tick, as many as fit the
# Hub's per-request limits; agent-rs's retry policy (1, 2, 4 s; four attempts), then dropped.
RECORD_LIMIT = 32  # records the Hub has not taken, the chunk being sent included; a newer one pushes the oldest out
RECORD_CHUNK = 50  # records per request
RECORD_CHUNK_BYTES = 1_000_000  # serialized request body, under the Hub's 1 MiB JSON parser limit
RECORD_RETRY_DELAYS = (1.0, 2.0, 4.0)
# Seconds from the end of the last request of a queue (local records, telemetry) to the start of a new chunk (agent-rs
# flushes every 10 s): steady, at most 6 chunks a minute. With retries (four tries a chunk, one request at a time) at most
# 28 POSTs in any 60 s -- 6 new chunks and the one under way -- under the Hub's ACTION_RECORD and telemetry limit of 30 per
# agent and route and their 300 s block.
RECORD_PERIOD = 10.0
# Telemetry points the Hub has not taken (15 s apart on two topics: about 20 hours). A request holds at most the Hub's
# telemetry/batch limits: 50 topics, 1000 points per topic, 1 MiB of body (Fastify), kept under it.
TELEMETRY_LIMIT = 10_000
TELEMETRY_TOPICS = 50
TELEMETRY_POINTS = 1000
TELEMETRY_BODY_BYTES = 1_000_000
# A 429 waits its Retry-After, clamped like agent-rs's telemetry client (no longer than the Hub's longest block; 30 s
# when the answer names none), and the same chunk goes again: a throttled point is never dropped.
TELEMETRY_THROTTLE_DEFAULT = 30.0
TELEMETRY_THROTTLE_MAX = 600.0
_RETRYABLE_RECORD_STATUS = frozenset({408, 500, 502, 503, 504})
_RECORD_JSON_BYTES = 32 * 1024  # each of parameters and result, as the Hub measures it (_hub_json_bytes)
_RECORD_JSON_DEPTH = 32
_RECORD_ERROR_BYTES = 4 * 1024
_RECORD_SPAN = timedelta(seconds=86400)  # completedAt - startedAt
_BATCH_LIMIT = 100  # results per results/batch message
_BAD_CREDENTIALS = frozenset({0x86, 0x87})
_TERMINAL_SESSION = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


class Link(Protocol):
    """One broker connection attempt. Callbacks land in :attr:`events`; only the supervisor calls these."""

    events: list[tuple[Any, ...]]

    def connect(self, endpoint: MqttEndpoint, slot: MqttSlot) -> None: ...
    def subscribe(self, topics: list[str]) -> int: ...
    def publish(self, topic: str, payload: bytes) -> int: ...
    def loop(self, timeout: float) -> None: ...
    def disconnect(self) -> None: ...


class PahoLink:
    """A fresh paho-mqtt 2.x client per attempt: MQTT 5, VERSION2 callbacks, clean start, no session expiry.

    paho's own reconnect and its in-flight QoS 1 queue die with this object; the loop's outbox is the only
    thing that republishes (redesign fact 13). ``loop_start``/``connect_async`` are never used (fact 7).
    """

    def __init__(self, client_id: str) -> None:
        from paho.mqtt.client import Client
        from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion

        self.events: list[tuple[Any, ...]] = []
        self._client = Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=MQTTProtocolVersion.MQTTv5,
            reconnect_on_failure=False,
        )
        self._client.connect_timeout = CONNECT_TIMEOUT
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_publish = self._on_publish
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def connect(self, endpoint: MqttEndpoint, slot: MqttSlot) -> None:
        from paho.mqtt.packettypes import PacketTypes
        from paho.mqtt.properties import Properties

        self._client.username_pw_set(slot.principal, slot.password)
        self._client.tls_set(ca_certs=endpoint.ca_file)  # verifies the chain and the host name
        properties = Properties(PacketTypes.CONNECT)  # type: ignore[no-untyped-call]
        properties.SessionExpiryInterval = 0
        self._client.connect(endpoint.host, endpoint.port, keepalive=KEEPALIVE, clean_start=True, properties=properties)

    def subscribe(self, topics: list[str]) -> int:
        from paho.mqtt.subscribeoptions import SubscribeOptions

        _rc, mid = self._client.subscribe([(topic, SubscribeOptions(qos=1)) for topic in topics])
        return int(mid) if mid is not None else -1

    def publish(self, topic: str, payload: bytes) -> int:
        return int(self._client.publish(topic, payload, qos=1).mid)

    def loop(self, timeout: float) -> None:
        self._client.loop(timeout)

    def disconnect(self) -> None:
        self._client.disconnect()

    def _on_connect(self, _client: object, _userdata: object, _flags: object, reason: Any, _props: object) -> None:
        self.events.append(("connack", int(reason.value)))

    def _on_subscribe(self, _client: object, _userdata: object, mid: int, reasons: Any, _props: object) -> None:
        self.events.append(("suback", mid, [int(code.value) for code in reasons]))

    def _on_publish(self, _client: object, _userdata: object, mid: int, reason: Any, _props: object) -> None:
        self.events.append(("puback", mid, int(reason.value)))

    def _on_disconnect(self, _client: object, _userdata: object, flags: Any, _reason: object, _props: object) -> None:
        self.events.append(("disconnect", bool(flags.is_disconnect_packet_from_server)))

    def _on_message(self, _client: object, _userdata: object, message: Any) -> None:
        self.events.append(("message", str(message.topic), bytes(message.payload)))


CAPTURE = "CAPTURE"
CAPTURE_ACTION_NAME = "device.capture"  # the one name the Hub treats as a capture (isCaptureActionDefinition)
ACTION_TYPES = frozenset({"CONTROL", "CONFIG", "QUERY", "CALIBRATION", "EMERGENCY", CAPTURE, "SYSTEM"})


@dataclass(frozen=True, slots=True)
class Action:
    """One row of the device's action table (:meth:`~phytoworks.device.Device.register`): a name, its handler and
    whether the Hub hears of it.

    A ``remote`` action is declared to the Hub, so Console and Hub commands can run it, the way agent-rs declares
    one: ``parameters`` (a JSON Schema) goes unchanged for the Hub to check a command's params against, ``ui`` (Console
    placement: ``{"category", "order"?, "displayContext"?, "controlType"?}``) as ``metadata.ui`` when given, and
    ``timeout`` (whole seconds, 1 to 86400) as the definition's timeout, which Console waits for, and
    ``name_translation`` (``{"ko": "식물 상태 조회", "en": "Plant status"}``, locale to display name) as the
    definition's ``nameTranslation``, which Console shows instead of the action name; without it Console falls back
    to the name. A remote ``CAPTURE``
    must be named ``device.capture``. ``remote=False`` keeps an action local: the Hub never hears of it, only
    :meth:`~phytoworks.device.Device.submit` runs it and none of its runs is recorded. A ``CAPTURE`` handler gets a
    :class:`CaptureContext`, any other an :class:`ActionContext`; a handler returns ``None`` or a JSON object, the
    run's ``result``.
    """

    name: str
    handler: (
        Callable[[CaptureContext], Mapping[str, Any] | None] | Callable[[ActionContext], Mapping[str, Any] | None]
    ) = field(repr=False)
    action_type: str = "CONTROL"
    parameters: Mapping[str, Any] | None = field(default=None, repr=False)
    remote: bool = True
    timeout: int = 3600
    ui: Mapping[str, Any] | None = field(default=None, repr=False)
    name_translation: Mapping[str, str] | None = field(default=None, repr=False)


class ActionContext:
    """What a handler receives for one executor item: a Hub command (``trigger == "hub"``) or a local
    :meth:`Device.submit` (``"local"``).

    The handler reaches the Hub only through :attr:`device`. Cancellation is cooperative: poll :attr:`cancelled`
    or call :meth:`check` between steps (motor moves included -- the handler owns the safety of any actuation it
    drives). Past :attr:`deadline` or a cancel, the loop waits ``stop_grace`` seconds, then abandons the run.
    """

    def __init__(
        self,
        device: Device,
        execution_id: str,
        action: str,
        params: Mapping[str, Any],
        trigger: Literal["hub", "local"],
        *,
        deadline: float,
    ) -> None:
        self._owner = device
        self.device: _ScopedDevice = device._scope()
        """This item's handle to the Hub (sessions and uploads); revoked once the executor settles or abandons it."""
        self.execution_id = execution_id
        """The Hub execution id, or for a local run a UUID the SDK made (its Hub record id if the action is declared)."""
        self.action = action
        self.params = params
        self.trigger = trigger
        self.deadline = deadline
        """``time.monotonic()`` value after which the loop cancels this run."""
        self._cancelled = threading.Event()
        self.cancel_reason: str | None = None
        self.cancelled_at: float | None = None

    @property
    def manual_mode(self) -> bool | None:
        """The Hub's manual-mode flag as the device last applied it (``None`` while unknown). A Hub command runs
        either way; a handler that must not act on an unknown mode checks ``is None`` itself."""

        return self._owner.manual_mode

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def remaining(self) -> float:
        return max(0.0, self.deadline - monotonic())

    def wait(self, timeout: float) -> bool:
        """Sleep up to ``timeout`` seconds, waking early (and returning ``True``) on a cancel."""

        return self._cancelled.wait(timeout)

    def check(self) -> None:
        """Raise :class:`~phytoworks.errors.ActionCancelled` once the run was cancelled or its deadline passed."""

        if monotonic() >= self.deadline:
            self._cancel("deadline")
        if self.cancelled:
            raise ActionCancelled(f"{self.action} {self.execution_id} cancelled ({self.cancel_reason})")

    def _cancel(self, reason: str) -> None:
        if not self._cancelled.is_set():
            self.cancel_reason, self.cancelled_at = reason, monotonic()
            self._cancelled.set()


class CaptureContext(ActionContext):
    """An :class:`ActionContext` for a ``CAPTURE`` action, with :attr:`session`: the capture session to fill.

    It is the one a manual capture named, or one the loop created (linked to the Hub command; for a local item,
    linked to none). The handler starts it, uploads and completes it with :attr:`device`. Once a run is abandoned
    the loop settles the session itself and refuses the handler's further writes to it.
    """

    session: str = ""


def _context(
    device: Device,
    action: Action,
    execution_id: str,
    params: object,
    trigger: Literal["hub", "local"],
    deadline: float,
) -> ActionContext:
    kind = CaptureContext if action.action_type == CAPTURE else ActionContext
    values = params if isinstance(params, Mapping) else {}
    return kind(device, execution_id, action.name, values, trigger, deadline=deadline)


@dataclass(frozen=True, slots=True)
class RunResult:
    """How a local run ended: ``SUCCESS``, ``FAILED``, ``CANCELLED``, ``TIMEOUT`` or ``SKIPPED`` (manual mode)."""

    status: str
    error: str | None
    session: str | None


class LocalRun:
    """The handle :meth:`Device.submit` returns. A run of an action declared to the Hub also leaves a Hub record."""

    def __init__(self, supervisor: Supervisor, execution_id: str, action: str) -> None:
        self.execution_id = execution_id
        """A UUID the SDK made: the Hub record id of a declared action's run, never a Hub command's execution id."""
        self.action = action
        self._supervisor = supervisor
        self._result: Future[RunResult] = Future()

    def done(self) -> bool:
        return self._result.done()

    def wait(self, timeout: float | None = None) -> RunResult:
        """The run's result once it has ended; :class:`TimeoutError` if it is still queued or running."""

        return self._result.result(timeout)

    def cancel(self) -> None:
        """Cancel it the way a Hub cancel does: a queued run never starts, a running one sees ``ctx.cancelled``."""

        self._supervisor._cancel(self.execution_id, "cancelled locally")

    def _end(self, result: RunResult) -> None:
        self._result.set_result(result)


@dataclass(slots=True)
class _Entry:
    """One executor item in the outbox; for a Hub command, the latest result body is what any (re)publish sends.

    The outbox in insertion order is also the worker's queue (a queued entry is complete and runnable), so a
    command cancelled or timed out while queued leaves nothing behind once its result expires. A local item
    (``run`` set) is never published as a Hub result and leaves the outbox the moment it ends; one with an
    ``action_def_id`` (a declared action) leaves a record and a current value instead.
    """

    execution_id: str
    action_def_id: str
    trigger_source: str
    session: str | None
    action: Action | None = None  # None: a Hub command for no action this process registered
    ctx: ActionContext | None = None
    run: LocalRun | None = None
    state: str = "queued"  # queued -> running -> done; queued | running -> abandoned (the supervisor settles it)
    body: bytes = b""
    terminal: bool = False
    published_on: int | None = None  # connection number the body last went out on
    mid: int | None = None
    acked_at: float | None = None  # PUBACK time of the current body; None until then
    started_at: datetime | None = None  # wall clock when the worker started it; None if it never started
    result: dict[str, Any] | None = None  # what the handler returned


@dataclass(slots=True)
class _Queue:
    """What the supervisor owes the Hub on one route, oldest first (executor design D6): one request per tick, at most
    ``chunk(items)`` of the oldest items, the same ones again on every retry (but for those the cap pushes out), then
    ``period`` seconds before the next chunk starts. Both instances -- local action records and telemetry -- are written
    only under the outbox lock; ``waits_on_429`` says a 429 holds the chunk for its ``Retry-After`` instead of dropping it."""

    route: str
    noun: str
    limit: int
    chunk: Callable[[deque[tuple[Any, int]]], int]
    body: Callable[[list[Any]], Mapping[str, object]]
    waits_on_429: bool = False
    taken: Callable[[object], None] | None = None
    items: deque[tuple[Any, int]] = field(
        default_factory=deque
    )  # (item, serialized size), the first `sending` in flight
    sending: int = 0
    dropped: int = 0  # items the cap pushed out since the last warning
    attempts: int = 0
    retry_at: float = 0.0
    next_at: float = 0.0

    def push(self, item: Any, size: int) -> None:
        if len(self.items) >= self.limit:  # the oldest may be in the chunk being sent: its retry goes without
            self.items.popleft()
            self.sending = max(self.sending - 1, 0)
            self.dropped += 1
        self.items.append((item, size))


class Supervisor:
    """Runs on the thread that called ``listen()`` until ``Device.stop()`` or a fatal broker/credential error."""

    def __init__(
        self,
        device: Device,
        *,
        handler_timeout: float,
        stop_grace: float,
        link_factory: Callable[[str], Link] = PahoLink,
    ) -> None:
        self._device = device
        self._handler_timeout = handler_timeout
        self._stop_grace = stop_grace
        self._link_factory = link_factory
        self._agent = str(device.agent_id)
        self._commands = f"agents/{self._agent}/commands"
        self._cancel_prefix = f"agents/{self._agent}/commands/"
        self._results = f"agents/{self._agent}/results"
        self._sync = f"agents/{self._agent}/manual-mode/sync"
        # Both doors check these under the outbox lock: the worker has started, the executor is closing.
        self._open = False
        self._closing = False
        self._outbox: dict[str, _Entry] = {}
        self._outbox_lock = threading.Lock()
        self._queued = threading.Condition(self._outbox_lock)  # the worker waits on it for a queued entry
        self._retired = False  # set once, under the lock, when the loop ends: the worker takes nothing more
        self._settlements: deque[tuple[_Entry, str, str | None]] = deque()  # (entry, status, error), one per tick
        # Under the outbox lock: the queues of what the Hub has not taken (local action records, telemetry points), and
        # current values waiting for the next flush.
        self._action_records = _Queue("RECORD", "local action record(s)", RECORD_LIMIT, _chunk_length, _records_body)
        self._telemetry = _Queue(
            "TELEMETRY",
            "telemetry point(s)",
            TELEMETRY_LIMIT,
            _telemetry_chunk,
            _telemetry_body,
            waits_on_429=True,
            taken=_warn_rejected,
        )
        self._batch: list[dict[str, Any]] = []
        self._link: Link | None = None
        self._events: list[tuple[Any, ...]] = []
        self._connection = 0
        self._subscribed = False
        self._connack_at = 0.0
        self._quick_kicks = 0
        self._backoff = 1.0
        self._want_open = False
        self._beat_failed = False
        self._beat_retry_at = 0.0
        self._beat_backoff = 1.0
        self.worker = threading.Thread(target=self._work, name="phytoworks-action", daemon=True)

    @property
    def _records(self) -> deque[tuple[Any, int]]:
        return self._action_records.items

    @property
    def _sending(self) -> int:
        return self._action_records.sending

    # ------------------------------------------------------------------
    # Public surface (through Device)
    # ------------------------------------------------------------------

    def run(self, endpoint: MqttEndpoint, slot: MqttSlot) -> None:
        with self._queued:
            self._open = True  # the local door opens with the worker, whatever the broker does
            self.worker.start()
        sign_off = True
        try:
            self._serve(endpoint, slot)
        except (SessionTakenOver, CredentialRevoked):
            sign_off = False  # the lease is another process's now, or the key is gone (design D6)
            raise
        finally:
            self._shutdown(sign_off=sign_off)

    def submit(self, action: Action, params: Mapping[str, Any]) -> LocalRun:
        """The local door (:meth:`Device.submit`): check and insert in one outbox-lock section, like a command."""

        if threading.current_thread() is self.worker:
            raise RuntimeError("submit() from the executor's own worker would wait on itself; return instead")
        execution = str(uuid.uuid4())
        run = LocalRun(self, execution, action.name)
        declared = next((defined for defined, remote in self._device._remote.items() if remote is action), "")
        entry = _Entry(execution, declared, "AGENT", None, action=action, run=run)  # "" (local only): never recorded
        entry.ctx = _context(self._device, action, execution, params, "local", monotonic() + self._deadline(action))
        with self._queued:
            if not self._open:
                raise NotServing("listen() has not started its worker yet")
            if self._closing or self._device._stop_requested:  # a stop() the supervisor has not acted on yet
                raise DeviceStopped("listen() is stopping; it takes no new work")
            if self._device.manual_mode is True:
                raise ManualModeActive("the Hub reports this device in manual mode; local runs are refused")
            if len(self._outbox) >= OUTBOX_LIMIT:
                raise DeviceBusy(f"the executor already holds {OUTBOX_LIMIT} items")
            self._outbox[execution] = entry
            self._queued.notify()
        return run

    def _deadline(self, action: Action) -> float:
        """Seconds a run may take: the action's declared timeout, never past the process-wide ``handler_timeout``."""

        return min(float(action.timeout), self._handler_timeout)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _serve(self, endpoint: MqttEndpoint, slot: MqttSlot) -> None:
        while not self._device._stop_requested:
            code = self._connect(endpoint, slot)
            if code in _BAD_CREDENTIALS:
                slot = self._rediscover(slot)
            elif code == 0:
                self._session()
            # One rule for every way an attempt ends short of a fatal error; only a stable connection resets it.
            self._idle(self._next_backoff())

    def _connect(self, endpoint: MqttEndpoint, slot: MqttSlot) -> int | None:
        """One attempt on a new client; the CONNACK reason code, or ``None`` if none arrived."""

        self._drop_link()
        self._connection += 1
        self._events = []
        link = self._link_factory(f"agent-{self._agent}")
        self._link = link
        try:
            link.connect(endpoint, slot)
        except (OSError, ValueError):
            self._link = None
            return None
        deadline = monotonic() + CONNACK_DEADLINE
        while monotonic() < deadline and not self._device._stop_requested:
            self._pump(min(LOOP_STEP, max(0.0, deadline - monotonic())))
            for event in self._take("connack"):
                self._connack_at = monotonic()
                if event[1] != 0:
                    self._drop_link()
                return int(event[1])
            if self._link is None:
                return None
        self._drop_link()
        return None

    def _session(self) -> None:
        """Subscribe, open the channel, then serve until the connection drops or ``stop()``."""

        link = self._link
        if link is None:
            return
        link.subscribe([self._commands, f"{self._commands}/+/cancel", self._sync])
        deadline = monotonic() + SUBACK_DEADLINE
        granted: list[int] | None = None
        while granted is None and monotonic() < deadline and not self._device._stop_requested:
            self._pump(LOOP_STEP)
            if self._link is None:
                self._lost(from_server=self._last_disconnect_from_server)
                return
            for event in self._take("suback"):
                granted = event[2]
        if granted is None:
            self._drop_link()
            return
        if len(granted) < 2 or any(code >= 0x80 for code in granted[:2]):
            raise SubscribeDenied(f"the broker refused this device's command topics (SUBACK {granted})")
        # A refused manual-mode/sync is not fatal: every successful heartbeat still carries the mode (design §8).
        self._subscribed = True  # the next tick opens the channel
        while not self._device._stop_requested:
            self._pump(LOOP_STEP)
            if self._link is None:
                self._lost(from_server=self._last_disconnect_from_server)
                return
            if monotonic() - self._connack_at > TAKEOVER_WINDOW:
                self._quick_kicks, self._backoff = 0, 1.0

    def _lost(self, *, from_server: bool) -> None:
        if from_server and monotonic() - self._connack_at <= TAKEOVER_WINDOW:
            self._quick_kicks += 1
            if self._quick_kicks >= 2:
                raise SessionTakenOver("another connection keeps taking this device's broker session")
        else:
            self._quick_kicks = 0

    def _rediscover(self, slot: MqttSlot) -> MqttSlot:
        """Refused credentials: re-discover for a fresh slot at most once per cooldown (redesign §2 F4), the one the
        Device shares with its HTTP 401 path; inside it, the cached slot. A key the Hub already refused on that path ends
        the loop at once instead of waiting the cooldown out (a flag set once until the next adoption, read unlocked)."""

        if self._device._key_refused:
            raise CredentialRevoked("the broker and the Hub both refused this device's key")
        try:
            return self._device._mqtt_slot(supervised=True, rediscover=True)
        except AuthError as refused:
            if refused.status_code == 401:
                raise CredentialRevoked("the broker and the Hub both refused this device's key") from None
            return slot
        except MqttUnavailable:
            raise
        except PWSError:
            return slot  # the Hub is unreachable; try the cached slot again after the backoff

    def _next_backoff(self) -> float:
        delay = self._backoff
        self._backoff = min(self._backoff * 2, BACKOFF_MAX)
        return delay

    def _drop_link(self) -> None:
        link, self._link = self._link, None
        self._subscribed = False
        if link is not None:
            try:
                link.disconnect()
            except (OSError, ValueError):
                pass

    # ------------------------------------------------------------------
    # One supervisor step
    # ------------------------------------------------------------------

    _last_disconnect_from_server = False

    def _pump(self, timeout: float) -> None:
        """Run the network for up to ``timeout`` s, then handle what arrived and do the periodic work."""

        link = self._link
        if link is not None:
            try:
                link.loop(timeout)
            except (OSError, ValueError):
                link.events.append(("disconnect", False))
            self._events.extend(link.events)
            link.events.clear()
            for event in self._take("message", "puback", "disconnect"):
                if event[0] == "message":
                    self._receive(event[1], event[2])
                elif event[0] == "puback":
                    self._acked(event[1], event[2])
                else:  # the tick below then closes the channel before it sends any other heartbeat
                    self._last_disconnect_from_server = bool(event[1])
                    self._link = None
                    self._subscribed = False
        else:
            # A plain sleep, never an Event: Device.stop() may run in a signal handler on this very thread, and an
            # Event's wait holds the lock its set() takes. Callers sleep at most LOOP_STEP, but a stop is seen only
            # after the blocking work around that sleep too: a synchronous broker connect, or the tick below, whose
            # one Hub call may begin after the stop.
            sleep(timeout)
        self._tick()

    def _take(self, *kinds: str) -> list[tuple[Any, ...]]:
        taken = [event for event in self._events if event[0] in kinds]
        self._events[:] = [event for event in self._events if event[0] not in kinds]
        return taken

    def _idle(self, seconds: float) -> None:
        deadline = monotonic() + seconds
        while not self._device._stop_requested and (remaining := deadline - monotonic()) > 0:
            self._pump(min(LOOP_STEP, remaining))

    def _tick(self) -> None:
        """Periodic work with at most one Hub call, so the broker is pumped between any two of them."""

        self._police()
        if not self._liveness():
            if self._settlements:
                self._settle_next()
            elif not self._closing and not self._send_records():  # nothing lengthens the stop: what is left is dropped
                self._send(self._telemetry)  # one Hub call a tick: records first
        self._flush()
        self._expire()

    def _accepting(self) -> bool:
        """The channel is open only while subscribed, not stopping and below the outbox limit."""

        with self._outbox_lock:
            return self._subscribed and not self._closing and len(self._outbox) < OUTBOX_LIMIT

    def _liveness(self) -> bool:
        """Send the heartbeat a channel change or the interval calls for; ``True`` if it tried one."""

        want = self._accepting()
        if want != self._want_open:  # a change goes out at once, ahead of any failure backoff
            self._want_open, self._beat_retry_at = want, 0.0
        now = monotonic()
        device = self._device
        if now < self._beat_retry_at:
            return False
        if device._channel_open == want and not self._beat_failed and not device._beat_due():
            return False
        try:
            if device._channel_open != want:
                device._set_channel(want, supervised=True)
            else:
                device._beat(online=True, who="loop", supervised=True)
        except PWSError:
            self._beat_failed = True
            self._beat_retry_at = now + self._beat_backoff
            self._beat_backoff = min(self._beat_backoff * 2, BACKOFF_MAX)
            return True
        self._beat_failed, self._beat_backoff = False, 1.0
        return True

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _receive(self, topic: str, payload: bytes) -> None:
        try:
            envelope = json.loads(payload)
        except (ValueError, RecursionError):  # nesting past the parser's limit is a bad message, not a fatal one
            return
        # The Hub publishes through a NestJS ClientProxy: {"pattern": ..., "data": <command>}, the shape agent-rs
        # requires too (NestJsMessage in its mqtt router). Results go back as the bare ActionResult.
        message = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(message, dict):
            return
        if topic == self._commands:
            self._command(message)
        elif topic == self._sync:
            self._manual_sync(message)
        elif topic.startswith(self._cancel_prefix) and topic.endswith("/cancel"):
            execution = topic[len(self._cancel_prefix) : -len("/cancel")]
            self._cancel(execution, "cancelled by the Hub")

    def _command(self, command: dict[str, Any]) -> None:
        execution, action = command.get("executionId"), command.get("actionDefId")
        if not isinstance(execution, str) or not execution or not isinstance(action, str) or not action:
            return
        params = command.get("params")
        session = params.get("captureSessionId") if isinstance(params, Mapping) else None
        trigger = command.get("triggerSource")
        entry = _Entry(
            execution,
            action,
            trigger if isinstance(trigger, str) else "MANUAL",
            session if isinstance(session, str) and session else None,
            action=self._device._remote.get(action),
        )
        runnable = entry.action is not None
        if entry.action is not None:
            entry.ctx = _context(
                self._device, entry.action, execution, params, "hub", monotonic() + self._deadline(entry.action)
            )
        # One section with the duplicate, limit and closing checks, the same lock submit() inserts under.
        with self._queued:
            known = self._outbox.get(execution)
            if known is not None:  # the Hub re-sends until it sees RUNNING: answer with the latest result
                known.published_on, known.acked_at = None, None  # held again until this answer's own PUBACK
                return
            full = len(self._outbox) >= OUTBOX_LIMIT
            if not full:
                # Complete the entry before the worker can see it: it runs any queued entry in the outbox.
                if self._closing:
                    entry.state, entry.ctx = "done", None
                    self._set_body(entry, "CANCELLED", "device stopping")
                elif not runnable:
                    entry.state = "done"
                    self._set_body(entry, "FAILED", "not an action this device registered")
                else:
                    self._set_body(entry, "RUNNING", None)
                self._outbox[execution] = entry
                self._queued.notify()
        if full:  # sent before the closed channel reached the Hub: answer once, hold nothing
            if self._link is not None and self._subscribed:
                self._link.publish(self._results, _body(entry, "FAILED", "device busy"))

    def _manual_sync(self, message: Mapping[str, Any]) -> None:
        """Apply this device's entry of a ``manual-mode/sync`` on receipt, as agent-rs does: the Hub sends
        ``{"manualModes": [{"deviceId", "enabled", "timestamp"}]}``; another device's entry is not ours."""

        own, modes = self._device.device_id, message.get("manualModes")
        if not own or not isinstance(modes, list):
            return
        for mode in modes:
            if isinstance(mode, Mapping) and mode.get("deviceId") == own and isinstance(mode.get("enabled"), bool):
                self._device.manual_mode = mode["enabled"]

    def _cancel(self, execution: str, reason: str) -> None:
        with self._outbox_lock:
            entry = self._outbox.get(execution)
            if entry is None or entry.state not in ("queued", "running"):
                return
            if entry.ctx is not None:
                entry.ctx._cancel(reason)
            if entry.state == "queued" and entry.ctx is not None:  # never started: the supervisor settles it
                entry.ctx.device._revoke()
                entry.state = "abandoned"
                self._settlements.append((entry, _stopped(entry.ctx), reason))

    def _police(self) -> None:
        """Cancel commands past their deadline, queued ones included (the worker may never come back for them);
        abandon running ones that ignore a cancel for ``stop_grace`` seconds."""

        now = monotonic()
        with self._outbox_lock:
            late = [
                entry.execution_id
                for entry in self._outbox.values()
                if entry.state == "queued" and entry.ctx is not None and now >= entry.ctx.deadline
            ]
            running = [entry for entry in self._outbox.values() if entry.state == "running" and entry.ctx]
        for execution in late:
            self._cancel(execution, "deadline")
        for entry in running:
            ctx = entry.ctx
            if ctx is None:
                continue
            if now >= ctx.deadline:
                ctx._cancel("deadline")
            if ctx.cancelled_at is not None and now - ctx.cancelled_at >= self._stop_grace:
                self._abandon(entry, ctx)

    def _abandon(self, entry: _Entry, ctx: ActionContext) -> None:
        with self._outbox_lock:  # the worker attaches a session it creates under this lock too
            if entry.state != "running":
                return
            entry.state = "abandoned"
            ctx.device._revoke()
            if entry.session:
                self._device._fence(entry.session)
            self._settlements.append((entry, _stopped(ctx), ctx.cancel_reason))

    def _settle_next(self) -> None:
        entry, status, error = self._settlements.popleft()
        settled = self._settle(entry.session, "cancelled", f"settled by the receive loop ({error})", supervised=True)
        self._finish(entry, settled if settled in ("SUCCESS", "FAILED") else status, error)

    def _send_records(self) -> bool:
        """One request of local records (agent-rs's 10 s flush; the Hub's ACTION_RECORD allows 30 a minute)."""

        return self._send(self._action_records)

    def _send(self, queue: _Queue) -> bool:
        """One request of ``queue``: the oldest items that fit one body, the same ones on every retry of it; a new chunk
        ``RECORD_PERIOD`` seconds after the last request of the queue ended, so chunk POSTs start at least that far
        apart however long a token refresh holds one back, or if the cap pushed a retried chunk out. ``True`` if it
        made a Hub call."""

        now = monotonic()
        if now < queue.retry_at:
            return False
        dropped = 0
        with self._outbox_lock:
            if not queue.sending:
                if not queue.items or now < queue.next_at:
                    return False
                queue.sending, queue.attempts = queue.chunk(queue.items), 0
                dropped, queue.dropped = queue.dropped, 0
            items = [item for item, _size in islice(queue.items, queue.sending)]
        if dropped:
            _logger.warning("dropped the %d oldest %s: at most %d wait for the Hub", dropped, queue.noun, queue.limit)
        try:
            response = self._device._call(queue.route, queue.body(items), who="loop", supervised=True)
            if queue.taken is not None:
                queue.taken(response)
        except PWSError as exc:
            if queue.waits_on_429 and isinstance(exc, RateLimitError):
                wait = exc.retry_after if exc.retry_after is not None else TELEMETRY_THROTTLE_DEFAULT
                # counted from the answer, as agent-rs does; the same chunk goes again and no attempt is spent
                queue.retry_at = monotonic() + min(wait, TELEMETRY_THROTTLE_MAX)
                return True
            queue.attempts += 1
            status = exc.status_code
            if (status is None or status in _RETRYABLE_RECORD_STATUS) and queue.attempts <= len(RECORD_RETRY_DELAYS):
                queue.retry_at = now + RECORD_RETRY_DELAYS[queue.attempts - 1]
                return True
            _logger.warning(
                "dropped %d %s the Hub did not take (%s)",
                len(items),
                queue.noun,
                f"HTTP {status}" if status is not None else type(exc).__name__,
            )
        finally:
            queue.next_at = monotonic() + RECORD_PERIOD
        with self._outbox_lock:
            for _taken in range(queue.sending):
                queue.items.popleft()
            queue.sending, queue.retry_at = 0, 0.0
        return True

    def enqueue_telemetry(
        self, points: list[tuple[tuple[str, dict[str, Any]], int]], scope: _ScopedDevice | None = None
    ) -> None:
        """The telemetry door (:meth:`Device.telemetry` from any thread, ``ctx.device.telemetry``): hold the points
        ((topic id, point), serialized size) for the next chunk and return. Not a Hub call, and neither the outbox
        limit nor manual mode applies. A handler's ``scope`` must still be live when the points go in: that check and the
        push are one step under the outbox lock (where a run is abandoned) and the in-flight condition (where its
        handle is revoked), so a run abandoned while its input was checked queues nothing."""

        with self._outbox_lock:
            if self._closing or self._retired:
                raise DeviceStopped("listen() is stopping; it takes no new telemetry")
            if scope is not None:
                with self._device._in_flight:
                    scope._live()
            for item, size in points:
                self._telemetry.push(item, size)

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _work(self) -> None:
        while (entry := self._next()) is not None:
            if entry.state == "skipped":
                self._finish(entry, "SKIPPED", "manual mode")
            else:
                self._run(entry)

    def _next(self) -> _Entry | None:
        """The oldest queued item, now running -- or ``skipped``: a local item meeting manual mode at the moment
        it would start (Hub commands still run, as agent-rs runs MANUAL ones); ``None`` once the loop has ended."""

        with self._queued:
            while not self._retired:
                entry = next((entry for entry in self._outbox.values() if entry.state == "queued"), None)
                if entry is not None:
                    skip = entry.run is not None and self._device.manual_mode is True
                    entry.state = "skipped" if skip else "running"
                    entry.started_at = None if skip else datetime.now(UTC)
                    return entry
                self._queued.wait()
        return None

    def _run(self, entry: _Entry) -> None:
        ctx, action = entry.ctx, entry.action
        if ctx is None or action is None:
            return
        outcome: str | None = None
        try:
            ctx.check()  # a command whose deadline passed while it was queued never starts
            if isinstance(ctx, CaptureContext):  # only a capture has a session to fill
                session = self._attach(entry, ctx)
                if session is None:
                    return
                ctx.session = session
                ctx.check()
            entry.result = _result(action.name, cast("Callable[[ActionContext], object]", action.handler)(ctx))
        except ActionCancelled:
            outcome = "cancelled"
        except Exception as exc:  # noqa: BLE001 - any handler failure becomes a FAILED result
            outcome = f"handler raised {type(exc).__name__}"
        ctx.device._revoke()  # threads the handler left behind lose the Hub with it
        with self._outbox_lock:
            if entry.state != "running":
                return  # abandoned: the supervisor already settled and answered
        if outcome is None and ctx.cancelled:
            outcome = "cancelled"
        status = self._settle(entry.session, outcome, outcome or "handler returned", supervised=False)
        if status is None:  # no session decided it: a capture left unfinished fails, any other action's return succeeds
            capture = isinstance(ctx, CaptureContext)
            status = _stopped(ctx) if outcome == "cancelled" else "FAILED" if outcome or capture else "SUCCESS"
        with self._outbox_lock:
            if entry.state != "running":
                return
            entry.state = "done"
        error = None if status == "SUCCESS" else (ctx.cancel_reason if outcome == "cancelled" else outcome)
        self._finish(entry, status, error or "the handler left the session unfinished")

    def _attach(self, entry: _Entry, ctx: ActionContext) -> str | None:
        """The session to fill: the command's, or a new one linked to it; ``None`` if abandoned meanwhile."""

        if entry.session is not None:
            return entry.session
        name = ctx.params.get("sessionName")
        if entry.run is not None:  # a local run is no Hub execution: the session names none (design D4)
            default, linked = f"Local capture {entry.execution_id[:8]}", None
        else:
            default, linked = f"Remote capture {entry.execution_id[:8]}", entry.execution_id
        session = str(
            self._device._create_session(name if isinstance(name, str) and name else default, None, linked, "loop")[
                "id"
            ]
        )
        with self._outbox_lock:  # the same lock under which _abandon fences entry.session
            if entry.state == "running":
                entry.session = session
                return session
        # Abandoned while the Hub was creating it: only this thread knows the session, so it settles it, and no
        # result will ever name it for _expire to forget.
        self._device._fence(session)
        try:
            self._settle(session, "cancelled", "capture abandoned before it started", supervised=False)
        finally:
            self._device._forget(session)
        return None

    def _settle(self, session: str | None, outcome: str | None, reason: str, *, supervised: bool) -> str | None:
        """Bring the session to a terminal state; return the result status it implies, or ``None`` to decide."""

        if not session:
            return None
        known = self._device._session_status(session)
        if known == "COMPLETED":
            return "SUCCESS"
        if known in _TERMINAL_SESSION:
            return "CANCELLED" if known == "CANCELLED" else "FAILED"
        if outcome == "cancelled":
            # The agent cancel route takes PLANNED and IN_PROGRESS and leaves the execution to this loop's result;
            # a session failure would fail the execution first (Hub failIfInFlight). agent-rs settles a cancel so too.
            writes: tuple[str, ...] = ("SESSION_CANCEL",)
        elif known == "IN_PROGRESS":
            writes = ("SESSION_FAIL",)
        else:
            writes = ("SESSION_CANCEL", "SESSION_FAIL")
        for write in writes:
            try:
                self._device._settle_write(write, session, reason, supervised=supervised)
                break
            except ValidationError:
                continue  # wrong state for this write (started elsewhere): try the next one
            except PWSError:
                break  # unreachable Hub: its reaper closes the session
        return None

    # ------------------------------------------------------------------
    # Outbox
    # ------------------------------------------------------------------

    def _finish(self, entry: _Entry, status: str, error: str | None) -> None:
        with self._outbox_lock:
            if entry.state in ("queued", "running", "skipped"):
                entry.state = "done"
            if entry.run is None:
                self._set_body(entry, status, error)
                return
            if self._outbox.get(entry.execution_id) is not entry:
                return  # already ended: a local run ends once
            del self._outbox[entry.execution_id]  # a local item ends here; no Hub result is published
        if entry.ctx is not None:
            entry.ctx.device._revoke()
        if entry.session:
            self._device._forget(entry.session)
        error = None if status == "SUCCESS" else error
        if entry.action_def_id and status != "SKIPPED":  # a declared action's run (design §2, Q1: no SKIPPED rows)
            self._keep(entry, status, error)
        entry.run._end(RunResult(status, error, entry.session))

    def _keep(self, entry: _Entry, status: str, error: str | None) -> None:
        """Queue a local run's record for the Hub and, for a run that ended ``SUCCESS``/``FAILED``, its current value.

        The record is built to pass the Hub's checks, as agent-rs builds its own, since one record the Hub refuses
        fails every record of its request: params are copied as the JSON they are now (a retry sends the same bytes
        whatever the caller does to them later), a field past the Hub's limits becomes agent-rs's marker, the error
        is cut to 4 KiB and the span to 0..86,400 s, keeping the end."""

        completed = datetime.now(UTC)
        completed = completed.replace(microsecond=completed.microsecond // 1000 * 1000)  # what _stamp writes
        started = completed - min(max(completed - (entry.started_at or completed), timedelta(0)), _RECORD_SPAN)
        try:
            params = json.loads(_json(dict(entry.ctx.params))) if entry.ctx is not None else {}
            record = {
                "executionId": entry.execution_id,
                "actionDefId": entry.action_def_id,
                "source": "AGENT",
                "captureSessionId": entry.session,
                "status": status,
                "parameters": _bounded(params),
                "result": _bounded(entry.result),
                "error": None if error is None else error.encode()[:_RECORD_ERROR_BYTES].decode(errors="ignore"),
                "startedAt": _stamp(started),  # never started: a zero-length run
                "completedAt": _stamp(completed),
            }
            size: int | None = len(_json(record))
        except (TypeError, ValueError, RecursionError):
            size = None
        value = None
        if status in ("SUCCESS", "FAILED"):
            value = {
                "executionId": entry.execution_id,
                "actionDefId": entry.action_def_id,
                "captureSessionId": entry.session,
                "triggerSource": "AGENT",
                "success": status == "SUCCESS",
                "status": status,
                "result": entry.result,
                "error": error,
                "timestamp": _stamp(completed),
            }
        with self._outbox_lock:
            if value is not None:
                self._batch.append(value)
            if size is None:
                _logger.warning("dropped the record of local run %s: its params are not JSON", entry.execution_id)
                return
            self._action_records.push(record, size)

    def _set_body(self, entry: _Entry, status: str, error: str | None) -> None:
        """Outbox lock held: the body any (re)publish of this Hub command sends from now on."""

        entry.body = _body(entry, status, error)
        entry.terminal = status != "RUNNING"
        entry.acked_at, entry.published_on, entry.mid = None, None, None

    def _flush(self) -> None:
        """Publish every result not yet sent on this connection; only after SUBACK (redesign §2 F3). Local current
        values go out once, as agent-rs's ``results/batch`` (QoS 1, no retry); with no subscribed link they are dropped
        (a current value is not history)."""

        link = self._link
        with self._outbox_lock:
            values, self._batch = self._batch, []
        if link is None or not self._subscribed:
            return
        for start in range(0, len(values), _BATCH_LIMIT):
            link.publish(f"{self._results}/batch", _batch_body(self._agent, values[start : start + _BATCH_LIMIT]))
        with self._outbox_lock:
            due = [
                entry
                for entry in self._outbox.values()
                if entry.run is None and entry.acked_at is None and entry.published_on != self._connection
            ]
        for entry in due:
            with self._outbox_lock:
                body = entry.body
            mid = link.publish(self._results, body)
            with self._outbox_lock:
                if entry.body is body:
                    entry.published_on, entry.mid = self._connection, mid

    def _acked(self, mid: int, code: int) -> None:
        with self._outbox_lock:
            for entry in self._outbox.values():
                if entry.mid == mid and entry.published_on == self._connection:
                    if code >= 0x80:
                        raise SubscribeDenied(f"the broker refused this device's results topic (PUBACK {code:#x})")
                    entry.acked_at = monotonic()
                    return

    def _expire(self) -> None:
        """Forget a terminal result, and its session's cached state, 60 s after its PUBACK; one never acknowledged stays."""

        now = monotonic()
        with self._outbox_lock:
            for execution in [
                execution
                for execution, entry in self._outbox.items()
                if entry.terminal and entry.acked_at is not None and now - entry.acked_at >= RESULT_RETENTION
            ]:
                session = self._outbox.pop(execution).session
                if session:
                    self._device._forget(session)

    def _pending(self) -> bool:
        with self._outbox_lock:
            return any(entry.run is None and entry.acked_at is None for entry in self._outbox.values())

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def _shutdown(self, *, sign_off: bool) -> None:
        """Close both doors, cancel queued work, give the running capture its grace, flush, disconnect, then sign
        off and retire the Device in one step (design D5); after a takeover or a revoked key, or with a request still
        under way ``stop_grace`` seconds into retirement, retire only."""

        with self._queued:  # no door admits once this section ends
            self._closing = True
        self._device._enter_closing()  # after the outbox lock is released: the two are never held together
        try:
            self._liveness()  # closing: the channel goes first
            with self._outbox_lock:
                queued = [entry for entry in self._outbox.values() if entry.state == "queued"]
            for entry in queued:
                self._cancel(entry.execution_id, "device stopping")
            with self._outbox_lock:
                running = [entry for entry in self._outbox.values() if entry.state == "running" and entry.ctx]
            for entry in running:
                if entry.ctx is not None:
                    entry.ctx._cancel("device stopping")
            deadline = monotonic() + self._stop_grace + LOOP_STEP
            while (self._running() or self._settlements) and monotonic() < deadline:
                self._pump(LOOP_STEP)
            while self._settlements:  # out of time: answer without the Hub write; its reaper closes the session
                entry, status, error = self._settlements.popleft()
                self._finish(entry, status, error)
            deadline = monotonic() + FLUSH_DEADLINE
            while self._link is not None and self._subscribed and self._pending() and monotonic() < deadline:
                self._pump(LOOP_STEP)
        finally:
            self._drop_link()
            with self._queued:  # a worker stuck in a handler sees it only when it returns; it is a daemon thread
                self._retired = True
                self._queued.notify()
                unended = [entry for entry in self._outbox.values() if entry.run is not None]
            for entry in unended:  # a fatal exit skipped the drain: every local handle still ends
                if entry.ctx is not None:
                    entry.ctx._cancel("device stopping")
                self._finish(entry, "CANCELLED", "device stopping")
            self._report_unsent()
            self._device._retire(sign_off=sign_off, grace=self._stop_grace)

    def _report_unsent(self) -> None:
        """One WARNING per queue at the stop for what is left and what the cap dropped since the last chunk."""

        with self._outbox_lock:
            counts = [
                (queue.noun, len(queue.items), queue.dropped) for queue in (self._action_records, self._telemetry)
            ]
        for noun, unsent, dropped in counts:
            if unsent or dropped:
                _logger.warning("listen() stopped with %d %s not sent to the Hub and %d dropped", unsent, noun, dropped)

    def _running(self) -> bool:
        with self._outbox_lock:
            return any(entry.state == "running" for entry in self._outbox.values())


def _stopped(ctx: ActionContext) -> str:
    return "TIMEOUT" if ctx.cancel_reason == "deadline" else "CANCELLED"


def _body(entry: _Entry, status: str, error: str | None) -> bytes:
    body = {
        "executionId": entry.execution_id,
        "actionDefId": entry.action_def_id,
        "captureSessionId": entry.session,
        "triggerSource": entry.trigger_source,
        "success": status in ("RUNNING", "SUCCESS"),
        "status": status,
        "result": entry.result if status != "RUNNING" else None,
        "error": error if status not in ("RUNNING", "SUCCESS") else None,
        "timestamp": _stamp(datetime.now(UTC)),
    }
    return json.dumps(body, separators=(",", ":")).encode()


def _batch_body(agent: str, values: list[dict[str, Any]]) -> bytes:
    """agent-rs's batch envelope; ``deviceId`` is the agent id, the one the topic names (L4 design §3)."""

    body = {"deviceId": agent, "batchType": "LOCAL", "results": values, "timestamp": _stamp(datetime.now(UTC))}
    return json.dumps(body, separators=(",", ":")).encode()


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json(value: object) -> bytes:
    """The bytes httpx sends for ``json=value``: the size a request body is measured in."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _result(action: str, value: object) -> dict[str, Any] | None:
    """A handler's return as the run's ``result``: ``None`` or a JSON object, anything else ``None`` with a WARNING
    (the run's status stays what it was)."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        try:
            return cast("dict[str, Any]", json.loads(_json(dict(value))))
        except (TypeError, ValueError, RecursionError):
            pass
    _logger.warning(
        "the %s handler returned %s, not None or a JSON object: its result is null", action, type(value).__name__
    )
    return None


def _nests_within(value: object, levels: int) -> bool:
    """The Hub's depth rule: objects and arrays at most ``levels`` deep, the value itself being level 1."""

    if isinstance(value, Mapping):
        return levels > 0 and all(_nests_within(item, levels - 1) for item in value.values())
    if isinstance(value, list | tuple):
        return levels > 0 and all(_nests_within(item, levels - 1) for item in value)
    return True


def _bounded(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """A ``parameters``/``result`` object as the Hub takes it: past 32 levels or 32 KiB it is agent-rs's marker
    ``{"omitted": "exceeds_record_limits", "bytes": N}``, so the record still reports the run."""

    if value is None:
        return None
    size = _hub_json_bytes(value)
    if size <= _RECORD_JSON_BYTES and _nests_within(value, _RECORD_JSON_DEPTH):
        return value
    return {"omitted": "exceeds_record_limits", "bytes": size}


def _hub_json_bytes(value: object) -> int:
    """UTF-8 bytes of ``JSON.stringify`` of the parsed value, which is what the Hub limits (agent-rs ``hub_json``):
    strings and structure print as ``_json`` prints them, numbers as JavaScript prints an f64 (``1e20`` is
    ``100000000000000000000``, ``1.0`` is ``1``). ``value`` is parsed JSON; walked without recursion."""

    size, stack = 0, [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            size += 1 + max(len(item), 1) + sum(len(_json(key)) + 1 for key in item)
            stack.extend(item.values())
        elif isinstance(item, list):
            size += 1 + max(len(item), 1)
            stack.extend(item)
        elif isinstance(item, str):
            size += len(_json(item))
        elif item is None or item is True:
            size += 4
        elif item is False:
            size += 5
        else:
            size += _js_number_length(cast("int | float", item))
    return size


def _js_number_length(number: float) -> int:
    """Length of ECMAScript ``Number::toString``: the shortest round-trip digits (``repr``) laid out by its rules."""

    try:
        x = float(number)  # JavaScript parses every number to an f64
    except OverflowError:
        x = math.inf
    if not math.isfinite(x):
        return 4  # JSON.stringify prints Infinity as null
    if x == 0:
        return 1
    # repr's digits read as text: a decimal.Decimal would round them to the thread's context, which a handler may set.
    mantissa, _e, exponent = repr(abs(x)).partition("e")
    whole, _point, fraction = mantissa.partition(".")
    significant = (whole + fraction).lstrip("0")
    digits = significant.rstrip("0")
    k, n = len(digits), len(whole) - (len(whole + fraction) - len(significant)) + int(exponent or 0)
    if k <= n <= 21:
        length = n
    elif 0 < n <= 21:
        length = k + 1
    elif -6 < n <= 0:
        length = 2 - n + k
    else:  # d[.ddd]e±x
        length = (1 if k == 1 else k + 1) + 2 + len(str(abs(n - 1)))
    return int(x < 0) + length


def _chunk_length(records: deque[tuple[dict[str, Any], int]]) -> int:
    """How many of the oldest records fit one request: at most ``RECORD_CHUNK`` and ``RECORD_CHUNK_BYTES`` of body
    (``{"records":[...]}``); always at least one, since a record within the limits is far below the byte cap."""

    count, size = 1, len('{"records":[]}') + records[0][1]
    for _record, length in islice(records, 1, RECORD_CHUNK):
        if size + 1 + length > RECORD_CHUNK_BYTES:
            break
        size += 1 + length
        count += 1
    return count


def _records_body(records: list[Any]) -> dict[str, Any]:
    return {"records": records}


def _telemetry_body(points: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """``telemetry/batch``'s body: the points grouped by topic, each topic's in the order given."""

    topics: dict[str, list[dict[str, Any]]] = {}
    for topic, point in points:
        topics.setdefault(topic, []).append(point)
    return {"topics": [{"topicId": topic, "dataPoints": values} for topic, values in topics.items()]}


def _telemetry_chunk(points: deque[tuple[tuple[str, dict[str, Any]], int]]) -> int:
    """How many of the oldest points fit one request: at most ``TELEMETRY_TOPICS`` topics, ``TELEMETRY_POINTS`` points
    per topic and ``TELEMETRY_BODY_BYTES`` of body (``_json`` of what ``_telemetry_body`` builds, counted exactly);
    always at least one."""

    per_topic: dict[str, int] = {}
    size = len(_json({"topics": []}))
    count = 0
    for (topic, _point), length in points:
        grown = size + 1 + length  # the comma before it and the point
        if topic not in per_topic:
            if len(per_topic) == TELEMETRY_TOPICS:
                break
            grown += len(_json({"topicId": topic, "dataPoints": []})) + (1 if per_topic else 0) - 1
        elif per_topic[topic] == TELEMETRY_POINTS:
            break
        if count and grown > TELEMETRY_BODY_BYTES:
            break
        per_topic[topic] = per_topic.get(topic, 0) + 1
        size, count = grown, count + 1
    return count


def _warn_rejected(response: object) -> None:
    """The Hub takes a batch whole or not at all, but may refuse single points of it (a stale or future time): say so."""

    rejected = response.get("totalRejected") if isinstance(response, Mapping) else None
    if isinstance(rejected, int) and rejected > 0:
        _logger.warning("the Hub rejected %d telemetry point(s) of a batch it took", rejected)
