"""Device persona: a field device calls the Hub's agent routes with its own DEVICE key.

Plain calls are HTTP only and start no thread: what to capture and when is the caller's code (a cron job, a
motor sequence); this module keeps the Hub's credential and call-order contract. :meth:`Device.listen` is the
one exception: it blocks the calling thread on the device's one action executor -- Hub commands over MQTT and
:meth:`Device.submit` from the caller's own threads -- and starts one worker thread for the handler
(``phytoworks[device]`` extra). A Device that served is single-use.
It shares no credential or HTTP client with :class:`phytoworks.PWS`.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from time import monotonic
from types import TracebackType
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from . import _multiband_write, _zarr_storage
from ._device_mqtt import (
    ACTION_TYPES,
    CAPTURE,
    CAPTURE_ACTION_NAME,
    REDISCOVERY_COOLDOWN,
    Action,
    ActionContext,
    CaptureContext,
    LocalRun,
    RunResult,
    _telemetry_body,
    _telemetry_chunk,
)
from ._device_sensors import (
    Component,
    Readings,
    Sensor,
    Topic,
    camera_report_body,
    component_ids,
    components_body,
    telemetry_points,
    topic_ids,
)
from ._media_shared import (
    ArrayUploadResult,
    OperationSpec,
    _array_provenance_declarations,
    _array_reservation,
    _array_reservation_extras,
    _array_result,
    _build_operation_table,
    _image_upload_body,
    _operation,
    _parse_model,
    _prepare_array,
    _PreparedArray,
    _registered_multispectral_declaration,
    _registered_provenance_declarations,
    _upload_source,
    _validated_labels,
)
from ._transport import Transport
from .auth import AgentKeyCredential
from .config import DEFAULT_BASE_URL, read_agent_key_file, require_secure_hub
from .errors import (
    AuthError,
    DeviceStopped,
    MqttUnavailable,
    NotFoundError,
    NotServing,
    PWSError,
    SessionFenced,
    TransportError,
    ValidationError,
    _status_only,
)
from .models import (
    AgentCaptureSession,
    AgentImageUploadComplete,
    BandProvenance,
    DeviceRegistration,
)
from .models.generated import AgentImageUpload

if TYPE_CHECKING:
    from ._device_mqtt import Link, Supervisor

__all__ = [
    "Action",
    "ActionContext",
    "CaptureContext",
    "Component",
    "Device",
    "DeviceRoute",
    "HEARTBEAT_INTERVAL",
    "LocalRun",
    "RunResult",
    "Sensor",
    "Topic",
]

_logger = logging.getLogger(__name__)

_SESSIONS = "/agents/media/capture-sessions"
_TABLE = _build_operation_table(
    cast(
        dict[str, OperationSpec[BaseModel]],
        {
            "DISCOVER": OperationSpec("POST", "/agents/device/self-discovery", None),
            "HEARTBEAT": OperationSpec("POST", "/agents/device/heartbeat", None),
            "REGISTER": OperationSpec("POST", "/agents/device/self-register", DeviceRegistration),
            "CAPABILITIES": OperationSpec("POST", "/agents/device/components/capabilities", None),
            "RECORD": OperationSpec("POST", "/agents/device/action-executions", None),
            "TELEMETRY": OperationSpec("POST", "/agents/device/telemetry/batch", None),
            "SHUTDOWN_NOTIFY": OperationSpec("POST", "/agents/device/shutdown-notify", None),
            "SESSION_CREATE": OperationSpec("POST", _SESSIONS, AgentCaptureSession),
            "SESSION_START": OperationSpec("POST", f"{_SESSIONS}/{{id}}/start", AgentCaptureSession),
            "SESSION_COMPLETE": OperationSpec("POST", f"{_SESSIONS}/{{id}}/complete", AgentCaptureSession),
            "SESSION_FAIL": OperationSpec("POST", f"{_SESSIONS}/{{id}}/fail", AgentCaptureSession),
            "SESSION_CANCEL": OperationSpec("POST", f"{_SESSIONS}/{{id}}/cancel", AgentCaptureSession),
            "UPLOAD": OperationSpec("POST", "/agents/media/assets/upload-image", AgentImageUpload),
            "UPLOAD_COMPLETE": OperationSpec(
                "POST", "/agents/media/assets/complete-image-upload", AgentImageUploadComplete
            ),
            "ZARR_UPLOAD": OperationSpec("POST", "/agents/media/assets/zarr/upload", None),
            "ZARR_COMPLETE": OperationSpec("POST", "/agents/media/assets/zarr/complete", None),
            "BAND_PROVENANCE": OperationSpec("GET", "/agents/media/assets/{id}/band-provenance", BandProvenance),
        },
    )
)
_DISCOVERY_FIELDS = ("agent", "spot", "organization", "device")
# The Hub keeps a device online for 300 s after a heartbeat and asks for one every 60 s. `commandChannel:
# "none"` tells it this device subscribes to no Hub command, so Console's remote actions are refused, not
# lost; only a receive loop with a live subscription leaves it out.
HEARTBEAT_INTERVAL = 60.0
# The receive loop's own HTTP budget: one attempt, no Retry-After sleep, short per-phase limits, so a slow
# Hub delays its MQTT keepalive by seconds, not by the default 30 s per phase times three attempts.
SUPERVISOR_TIMEOUT = httpx.Timeout(connect=5.0, write=5.0, read=10.0, pool=5.0)
# How long the receive loop waits for the credential lock another thread holds before it skips a tick.
SUPERVISOR_LOCK_WAIT = 1.0
# The one shutdown-notify after the last sign-off, like agent-rs's HTTP_NOTIFY_TIMEOUT: one attempt that retirement waits
# for 3 s in all. httpx limits each read or write, not a whole request (an answer dribbled in short reads never times
# out), so the request runs on a thread of its own and is left to end, or time out, behind the retired Device.
SHUTDOWN_NOTIFY_DEADLINE = 3.0
SHUTDOWN_NOTIFY_TIMEOUT = httpx.Timeout(SHUTDOWN_NOTIFY_DEADLINE)

# idle -> serving -> closing -> retired, written only under Device._lock; _retire writes
# retired under Device._in_flight too, which admits the shutdown-notify's thread while retirement holds the lock.
_State = Literal["idle", "serving", "closing", "retired"]
# Who asks for a Hub call: the caller's own code ("bare", only while idle) or the executor -- its supervisor, its
# worker, or a handler through its live ctx.device ("loop").
_Who = Literal["bare", "loop"]


@dataclass(frozen=True, slots=True)
class MqttSlot:
    """The broker credential self-discovery returned; the password never appears in a repr."""

    principal: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MqttEndpoint:
    host: str
    port: int
    ca_file: str | None


class DeviceRoute:
    """Every Hub operation :class:`Device` calls; all are allowlisted and none is on the operator facade."""

    @classmethod
    def all(cls) -> tuple[tuple[str, str], ...]:
        return tuple((operation.method, operation.path) for operation in _TABLE.values())


class Device:
    """A device holding one DEVICE key file (``pws edge agents keys issue --out``, mode 0600).

    The key goes only to self-discovery and self-register; every other call carries the agent JWT those
    return. Both mint a new JWT and invalidate the agent's earlier ones, so :meth:`register` adopts its
    token. Whether the key may do something is the Hub's decision (a refused key raises
    :class:`~phytoworks.errors.PermissionError`); a rejected write is never replayed. A failed call keeps
    its error class and HTTP status only.

    The Hub keeps one live JWT per agent, so run one process per key at a time: a second one (say, a separate
    heartbeat job) re-discovers and cuts this one's JWT mid-upload. Inside one process, threads share one
    credential: only one of them re-discovers, and a call the Hub refused with 401 because another thread of
    this Device had just replaced the session is sent once more with the new token. A 401 this Device did not
    cause (another process signed in with the key) makes it sign in again and send that call once more, at most
    once per :data:`~phytoworks._device_mqtt.REDISCOVERY_COOLDOWN` -- two processes on one key take the session
    from each other that often. A key the Hub then refuses is not tried again.
    Liveness comes from this process alone -- every call heartbeats first when :data:`HEARTBEAT_INTERVAL`
    has passed -- so a cron that runs at least every four minutes keeps the device online; a longer gap shows
    it offline until the next run.

    The Device builds its own HTTP client with no default headers or cookies; ``transport`` is only the
    low-level :class:`httpx.BaseTransport` under it (a proxy mount, a test double).

    While :meth:`listen` serves, the executor owns the credential: a direct call on the Device from any thread
    raises :class:`RuntimeError` without a request (a handler uses ``ctx.device``; other threads use
    :meth:`submit`; :meth:`telemetry` alone is accepted from anywhere and queued), and once ``listen()`` has started its worker the Device is retired when it returns -- every
    later call raises :class:`~phytoworks.errors.DeviceStopped`, again without a request.
    """

    def __init__(
        self,
        key_file: str | os.PathLike[str],
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        mqtt_url: str | None = None,
        mqtt_ca_file: str | os.PathLike[str] | None = None,
    ) -> None:
        if not isinstance(key_file, (str, os.PathLike)):
            raise TypeError("Device takes a DEVICE key file path; user session credentials are refused")
        if transport is not None and not isinstance(transport, httpx.BaseTransport):
            raise TypeError("transport must be a low-level httpx transport; Device never shares an SDK client")
        # Before the key file is touched or any transport exists; the three transports share this Hub.
        hub = require_secure_hub(os.getenv("PWS_BASE_URL") or base_url or DEFAULT_BASE_URL)
        path = Path(key_file)
        self._key = read_agent_key_file(path)
        self._client = httpx.Client(transport=transport, timeout=timeout)
        self._transport = Transport(hub, client=self._client, timeout=timeout)
        self._supervisor = Transport(hub, client=self._client, timeout=SUPERVISOR_TIMEOUT, max_retries=0)
        self._notifier = Transport(hub, client=self._client, timeout=SHUTDOWN_NOTIFY_TIMEOUT, max_retries=0)
        self._mqtt_url = os.getenv("PWS_MQTT_URL") or mqtt_url
        ca_file = os.getenv("PWS_MQTT_CA_FILE") or mqtt_ca_file
        self._mqtt_ca_file = os.fspath(ca_file) if ca_file is not None else None
        # Guards the credential, its generation, the command-channel declaration and the executor state. Re-entrant:
        # a heartbeat holds it across its own session refresh.
        self._lock = threading.RLock()
        self._state: _State = "idle"
        # Requests under way: each Hub request and each presigned PUT is admitted (state, then its ctx.device's
        # liveness) and counted in one step, under this condition inside Device._lock; a key exchange is admitted under
        # it too. _retire waits a bounded time for none to be left; a revoke is written under it. A leaf lock: nothing
        # is acquired while it is held.
        self._in_flight = threading.Condition()
        self._requests = 0
        self._credential: AgentKeyCredential | None = None
        self._generation = 0
        # The last forced re-discovery -- a 401 this Device did not cause, or the broker refusing the cached slot -- for
        # one REDISCOVERY_COOLDOWN shared by both; a plain discover(), register() or expired JWT does not count. Once a
        # forced one is refused (401/403) the key is known refused and no 401 forces another; an adoption clears it.
        self._rediscovered_at: float | None = None
        self._key_refused = False
        self._mqtt: MqttSlot | None = None
        self._channel_open = False
        self._sessions: dict[str, str] = {}
        self._fenced: set[str] = set()
        self._actions: dict[str, Action] = {}  # the registered action table by name: what submit() runs
        self._remote: dict[str, Action] = {}  # Hub actionDefId -> the remote action a Hub command runs
        # (component identifier, topic name) -> topic id, from the last register that carried components; swapped whole
        # under the lock by that register only, read without it.
        self._topics: dict[tuple[str, str], str] = {}
        self._components: dict[str, str] = {}  # registered local identifier -> Hub UUID
        self._loop: Supervisor | None = None
        # Set by stop() and read by listen() and its loop. A plain attribute, never a lock or an Event, so stop()
        # is safe in a signal handler that interrupts the thread inside listen().
        self._stop_requested = False
        self._worker: threading.Thread | None = None
        self._link_factory: Callable[[str], Link] | None = None
        self.agent_id: str | None = None
        self.spot_id: str | None = None
        self.device_id: str | None = None
        self.manual_mode: bool | None = None
        """The Hub's manual-mode flag for this device as last applied, ``None`` while unknown: every successful
        heartbeat's ``deviceStatus.manualMode`` and, while :meth:`listen` serves, each ``manual-mode/sync`` entry for
        this device. The later one wins; neither carries a version, so a lost sync stays until the next heartbeat."""
        self._beat_at: float | None = None

    def __enter__(self) -> Device:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client. The device stays online until its lease runs out; see :meth:`sign_off`."""

        self._client.close()

    def heartbeat(self) -> None:
        """Mark the device online now; every call already does this once :data:`HEARTBEAT_INTERVAL` has passed.

        A caller that waits longer than that between calls (a long motor move) can call this to stay online.
        """

        self._beat(online=True, who="bare")

    def sign_off(self) -> None:
        """Hand the online lease back so Console shows the device offline at once.

        For a process that stays up and is now stopping. A cron run should not call it: the device would read
        offline between runs instead of for the 300 s after its last call.
        """

        self._beat(online=False, who="bare")

    def discover(self) -> dict[str, object]:
        """Exchange the key for a session; return the agent, spot, organization and bound device (no secrets)."""

        with self._lock:
            payload = self._discover(self._transport, "bare")
        return {field: payload[field] for field in _DISCOVERY_FIELDS if field in payload}

    def register(
        self,
        identifier: str,
        name: str,
        *,
        actions: Sequence[Action] = (),
        components: Sequence[Component] | None = None,
    ) -> DeviceRegistration:
        """Bind this agent's Device (idempotent per identifier) and set its action table: what :meth:`listen` runs.

        Each remote :class:`Action` is declared to the Hub like an agent-rs action definition: ``parameters`` as
        given, ``nameTranslation`` from ``name_translation`` and ``metadata.ui`` from ``ui`` when given and ``timeout``; a ``remote=False`` one never is. A remote
        ``CAPTURE`` must be named ``device.capture`` (the Hub tells a capture by that name, Console picks one by type),
        so another name raises :class:`ValueError` before a request, as does a ``timeout`` outside 1 to 86400 seconds.
        The Hub keeps every device action it was ever sent and lists them in every answer: if it still lists a
        ``CAPTURE`` under another name (an earlier SDK's ``capture``), Console would keep picking that one, so this
        raises :class:`ValueError` naming it with the cleanup and leaves no action table (``listen()`` stays
        refused), whatever this registration declares.

        ``components`` declares sensor parts like agent-rs's IOBoard components (:class:`Component`, :class:`Topic`).
        ``None`` sends none, so the components the Hub already knows are kept. A list is the full snapshot: the Hub
        removes every component of this agent the list leaves out, and an empty one is refused with
        :class:`ValueError` before a request. Whatever the Hub refuses of it (a closed value, a length, a duplicate
        name) raises :class:`ValueError` before a request too. Declare the CAMERA (with its ``capture_group`` and
        ``sensors``) and every SENSOR in the same list every time: a list of only the sensors removes the camera.
        The answer's topic ids replace the table
        :meth:`telemetry` resolves names with; a registration without components, a failed one, :meth:`discover` and
        every session change leave it as it was.
        """

        table = _action_table(actions)
        declared = None if components is None else components_body(components)
        remote = [action for action in table.values() if action.remote]
        body: dict[str, object] = {"deviceIdentifier": identifier, "deviceName": name}
        if remote:
            body["device_actions"] = [_declaration(action) for action in remote]
        if declared is not None:
            body["components"] = declared
        with self._lock:
            payload = self._adopt(self._key_request("REGISTER", body, self._transport, "bare"))
            self._actions, self._remote = {}, {}  # the Hub took this registration: the old table is gone either way
            if declared is not None:
                self._topics = topic_ids(payload)  # the Hub took the snapshot: these are the ids that stand
                self._components = component_ids(payload)
        registration = _parse_model(
            {key: value for key, value in payload.items() if key != "session"}, DeviceRegistration
        )
        device = registration["device"]
        self.device_id = str(device["id"]) if isinstance(device, Mapping) else None
        listed = payload.get("device_actions")
        rows = [row for row in listed if isinstance(row, Mapping)] if isinstance(listed, Sequence) else []
        _refuse_legacy_captures(rows, self.device_id)
        ids = {str(row["name"]): str(row["id"]) for row in rows if row.get("id") and not row.get("componentId")}
        self._remote = {ids[action.name]: action for action in remote if action.name in ids}
        self._actions = table
        return registration

    def telemetry(self, readings: Readings, *, at: datetime | None = None) -> object:
        """Send sensor readings for the topics :meth:`register` declared: ``{name: number}`` stamped ``at`` (default
        now) or ``{name: [(time, number), ...]}``. ``name`` is the topic name when one component has it, else
        ``(component identifier, name)``; times need a timezone (written in UTC, to the millisecond) and may be at most
        5 s ahead of now.

        The whole input is checked before anything is sent: a bool or non-finite number, a time without a zone or too
        far ahead, an unknown or ambiguous topic, an empty input or a call before ``register(components=...)`` raises
        :class:`ValueError` and sends nothing. Outside :meth:`listen` this is one ``telemetry/batch`` request and returns
        the Hub's answer; more than 50 topics, 1000 points on one topic or 1,000,000 bytes of body raise
        :class:`ValueError` too (send them in several calls). While :meth:`listen` serves, from any thread, the points
        join the receive loop's queue and this returns ``None`` at once: manual mode and :meth:`submit`'s limit do not
        apply, and the loop sends them oldest first every 10 s, waiting out a 429.
        """

        return self._telemetry(readings, at, "bare", None)

    def _telemetry(self, readings: Readings, at: datetime | None, who: _Who, scope: _ScopedDevice | None) -> object:
        points = telemetry_points(readings, at, self._topics)
        loop = self._loop  # read without the lock, as submit() does: enqueuing is not a Hub call
        if loop is not None:
            loop.enqueue_telemetry(points, scope)
            return None
        if _telemetry_chunk(deque(points)) < len(points):
            raise ValueError(
                "more than one request holds (50 topics, 1000 points per topic, 1,000,000 bytes): send fewer"
            )
        return self._call("TELEMETRY", _telemetry_body([point for point, _size in points]), who=who, scope=scope)

    def report_camera(
        self,
        identifier: str,
        *,
        model: str | None = None,
        serial: str | None = None,
        firmware: str | None = None,
    ) -> dict[str, object]:
        """Report what a registered CAMERA component actually is, like agent-rs once its driver has opened the camera.

        :meth:`register` declares the camera (``Sensor("THERMAL", model=...)``); this call is the only writer of its
        reported ``model``, ``serial`` and ``firmware``, and ``serial`` is what an asset's ``sensorSerial`` shows. A
        field left ``None`` is not sent, so the Hub keeps what it holds; ``model`` is required and each given field is
        a non-empty string, because the Hub keeps ``serial`` and ``firmware`` only together with the reported
        ``model`` (the declared Sensor model is not copied in for you). A ``model`` outside the Hub's camera catalog is stored as given and shown without RGB
        alignment. This SDK reports no capability profile, so the Hub drops any it held.

        Returns the Hub's answer: ``accepted`` (components changed; ``0`` also when the report repeats what is stored)
        and ``unknownIdentifiers`` (names this device does not have: register the camera first). Invalid input raises
        :class:`ValueError` before a request.
        """

        answer = self._call("CAPABILITIES", camera_report_body(identifier, model, serial, firmware), who="bare")
        return dict(answer) if isinstance(answer, Mapping) else {}

    def create_session(
        self,
        name: str,
        *,
        identity_label_keys: Sequence[str] | None = None,
        triggered_action_execution_id: str | None = None,
    ) -> AgentCaptureSession:
        """A ``PLANNED`` session on this device; uploads must then carry a label for each identity key.

        ``triggered_action_execution_id`` names the Hub command this capture answers, so the Hub links the
        session to that execution; the Hub drops it unless the execution targets this agent's spot.
        """

        return self._create_session(name, identity_label_keys, triggered_action_execution_id, "bare")

    def start(self, session: str) -> AgentCaptureSession:
        return self._session_write("SESSION_START", session, None, "bare")

    def complete(self, session: str) -> AgentCaptureSession:
        return self._session_write("SESSION_COMPLETE", session, None, "bare")

    def fail(self, session: str, *, reason: str | None = None) -> AgentCaptureSession:
        """Settle a started (``IN_PROGRESS``) session as failed; before :meth:`start`, use :meth:`cancel`."""

        return self._session_write("SESSION_FAIL", session, _reason(reason), "bare")

    def cancel(self, session: str, *, reason: str | None = None) -> AgentCaptureSession:
        return self._session_write("SESSION_CANCEL", session, _reason(reason), "bare")

    def upload_image(
        self,
        file: str | Path,
        *,
        thumbnail: str | Path,
        session: str,
        width: int,
        height: int,
        modality: str = "RGB",
        labels: Mapping[str, str] | None = None,
        component: str | None = None,
    ) -> AgentImageUploadComplete:
        """Reserve, PUT the image and thumbnail to their presigned URLs, then report completion.

        ``component`` is the local identifier declared through ``register(components=...)``. It resolves to the
        Hub UUID from that registration so the media is attributed to the physical camera. An unknown identifier
        is refused before any request. Omitting it keeps the device-level upload without a component attribution.
        """

        return self._upload_image(file, thumbnail, session, width, height, modality, labels, component, "bare", None)

    def _upload_image(
        self,
        file: str | Path,
        thumbnail: str | Path,
        session: str,
        width: int,
        height: int,
        modality: str,
        labels: Mapping[str, str] | None,
        component: str | None,
        who: _Who,
        scope: _ScopedDevice | None,
    ) -> AgentImageUploadComplete:
        self._refuse_fenced(session)
        component_id = self._upload_component_id(component)
        checked = None if labels is None else _validated_labels(labels)
        image, preview = Path(file), Path(thumbnail)
        with (
            _upload_source(image) as (image_source, image_size),
            _upload_source(preview) as (preview_source, preview_size),
        ):
            body, image_type, preview_type = _image_upload_body(
                image,
                preview,
                image_size,
                preview_size,
                session=session,
                width=width,
                height=height,
                modality=modality,
                spot=None,
                device=self.device_id,
            )
            if component_id is not None:
                body["componentId"] = component_id
            if checked is not None:
                body["labels"] = checked
            issued = _parse_model(self._call("UPLOAD", body, who=who, scope=scope), AgentImageUpload)
            puts = (
                (_text(issued, "uploadUrl"), image_source, image_size, image_type),
                (_text(issued, "thumbnailUploadUrl"), preview_source, preview_size, preview_type),
            )
            for url, source, size, content_type in puts:
                with self._request(who, scope):  # each presigned PUT is admitted at its start, like a Hub request
                    _status_only_call(
                        "presigned upload",
                        partial(self._transport.upload_opened, url, source, size=size, content_type=content_type),
                    )
        completion = {"mediaAssetId": _text(issued, "mediaAssetId"), "width": width, "height": height}
        self._refuse_fenced(session)
        return _parse_model(self._call("UPLOAD_COMPLETE", completion, who=who, scope=scope), AgentImageUploadComplete)

    def upload_registered_multispectral(
        self,
        source_asset_id: str,
        aligned_bands: object,
        *,
        session: str,
        path: str,
        radiometric_level: str,
        record_fragment: object | None = None,
        profile: Mapping[str, object] | None = None,
        band_metadata: Sequence[_multiband_write.BandInput] | None = None,
        labels: Mapping[str, str] | None = None,
        calibration: Mapping[str, object] | None = None,
        normalization: Mapping[str, object] | None = None,
        interpretation: Sequence[Mapping[str, object]] | None = None,
    ) -> ArrayUploadResult:
        """Device-route twin of :meth:`phytoworks.PWS.media.upload_registered_multispectral`."""

        bands, registration = _registered_multispectral_declaration(
            source_asset_id,
            aligned_bands,
            record_fragment=record_fragment,
            path=path,
            profile=profile,
            band_metadata=band_metadata,
        )
        source_provenance: object = None
        if normalization is None or interpretation is None:
            try:
                source_provenance = self._band_provenance(source_asset_id, who="bare")
            except NotFoundError:
                raise ValidationError("source MULTISPECTRAL asset has no verified band provenance") from None
        normalization, interpretation = _registered_provenance_declarations(
            bands,
            radiometric_level,
            calibration,
            source_provenance,
            normalization=normalization,
            interpretation=interpretation,
        )
        return self.upload_array(
            "MULTISPECTRAL",
            bands,
            session=session,
            labels=labels,
            derived_from=[source_asset_id],
            radiometric_level=radiometric_level,
            calibration=calibration,
            registration=registration,
            normalization=normalization,
            interpretation=interpretation,
        )

    def _upload_component_id(self, identifier: str | None) -> str | None:
        if identifier is None:
            return None
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("upload component must be a non-empty registered component identifier")
        try:
            return self._components[identifier]
        except KeyError as error:
            raise ValueError(
                "upload component was not returned by register(components=...); "
                "declare it in this Device's full component snapshot"
            ) from error

    def upload_array(
        self,
        modality: str,
        data: object,
        *,
        session: str,
        labels: Mapping[str, str] | None = None,
        derived_from: Sequence[str] | None = None,
        unit: str | None = None,
        scale: float | None = None,
        offset: float | None = None,
        no_data: float | None = None,
        display_range: tuple[float, float] | None = None,
        colormap: str | None = None,
        intrinsics: Mapping[str, float] | None = None,
        source_sensor: str | None = None,
        capture_parameters: Mapping[str, str | int | float | bool] | None = None,
        radiometric_level: str | None = None,
        calibration: Mapping[str, object] | None = None,
        registration: Mapping[str, object] | None = None,
        normalization: Mapping[str, object] | None = None,
        interpretation: Sequence[Mapping[str, object]] | None = None,
    ) -> ArrayUploadResult:
        """:meth:`phytoworks.PWS.media.upload_array` (same arguments, encoding and client checks) on the device
        Zarr routes; the Hub decides device provenance and every switch.

        ``capture_parameters`` are the capture conditions stored on the asset as ``captureParameters`` (the field
        agent-rs sends): string keys to ``str``, ``bool``, ``int`` or finite ``float`` values, e.g.
        ``{"emissivity": 0.95, "ambient_c": 21.5}``. Anything else raises :class:`ValidationError` before a request."""

        descriptor: dict[str, object] = {
            "unit": unit,
            "scale": scale,
            "offset": offset,
            "no_data": no_data,
            "display_range": display_range,
            "colormap": colormap,
            "intrinsics": intrinsics,
            "source_sensor": source_sensor,
            "radiometric_level": radiometric_level,
            "calibration": calibration,
        }
        declarations = _array_provenance_declarations(modality, registration, normalization, interpretation)
        return self._upload_array(
            modality, data, session, labels, derived_from, descriptor, declarations, capture_parameters, "bare", None
        )

    def _upload_array(
        self,
        modality: str,
        data: object,
        session: str,
        labels: Mapping[str, str] | None,
        derived_from: Sequence[str] | None,
        descriptor: dict[str, object],
        declarations: Mapping[str, object],
        capture_parameters: Mapping[str, str | int | float | bool] | None,
        who: _Who,
        scope: _ScopedDevice | None,
    ) -> ArrayUploadResult:
        self._refuse_fenced(session)
        extras = _array_reservation_extras(modality, session, labels, derived_from, descriptor, capture_parameters)
        with tempfile.TemporaryDirectory(prefix=f"pws-device-{modality.lower()}-") as temporary:
            prepared = _prepare_array(modality, data, Path(temporary), session, extras, descriptor, declarations)
            # The receive loop may have settled the session, revoked ctx.device or retired while the store was
            # prepared: the reservation's own admission sees the last two.
            self._refuse_fenced(session)
            reserved = self._call("ZARR_UPLOAD", prepared.reservation, who=who, scope=scope)
            reservation = _array_reservation(reserved, modality)
            reserved_id = cast(str, reservation["mediaAssetId"])
            _put_members(prepared, reservation, partial(self._request, who, scope))  # each member PUT admitted
            with self._request(who, scope):  # the thumbnail PUT, admitted like a Hub request
                _status_only_call(
                    "presigned upload",
                    partial(
                        self._transport.upload,
                        cast(str, reservation["thumbnailUploadUrl"]),
                        prepared.preview,
                        content_type="image/jpeg",
                    ),
                )
            self._refuse_fenced(session)
            completion = {"mediaAssetId": reserved_id, **prepared.completion}
            completed = self._call("ZARR_COMPLETE", completion, who=who, scope=scope)
            return _array_result(completed, reserved_id, modality)

    def listen(
        self,
        *,
        handler_timeout: float = 3600.0,
        stop_grace: float = 30.0,
    ) -> None:
        """Run this device's action executor until :meth:`stop` (or a fatal broker or key error); blocks this thread.

        Needs ``pip install 'phytoworks[device]'``, a broker URL (``mqtt_url=`` or ``PWS_MQTT_URL``,
        ``mqtts://host:port``; production serves ``:443``) and, in this process, :meth:`register` with
        ``actions``. Two doors lead to the same executor: a Hub command for a remote action and :meth:`submit` from
        the caller's own threads (a schedule). A Hub command for any other action is answered ``FAILED`` without
        calling a handler. One worker thread runs each item's handler in the order it was accepted, with an
        :class:`ActionContext` (a :class:`CaptureContext` with a capture session to fill for a ``CAPTURE``); the
        handler reaches the Hub only through ``ctx.device``. The handler may move motors (a pan-tilt sweep); the
        safety of any actuation it drives is the caller's. Cancellation is cooperative: a Hub cancel,
        :meth:`LocalRun.cancel`, the run's deadline (the action's ``timeout``, at most ``handler_timeout`` seconds
        from acceptance) or :meth:`stop` sets ``ctx.cancelled``; a handler still running ``stop_grace`` seconds later
        is abandoned -- the loop settles its session and its further writes raise
        :class:`~phytoworks.errors.SessionFenced`.

        While listening, this thread is the only heartbeat writer and Console shows the device accepting
        commands only while the broker subscription stands. Raises
        :class:`~phytoworks.errors.MqttUnavailable` (no URL, no port or no Hub-issued credential) before any socket,
        :class:`~phytoworks.errors.CredentialRevoked`, :class:`~phytoworks.errors.SessionTakenOver` or
        :class:`~phytoworks.errors.SubscribeDenied`. Returns after :meth:`stop` has closed both doors, settled
        work, flushed results, signed off and sent one ``shutdown-notify`` as agent-rs does (neither after a takeover
        or a revoked key: the lease is no longer this process's; neither either when an abandoned handler's request is
        still under way ``stop_grace`` seconds into retirement: the Hub lease runs out instead), or at once, with no
        Hub call, thread or socket, if :meth:`stop` came first. Either way the Device is then retired; only a setup
        error raised before the worker starts leaves it usable.
        """

        with self._lock:
            self._refuse_listen()
        if not self._actions:
            raise ValueError("call register(..., actions=[...]) in this process before listen()")
        if self._stop_requested:
            with self._lock:
                self._state = "retired"
            return
        endpoint = self._mqtt_endpoint()
        factory = self._link_factory
        if factory is None:
            try:
                import paho.mqtt.client  # noqa: F401
            except ImportError:
                raise ImportError("Device.listen() needs the MQTT extra: pip install 'phytoworks[device]'") from None
        slot = self._mqtt_slot(supervised=True, who="bare")
        from ._device_mqtt import PahoLink, Supervisor

        loop = Supervisor(
            self,
            handler_timeout=handler_timeout,
            stop_grace=stop_grace,
            link_factory=factory or PahoLink,
        )
        with self._lock:
            self._refuse_listen()
            self._state, self._loop, self._worker = "serving", loop, loop.worker
        try:
            loop.run(endpoint, slot)  # a stop() during the discovery above ends it before any connection
        finally:
            self._loop = None

    def submit(self, action: str, params: Mapping[str, object] | None = None) -> LocalRun:
        """Ask the running :meth:`listen` executor to run ``action`` now; return its handle at once.

        ``action`` is the name of any action this process registered, remote or local. The item joins the Hub's
        commands in one queue (first accepted, first run; ``OUTBOX_LIMIT`` items in all) and runs that action's
        handler with ``ctx.trigger == "local"``; a ``CAPTURE`` gets a capture session the executor creates
        (``triggerSource: AGENT``, linked to no Hub execution). When to call it is the caller's schedule. Local items
        are never published as Hub command results. A run of an action declared to the Hub (``remote=True``) leaves a
        Hub record (``source`` ``AGENT``, its session linked) once it ends, unless it was ``SKIPPED``, and one that
        ends ``SUCCESS`` or ``FAILED`` updates the device's current value; both are best effort (retried, then dropped;
        nothing is sent once :meth:`stop` was seen). A ``remote=False`` action's runs stay in their :class:`LocalRun`.
        ``params`` go to the handler as ``ctx.params`` unchecked (a remote action's ``parameters`` schema binds only Hub
        commands).

        Refused at once, without a request: before ``listen()`` has started its worker
        (:class:`~phytoworks.errors.NotServing`), once :meth:`stop` was asked (even before the loop acts on it) or the
        Device is retired (:class:`~phytoworks.errors.DeviceStopped`), a name this process did not register
        (:class:`ValueError`), while the Hub reports manual mode (:class:`~phytoworks.errors.ManualModeActive`; an
        unknown mode counts as automatic), a full executor (:class:`~phytoworks.errors.DeviceBusy`), and a call from
        the handler's worker thread (:class:`RuntimeError` -- waiting on its own run would deadlock). A queued local
        item that reaches the worker while manual mode is on ends ``SKIPPED`` without starting; a running one
        finishes. It takes locks, so call it from a thread, never from a signal handler (use :meth:`stop` there).
        """

        loop = self._loop
        if loop is None:
            if self._state == "idle":
                raise NotServing("listen() is not serving yet; submit() needs its executor")
            raise DeviceStopped("this Device's executor has stopped")
        entry = self._actions.get(action)
        if entry is None:
            raise ValueError(f"{action!r} is not an action this Device registered")
        return loop.submit(entry, dict(params) if params is not None else {})

    def stop(self) -> None:
        """Ask :meth:`listen` to wind down: the running one, or else the next one, which then returns at once.

        It only sets a flag (no lock, no I/O), so it is safe from another thread or from a signal handler that
        interrupts the thread inside :meth:`listen`. The loop sleeps at most one loop step (a second) between
        checks, but sees the request only after a synchronous broker connect or the step's Hub call (which may
        begin after the stop) returns, so detection has no fixed bound. Either way the Device ends retired.
        """

        self._stop_requested = True

    # ------------------------------------------------------------------
    # Receive-loop hooks (phytoworks._device_mqtt)
    # ------------------------------------------------------------------

    def _mqtt_endpoint(self) -> MqttEndpoint:
        """The broker this device connects to: ``PWS_MQTT_URL`` or ``mqtt_url``, ``mqtts://`` with an explicit port."""

        if not self._mqtt_url:
            raise MqttUnavailable("no broker URL: pass Device(mqtt_url='mqtts://host:443') or set PWS_MQTT_URL")
        parts = urlsplit(self._mqtt_url)
        if parts.scheme != "mqtts" or not parts.hostname:
            raise MqttUnavailable(
                "the broker URL must be mqtts://host:port; a plain connection would send the password"
            )
        try:
            port = parts.port
        except ValueError:
            raise MqttUnavailable("the broker URL has an invalid port") from None
        if not port:  # no default: the broker's TLS port is a deployment fact (production serves :443)
            raise MqttUnavailable("the broker URL needs its port, such as mqtts://host:443")
        return MqttEndpoint(parts.hostname, port, self._mqtt_ca_file)

    def _mqtt_slot(self, *, supervised: bool, who: _Who = "loop", rediscover: bool = False) -> MqttSlot:
        """The cached broker credential; discovery runs only when none is cached or ``rediscover`` asks for it and the
        shared cooldown allows (otherwise the cached slot, which a 401's re-discovery may have just refreshed)."""

        transport = self._supervisor if supervised else self._transport
        with self._locked(supervised):
            if (rediscover and self._rediscovery_due()) or self._mqtt is None:
                self._discover(transport, who)
            if self._mqtt is None:
                raise MqttUnavailable("the Hub issued no MQTT credential to this device")
            return self._mqtt

    def _set_channel(self, open_: bool, *, supervised: bool = True) -> None:
        """Declare (or withdraw) the command channel and send the heartbeat that tells the Hub, as one step."""

        with self._locked(supervised):
            self._channel_open = open_
            self._beat(online=True, who="loop", supervised=supervised)

    def _beat_due(self) -> bool:
        return self._beat_at is None or monotonic() - self._beat_at >= HEARTBEAT_INTERVAL

    def _fence(self, session: str) -> None:
        self._fenced.add(session)

    def _session_status(self, session: str) -> str | None:
        return self._sessions.get(session)

    def _forget(self, session: str) -> None:
        self._sessions.pop(session, None)

    def _settle_write(self, name: str, session: str, reason: str, *, supervised: bool = True) -> AgentCaptureSession:
        """A settlement write the receive loop makes past the fence it set (on its own budget when supervised)."""

        settled = _parse_model(
            self._call(name, _reason(reason), who="loop", supervised=supervised, id=session), AgentCaptureSession
        )
        self._note(settled)
        return settled

    def _scope(self) -> _ScopedDevice:
        return _ScopedDevice(self)

    def _refuse_listen(self) -> None:
        """Lock held: a Device runs one executor in its life."""

        if self._state == "retired":
            raise DeviceStopped("this Device already served listen(); a served Device is single-use")
        if self._state != "idle":
            raise RuntimeError("listen() is already serving this Device")

    def _enter_closing(self) -> None:
        """Both doors are closed: from here no call makes a new session. Waits out an exchange in progress."""

        with self._lock:
            self._state = "closing"

    def _retire(self, *, sign_off: bool, grace: float) -> None:
        """The last sign-off and one ``shutdown-notify`` (unless the lease is no longer this process's) and
        ``retired``, as one step.

        Holding the lock admits nothing new. A request admitted before it may still be under way: retirement waits up
        to ``grace`` seconds for those to end, so no thread's request follows the sign-off. HTTP limits are per read
        or write, not per request, so an abandoned handler's upload may outlast that: then both are skipped
        (the Hub's 300 s lease marks the device offline) and the Device retires anyway; whatever that handler tries
        next is refused at its own admission. The notify clears the same lease as the sign-off (agent-rs sends it
        after draining): one attempt, sent even if the sign-off failed, waited on ``SHUTDOWN_NOTIFY_DEADLINE`` seconds
        in all, and sent only if its thread was admitted before ``retired`` is written.
        """

        with self._lock:
            deadline = monotonic() + grace
            with self._in_flight:
                while self._requests and (left := deadline - monotonic()) > 0:
                    self._in_flight.wait(min(left, 1.0))  # wakes as each request ends; reads the clock every second
                lingering = self._requests
            try:
                if sign_off and lingering:
                    _logger.warning(
                        "listen() retired without a sign-off: %d request(s) still under way after stop_grace; "
                        "the Hub lease marks the device offline within 300 s",
                        lingering,
                    )
                elif sign_off:
                    try:
                        self._beat(online=False, who="loop", supervised=True)
                    except PWSError:
                        pass  # the lease runs out on its own within 300 s
                    self._notify()  # likewise; tried even when the sign-off failed
            finally:
                with self._in_flight:
                    self._state = "retired"

    def _notify(self) -> None:
        """Lock held: its headers made here, the request sent on a thread retirement waits for at most
        ``SHUTDOWN_NOTIFY_DEADLINE`` seconds; any failure is swallowed (the lease runs out on its own within 300 s).

        ``thread.start()`` is no barrier, and the thread cannot take the lock retirement holds: it is admitted, just
        before its request, under the in-flight condition ``retired`` is written under, so it falls wholly before
        retirement (sent) or after it (never sent)."""

        try:
            headers, _generation = self._session_headers(self._notifier, True, "loop", None)
        except PWSError:
            return
        operation = _operation(_TABLE["SHUTDOWN_NOTIFY"])
        send = partial(
            self._notifier.request,
            operation.spec.method,
            operation.path,
            json_body={"reason": "graceful_shutdown"},
            headers=headers,
        )

        def admitted() -> object:
            with self._in_flight:
                if self._state == "retired":
                    raise DeviceStopped("retired before the shutdown-notify started")
            return send()

        def notify() -> None:
            with suppress(Exception):  # nobody waits for it past the deadline; the client may be closed by then
                _status_only_call(f"{operation.spec.method} {operation.spec.path}", admitted)

        thread = threading.Thread(target=notify, name="phytoworks-shutdown-notify", daemon=True)
        thread.start()
        thread.join(SHUTDOWN_NOTIFY_DEADLINE)

    # ------------------------------------------------------------------
    # Credential and call plumbing
    # ------------------------------------------------------------------

    @contextmanager
    def _locked(self, supervised: bool) -> Iterator[None]:
        """The credential lock; the receive loop waits only briefly for it so its MQTT keepalive keeps running."""

        if not self._lock.acquire(timeout=SUPERVISOR_LOCK_WAIT if supervised else -1):
            raise TransportError("device credential busy in another thread")
        try:
            yield
        finally:
            self._lock.release()

    def _admit(self, who: _Who, scope: _ScopedDevice | None = None) -> None:
        """Lock held, before any Hub request: the executor owns the credential while it serves, nobody after it,
        and a handler's ctx.device only until its item is settled or abandoned."""

        if self._state == "retired":
            raise DeviceStopped("this Device served listen() and is retired; a served Device is single-use")
        if who == "bare" and self._state != "idle":
            raise RuntimeError(
                "Device calls are refused while listen() serves: a handler uses ctx.device, other threads submit()"
            )
        if scope is not None:
            scope._live()

    @contextmanager
    def _request(self, who: _Who, scope: _ScopedDevice | None, supervised: bool = False) -> Iterator[None]:
        """One request's start: admitted under the lock and the in-flight condition and counted until it ends, so
        retirement and a revoke each fall wholly before it (it is refused) or after it started."""

        with self._locked(supervised), self._in_flight:
            self._admit(who, scope)
            self._requests += 1
        try:
            yield
        finally:
            with self._in_flight:
                self._requests -= 1
                self._in_flight.notify_all()

    def _discover(self, transport: Transport, who: _Who, scope: _ScopedDevice | None = None) -> Mapping[str, object]:
        payload = self._adopt(self._key_request("DISCOVER", None, transport, who, scope))
        spot, device = payload.get("spot"), payload.get("device")
        self.spot_id = str(spot["id"]) if isinstance(spot, Mapping) else None
        self.device_id = str(device["id"]) if isinstance(device, Mapping) else None
        return payload

    def _key_request(
        self,
        name: str,
        body: Mapping[str, object] | None,
        transport: Transport,
        who: _Who,
        scope: _ScopedDevice | None = None,
    ) -> object:
        """A key exchange (lock held): it replaces the agent's sessions and moves its lease, so none from ``closing``
        and none for a revoked ctx.device. Admitted under the in-flight condition like a request, so a revoke falls
        wholly before it (refused) or after it started; the exchange itself then runs and is adopted under the lock."""

        with self._in_flight:
            self._admit(who, scope)
            if self._state == "closing":
                raise DeviceStopped("this Device is stopping; it makes no new agent session")
        operation = _TABLE[name]
        headers = {"X-API-Key": self._key}
        request = partial(transport.request, operation.method, operation.path, headers=headers, json_body=body)
        return _status_only_call(f"{operation.method} {operation.path}", request)

    def _adopt(self, payload: object) -> Mapping[str, object]:
        """Make the session in a discovery or register response the one every later call uses (lock held)."""

        agent = payload.get("agent") if isinstance(payload, Mapping) else None
        if not isinstance(payload, Mapping) or not isinstance(agent, Mapping) or not agent.get("id"):
            raise ValidationError("Hub returned an agent session without an agent")
        credential = AgentKeyCredential(self._key, agent_id=str(agent["id"]))
        credential._store_session(payload)
        self._credential, self.agent_id = credential, credential.agent_id
        self._generation += 1
        self._key_refused = False
        if "mqtt" in payload:  # discovery only; register keeps the slot, which is derived from the key, not the JWT
            self._mqtt = _slot(payload.get("mqtt"))
        self._beat_at = None  # the lease names the session this response just replaced
        return payload

    def _session_headers(
        self, transport: Transport, supervised: bool, who: _Who, scope: _ScopedDevice | None
    ) -> tuple[Mapping[str, str], int]:
        with self._locked(supervised):
            self._admit(who, scope)
            if self._credential is None or not self._credential._token_is_valid():
                self._discover(transport, who, scope)  # once the JWT has expired (a 401 is _call's); never from closing
            return cast(AgentKeyCredential, self._credential).headers(), self._generation

    def _rediscovery_due(self) -> bool:
        """Lock held: whether a forced re-discovery may run now, at most once per ``REDISCOVERY_COOLDOWN`` for the
        HTTP 401 path and the broker path together. Counted when it is attempted, so a refused one waits too."""

        now = monotonic()
        if self._rediscovered_at is not None and now - self._rediscovered_at < REDISCOVERY_COOLDOWN:
            return False
        self._rediscovered_at = now
        return True

    def _replace_session(self, transport: Transport, who: _Who, scope: _ScopedDevice | None) -> bool:
        """Lock held, after a 401 this Device did not cause: the Hub dropped the session (another process signed in
        with this key) or the JWT ran out early. Sign in again unless stopping (a stop() already asked included, so the
        unit's stop budget gains no call), a handler's ctx.device is revoked, the key is known refused or the cooldown
        says no; ``False`` then, and the 401 stands. A refused sign-in (401/403) marks the key refused and raises its
        own status-only error."""

        if self._stop_requested or (self._state != "idle" and self._state != "serving"):
            return False
        if scope is not None:
            with self._in_flight:
                if scope._revoked:
                    return False
        if self._key_refused or not self._rediscovery_due():
            return False
        _logger.warning(
            "the Hub dropped this device's session (HTTP 401): another process may have signed in with this key; "
            "signing in again (run one process per key)"
        )
        try:
            self._discover(transport, who, scope)
        except PWSError as refused:
            if refused.status_code in (401, 403):
                self._key_refused = True
            raise
        return True

    def _beat(self, *, online: bool, who: _Who, supervised: bool = False) -> None:
        """One heartbeat whose body matches the channel state at the moment it is sent (lock held throughout)."""

        with self._locked(supervised):
            self._admit(who)
            if not online:
                self._channel_open = False
            body: dict[str, object] = {"status": "online" if online else "offline"}
            if not self._channel_open:
                body["commandChannel"] = "none"
            self._beat_at = monotonic()
            payload = self._call("HEARTBEAT", body, who=who, supervised=supervised)
            status = payload.get("deviceStatus") if isinstance(payload, Mapping) else None
            manual = status.get("manualMode") if isinstance(status, Mapping) else None
            self.manual_mode = manual if isinstance(manual, bool) else None  # every success corrects a sync

    def _call(
        self,
        name: str,
        body: Mapping[str, object] | None,
        *,
        who: _Who,
        scope: _ScopedDevice | None = None,
        supervised: bool = False,
        transport: Transport | None = None,
        **params: str,
    ) -> object:
        transport = transport or (self._supervisor if supervised else self._transport)
        headers, generation = self._session_headers(transport, supervised, who, scope)
        # Only an idle Device heartbeats before a call; while it serves, the supervisor is the one writer.
        if name != "HEARTBEAT" and who == "bare" and self._beat_due():
            try:
                self._beat(online=True, who=who)
            except PWSError:
                pass  # liveness is best effort; it must never fail the capture write behind it
            headers, generation = self._session_headers(transport, supervised, who, scope)
        operation = _operation(_TABLE[name], **params)
        spec = operation.spec
        what = f"{spec.method} {spec.path}"
        send = partial(transport.request, spec.method, operation.path, json_body=body)
        try:
            with self._request(who, scope, supervised):
                return _status_only_call(what, partial(send, headers=headers))
        except AuthError as error:
            if error.status_code != 401:
                raise
            refused = error
        # A 401 on a JWT route is the guard refusing a dropped session before any handler ran, so the call is sent
        # once more: with the session this Device adopted meanwhile, or else after signing in again. Handled
        # out of the except block so no error here is chained to the refused request.
        with self._locked(supervised):
            if self._generation == generation and not self._replace_session(transport, who, scope):
                raise refused
            if self._credential is None:
                raise refused
            headers = self._credential.headers()
        with self._request(who, scope, supervised):  # admitted again: the resend is a request of its own
            return _status_only_call(what, partial(send, headers=headers))

    def _create_session(
        self,
        name: str,
        identity_label_keys: Sequence[str] | None,
        triggered_action_execution_id: str | None,
        who: _Who,
        scope: _ScopedDevice | None = None,
    ) -> AgentCaptureSession:
        body: dict[str, object] = {"name": name, "triggerSource": "AGENT"}
        if identity_label_keys is not None:
            body["identityLabelKeys"] = list(identity_label_keys)
        if triggered_action_execution_id is not None:
            body["triggeredActionExecutionId"] = triggered_action_execution_id
        created = _parse_model(self._call("SESSION_CREATE", body, who=who, scope=scope), AgentCaptureSession)
        self._note(created)
        return created

    def _band_provenance(self, identifier: str, *, who: _Who, scope: _ScopedDevice | None = None) -> BandProvenance:
        return _parse_model(self._call("BAND_PROVENANCE", None, who=who, scope=scope, id=identifier), BandProvenance)

    def _session_write(
        self, name: str, session: str, body: Mapping[str, object] | None, who: _Who, scope: _ScopedDevice | None = None
    ) -> AgentCaptureSession:
        self._refuse_fenced(session)
        written = _parse_model(self._call(name, body, who=who, scope=scope, id=session), AgentCaptureSession)
        self._note(written)
        return written

    def _refuse_fenced(self, session: str) -> None:
        if session in self._fenced:
            raise SessionFenced(f"capture session {session} was settled by the receive loop after its handler overran")

    def _note(self, session: AgentCaptureSession) -> None:
        try:
            identifier, status = session["id"], session["status"]
        except KeyError:
            return
        if isinstance(identifier, str) and isinstance(status, str):
            self._sessions[identifier] = status


class _ScopedDevice:
    """``ctx.device``: the handler's way to the Hub for one executor item -- its capture sessions and uploads, no
    key exchange, heartbeat or sign-off. The executor revokes it when it settles or abandons the item; a revoked
    handle, like a retired Device, refuses every call without a request. Each Hub request of a call, its key
    exchange and each presigned PUT is admitted when it starts, so a call already running when the revoke lands
    starts nothing more (a request already started runs to its end)."""

    def __init__(self, device: Device) -> None:
        self._device = device
        self._revoked = False

    def create_session(
        self,
        name: str,
        *,
        identity_label_keys: Sequence[str] | None = None,
        triggered_action_execution_id: str | None = None,
    ) -> AgentCaptureSession:
        """:meth:`Device.create_session`."""

        self._live()
        return self._device._create_session(name, identity_label_keys, triggered_action_execution_id, "loop", self)

    def telemetry(self, readings: Readings, *, at: datetime | None = None) -> object:
        """:meth:`Device.telemetry`; it joins the receive loop's queue."""

        self._live()
        return self._device._telemetry(readings, at, "loop", self)

    def start(self, session: str) -> AgentCaptureSession:
        self._live()
        return self._device._session_write("SESSION_START", session, None, "loop", self)

    def complete(self, session: str) -> AgentCaptureSession:
        self._live()
        return self._device._session_write("SESSION_COMPLETE", session, None, "loop", self)

    def fail(self, session: str, *, reason: str | None = None) -> AgentCaptureSession:
        """:meth:`Device.fail`."""

        self._live()
        return self._device._session_write("SESSION_FAIL", session, _reason(reason), "loop", self)

    def cancel(self, session: str, *, reason: str | None = None) -> AgentCaptureSession:
        self._live()
        return self._device._session_write("SESSION_CANCEL", session, _reason(reason), "loop", self)

    def upload_image(
        self,
        file: str | Path,
        *,
        thumbnail: str | Path,
        session: str,
        width: int,
        height: int,
        modality: str = "RGB",
        labels: Mapping[str, str] | None = None,
        component: str | None = None,
    ) -> AgentImageUploadComplete:
        """:meth:`Device.upload_image`."""

        self._live()
        return self._device._upload_image(
            file, thumbnail, session, width, height, modality, labels, component, "loop", self
        )

    def upload_registered_multispectral(
        self,
        source_asset_id: str,
        aligned_bands: object,
        *,
        session: str,
        path: str,
        radiometric_level: str,
        record_fragment: object | None = None,
        profile: Mapping[str, object] | None = None,
        band_metadata: Sequence[_multiband_write.BandInput] | None = None,
        labels: Mapping[str, str] | None = None,
        calibration: Mapping[str, object] | None = None,
        normalization: Mapping[str, object] | None = None,
        interpretation: Sequence[Mapping[str, object]] | None = None,
    ) -> ArrayUploadResult:
        """Upload a registered derivative through this handler's fenced Device scope."""

        bands, registration = _registered_multispectral_declaration(
            source_asset_id,
            aligned_bands,
            record_fragment=record_fragment,
            path=path,
            profile=profile,
            band_metadata=band_metadata,
        )
        source_provenance: object = None
        if normalization is None or interpretation is None:
            self._live()
            try:
                source_provenance = self._device._band_provenance(source_asset_id, who="loop", scope=self)
            except NotFoundError:
                raise ValidationError("source MULTISPECTRAL asset has no verified band provenance") from None
        normalization, interpretation = _registered_provenance_declarations(
            bands,
            radiometric_level,
            calibration,
            source_provenance,
            normalization=normalization,
            interpretation=interpretation,
        )
        return self.upload_array(
            "MULTISPECTRAL",
            bands,
            session=session,
            labels=labels,
            derived_from=[source_asset_id],
            radiometric_level=radiometric_level,
            calibration=calibration,
            registration=registration,
            normalization=normalization,
            interpretation=interpretation,
        )

    def upload_array(
        self,
        modality: str,
        data: object,
        *,
        session: str,
        labels: Mapping[str, str] | None = None,
        derived_from: Sequence[str] | None = None,
        unit: str | None = None,
        scale: float | None = None,
        offset: float | None = None,
        no_data: float | None = None,
        display_range: tuple[float, float] | None = None,
        colormap: str | None = None,
        intrinsics: Mapping[str, float] | None = None,
        source_sensor: str | None = None,
        capture_parameters: Mapping[str, str | int | float | bool] | None = None,
        radiometric_level: str | None = None,
        calibration: Mapping[str, object] | None = None,
        registration: Mapping[str, object] | None = None,
        normalization: Mapping[str, object] | None = None,
        interpretation: Sequence[Mapping[str, object]] | None = None,
    ) -> ArrayUploadResult:
        """:meth:`Device.upload_array`."""

        self._live()
        descriptor: dict[str, object] = {
            "unit": unit,
            "scale": scale,
            "offset": offset,
            "no_data": no_data,
            "display_range": display_range,
            "colormap": colormap,
            "intrinsics": intrinsics,
            "source_sensor": source_sensor,
            "radiometric_level": radiometric_level,
            "calibration": calibration,
        }
        declarations = _array_provenance_declarations(modality, registration, normalization, interpretation)
        return self._device._upload_array(
            modality, data, session, labels, derived_from, descriptor, declarations, capture_parameters, "loop", self
        )

    def _revoke(self) -> None:
        with self._device._in_flight:  # ordered with every request admission; never waits for one
            self._revoked = True

    def _live(self) -> None:
        if self._revoked:
            raise SessionFenced(
                "this handler's run was settled or abandoned by the executor; its ctx.device is revoked"
            )


def _slot(value: object) -> MqttSlot | None:
    """A usable broker credential, or ``None`` for a missing object, a ``null`` or an empty field."""

    if not isinstance(value, Mapping):
        return None
    principal, password = value.get("principal"), value.get("password")
    if not isinstance(principal, str) or not principal or not isinstance(password, str) or not password:
        return None
    return MqttSlot(principal, password)


def _status_only_call[T](what: str, call: Callable[[], T]) -> T:
    """Run one Hub or presigned call; a failure keeps its class and status only, never the request,
    the server's body or the original exception."""

    try:
        return call()
    except PWSError as exc:
        error = _status_only(exc, what)
    raise error  # outside the handler, so the original is not chained as __context__


def _put_members(
    prepared: _PreparedArray, reservation: Mapping[str, object], admit: Callable[[], AbstractContextManager[None]]
) -> None:
    """PUT the store under the issued grant, each member PUT admitted at its start; an SDK error (a refused admission
    included) keeps its class and status only and anything else (a boto3 client or transfer fault may carry the
    grant) becomes a bare :class:`~phytoworks.errors.TransportError`."""

    what = f"{prepared.modality} Zarr member upload"
    try:
        _zarr_storage.upload_store(prepared.root, reservation, prepared.modality, admit=admit)
        return
    except PWSError as exc:
        error = _status_only(exc, what)
    except Exception:
        error = TransportError(f"{what} failed")
    raise error  # outside the handler, so the original is not chained as __context__


def _action_table(actions: Sequence[Action]) -> dict[str, Action]:
    """The action table by name, refused before any request when ``register()`` could not declare it as given."""

    table: dict[str, Action] = {}
    for action in actions:
        if not isinstance(action, Action):
            raise TypeError("register(actions=...) takes phytoworks.device.Action rows")
        if not action.name or action.name in table:
            raise ValueError(f"action names must be unique and non-empty: {action.name!r}")
        if action.action_type not in ACTION_TYPES:
            raise ValueError(f"{action.name!r}: action_type must be one of {sorted(ACTION_TYPES)}")
        if not callable(action.handler):
            raise TypeError(f"{action.name!r}: handler must be callable")
        if isinstance(action.timeout, bool) or not isinstance(action.timeout, int) or not 1 <= action.timeout <= 86400:
            raise ValueError(f"{action.name!r}: timeout must be whole seconds from 1 to 86400")
        if action.ui is not None and not isinstance(action.ui, Mapping):
            raise TypeError(f"{action.name!r}: ui must be a mapping such as {{'category': 'system'}}")
        _check_name_translation(action)
        if action.remote and (action.action_type == CAPTURE) != (action.name == CAPTURE_ACTION_NAME):
            raise ValueError(
                f"{action.name!r}: a remote CAPTURE must be named {CAPTURE_ACTION_NAME!r}, the name the Hub runs "
                "captures by, and only a CAPTURE may use that name; pass remote=False to run it locally"
            )
        table[action.name] = action
    return table


def _check_name_translation(action: Action) -> None:
    """``nameTranslation`` is a record of locale to display name (``ActionDefinitionSchema``); refuse anything else."""

    translation = action.name_translation
    if translation is None:
        return
    if (
        not isinstance(translation, Mapping)
        or not all(isinstance(locale, str) for locale in translation)
        or not all(isinstance(text, str) for text in translation.values())
    ):
        raise ValueError(f"{action.name!r}: name_translation must map locales to names, such as {{'ko': '관수'}}")


def _declaration(action: Action) -> dict[str, object]:
    """agent-rs's ``ActionDefinition`` fields ; ``timeout`` always, so the Hub never falls back to 30."""

    declared: dict[str, object] = {
        "name": action.name,
        "actionType": action.action_type,
        "handlerType": "mqtt",
        "timeout": action.timeout,
    }
    if action.parameters is not None:
        declared["parameters"] = action.parameters
    if action.name_translation is not None:
        declared["nameTranslation"] = dict(action.name_translation)
    if action.ui is not None:
        declared["metadata"] = {"ui": dict(action.ui)}
    return declared


def _refuse_legacy_captures(rows: Sequence[Mapping[str, object]], device_id: str | None) -> None:
    """An active device-level ``CAPTURE`` under another name would win Console's pick over ``device.capture``
    ."""

    legacy = [
        row
        for row in rows
        if row.get("actionType") == CAPTURE and row.get("name") != CAPTURE_ACTION_NAME and not row.get("componentId")
    ]
    if legacy:
        named = ", ".join(f"{row.get('name')!r} (id {row.get('id')})" for row in legacy)
        routes = ", ".join(f"DELETE /api/v1/devices/{device_id}/actions/{row.get('id')}" for row in legacy)
        raise ValueError(
            f"device {device_id} still has the CAPTURE action {named}, which Console picks instead of "
            f"{CAPTURE_ACTION_NAME!r}. Clean it up: 1. stop every process that still registers "
            f"it -- registering it again revives it; 2. delete it as a user with Device delete rights ({routes}); "
            "3. call register() again"
        )


def _reason(reason: str | None) -> dict[str, object]:
    return {} if reason is None else {"reason": reason}


def _text(model: BaseModel, field: str) -> str:
    value = model.model_extra.get(field) if model.model_extra else None
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Hub returned an upload without {field}")
    return value
