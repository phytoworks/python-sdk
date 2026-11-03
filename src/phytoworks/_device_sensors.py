"""Device sensor components and readings (python-sdk INV-11, INV-12): what ``Device.register(components=...)`` declares
to the Hub and what ``Device.telemetry()`` turns into points, checked in full before any request.

The declaration is agent-rs's IOBoard numeric sensor topic (``dataType`` FLOAT, ``type`` TELEMETRY, qos 0, not retained,
``telemetryCategory`` SENSOR, ``valueType`` float) under the same Hub schema (``SelfRegisterRequestSchema``), so Console
shows it the way it shows a NITRO sensor.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from numbers import Real
from typing import Any

from ._depth import _finite_number
from ._device_mqtt import _json, _stamp
from ._scalar_policy import media_modalities

__all__ = ["Component", "Readings", "Sensor", "Topic", "camera_report_body"]

# A reading may be at most this far ahead of the Hub's clock (DeviceTelemetryService.validateDataPoints).
_FUTURE_LIMIT = timedelta(seconds=5)
_CATEGORIES = frozenset({"CAMERA", "SENSOR", "ACTUATOR", "COMPOSITE"})
_TELEMETRY_CATEGORIES = frozenset({"SENSOR", "CONTROL_HISTORY"})
# Closed by the Hub (CaptureGroupSchema) and agent-rs (CaptureGroup); the modalities come from the generated policy artifact.
_CAPTURE_GROUPS = frozenset({"top", "side"})
_VALUE_TYPES = frozenset({"boolean", "enum", "percentage", "float", "integer"})

Readings = Mapping[str | tuple[str, str], float | Sequence[tuple[datetime, float]]]


@dataclass(frozen=True, slots=True)
class Topic:
    """One numeric reading a :class:`Component` reports, named like Console's ``temperature.inside``.

    The defaults are agent-rs's IOBoard sensor topic: ``FLOAT``, ``TELEMETRY``, qos 0, not retained, metadata
    ``{"telemetryCategory": "SENSOR", "valueType": "float"}``. ``unit`` is the topic's unit (at most 50 characters) and
    ``label`` the name Console shows when it has no translation for ``name`` (1 to 100 characters, ``metadata.label``).
    ``path`` defaults to ``status/<component identifier>/<name with . as />`` so two components never share one.
    ``metadata`` replaces the default wholesale, as the Hub reads it (an empty mapping sends none); only the keys
    ``telemetryCategory``, ``valueType``, ``description``, ``unit``, ``domain`` and ``stateMapping`` exist, and
    ``label`` joins it.
    """

    name: str
    unit: str | None = field(default=None, kw_only=True)
    label: str | None = field(default=None, kw_only=True)
    path: str | None = field(default=None, kw_only=True)
    metadata: Mapping[str, Any] | None = field(default=None, kw_only=True, repr=False)


@dataclass(frozen=True, slots=True)
class Sensor:
    """One sensor a CAMERA :class:`Component` carries: its ``modality`` (``RGB``, ``THERMAL``, ``FLUORESCENCE``, ``NIR``
    or ``DEPTH``) and optionally the ``model`` it reports, a free string (a catalog key such as
    ``raspberrypi/camera-module-3``, or whatever the vendor calls it)."""

    modality: str
    model: str | None = None


@dataclass(frozen=True, slots=True)
class Component:
    """One part of the device and its topics, as agent-rs registers a component: an IOBoard sensor by default.

    ``name`` defaults to ``identifier``. ``disabled_topics`` names topics to take down: leaving one out of ``topics`` only
    keeps it in Console.

    A camera Console can capture from is ``Component("cam", [], category="CAMERA", capture_group="top",
    sensors=[Sensor("RGB")])``: ``capture_group`` (``top`` or ``side``) and ``sensors`` are sent as the component's
    ``metadata.captureGroup`` and ``metadata.sensors``, which the Hub routes captures by, and only a ``CAMERA`` takes
    them. A camera with a ``capture_group`` must declare ``sensors``, or the Hub cannot tell what it captures; ``None``
    sends none and ``[]`` sends an empty list (a camera with no sensor to capture from).

    A registration that carries components is the full snapshot -- the Hub removes every component it holds that the
    list leaves out. Declare the CAMERA and every SENSOR together in each ``register(components=[...])``; a list with
    only the sensors drops the camera.
    """

    identifier: str
    topics: Sequence[Topic]
    name: str | None = field(default=None, kw_only=True)
    component_type: str = field(default="sdk-sensor", kw_only=True)
    category: str = field(default="SENSOR", kw_only=True)
    disabled_topics: Sequence[str] = field(default=(), kw_only=True)
    capture_group: str | None = field(default=None, kw_only=True)
    sensors: Sequence[Sensor] | None = field(default=None, kw_only=True)


def components_body(components: Sequence[Component]) -> list[dict[str, object]]:
    """The ``components`` of a self-register request, or :class:`ValueError` (:class:`TypeError` for a wrong type) for
    anything the Hub's schema would refuse, before a request is made."""

    if isinstance(components, (str, bytes)) or not isinstance(components, Sequence):
        raise TypeError("register(components=...) takes a list of phytoworks.device.Component")
    if not components:
        raise ValueError("components=[] would remove every component the Hub holds: pass None to leave them alone")
    body: list[dict[str, object]] = []
    seen: set[str] = set()
    for component in components:
        if not isinstance(component, Component):
            raise TypeError("register(components=...) takes phytoworks.device.Component rows")
        _text(component.identifier, "component identifier", 100)
        if component.identifier in seen:
            raise ValueError(f"component identifiers must be unique: {component.identifier!r}")
        seen.add(component.identifier)
        body.append(_component(component))
    return body


def camera_report_body(
    identifier: str, model: str | None, serial: str | None, firmware: str | None
) -> dict[str, object]:
    """A capability report for one component (``ReportCameraCapabilitiesRequestSchema``): the identity the camera
    reports, each key only when given, since the Hub keeps a key the report omits. ``serial`` and ``firmware`` travel
    only with the reported ``model``: the resolver keeps them on the row that model matches."""

    reported = {"model": model, "serial": serial, "firmware": firmware}
    if all(value is None for value in reported.values()):
        raise ValueError("report_camera needs at least one of model, serial or firmware")
    if model is None:
        # the Hub's resolver attaches a reported serial/firmware only to the row its reported model matches
        raise ValueError("report_camera needs model whenever serial or firmware is given")
    component: dict[str, object] = {"identifier": _text(identifier, "component identifier", 100)}
    for key, value in reported.items():
        if value is not None:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{key} must be a non-empty string")
            component[key] = value
    return {"components": [component]}


def _component(component: Component) -> dict[str, object]:
    where = f"component {component.identifier!r}"
    name = component.identifier if component.name is None else component.name
    _text(name, f"{where} name", 255)
    _text(component.component_type, f"{where} component_type", 100)
    if component.category not in _CATEGORIES:
        raise ValueError(f"{where}: category must be one of {sorted(_CATEGORIES)}")
    if isinstance(component.topics, (str, bytes)) or not isinstance(component.topics, Sequence):
        raise TypeError(f"{where}: topics must be a list of Topic")
    names: set[str] = set()
    topics: list[dict[str, object]] = []
    for topic in component.topics:
        if not isinstance(topic, Topic):
            raise TypeError(f"{where}: topics takes phytoworks.device.Topic rows")
        _text(topic.name, f"{where} topic name", 100)
        if topic.name in names:
            raise ValueError(f"{where}: topic names must be unique: {topic.name!r}")
        names.add(topic.name)
        topics.append(_topic(component.identifier, topic))
    if isinstance(component.disabled_topics, (str, bytes)):
        raise TypeError(f"{where}: disabled_topics must be a list of topic names")
    for disabled in component.disabled_topics:
        _text(disabled, f"{where} disabled topic", 100)
    body: dict[str, object] = {
        "identifier": component.identifier,
        "name": name,
        "componentType": component.component_type,
        "category": component.category,
        "topics": topics,
    }
    if component.disabled_topics:
        body["disabledTopics"] = list(component.disabled_topics)
    if routing := _capture_routing(component, where):
        body["metadata"] = routing
    return body


def _capture_routing(component: Component, where: str) -> dict[str, object]:
    """The camera routing metadata agent-rs sends (``captureGroup``, ``sensors``), or ``{}`` when none is declared."""

    routing: dict[str, object] = {}
    group = component.capture_group
    if group is not None:
        if not isinstance(group, str) or group not in _CAPTURE_GROUPS:
            raise ValueError(f"{where}: captureGroup must be one of {sorted(_CAPTURE_GROUPS)}")
        routing["captureGroup"] = group
    if component.sensors is not None:
        routing["sensors"] = _sensors(component.sensors, where)
    if routing and component.category != "CAMERA":
        raise ValueError(f"{where}: captureGroup and sensors belong on a CAMERA component, not {component.category}")
    if group is not None and component.sensors is None:
        raise ValueError(f"{where}: a CAMERA with a capture_group must declare sensors=[Sensor(...)]")
    return routing


def _sensors(sensors: Sequence[Sensor], where: str) -> list[dict[str, str]]:
    if isinstance(sensors, (str, bytes)) or not isinstance(sensors, Sequence):
        raise TypeError(f"{where}: sensors must be a list of Sensor")
    rows: list[dict[str, str]] = []
    for sensor in sensors:
        if not isinstance(sensor, Sensor):
            raise TypeError(f"{where}: sensors takes phytoworks.device.Sensor rows")
        modalities = media_modalities()
        if not isinstance(sensor.modality, str) or sensor.modality not in modalities:
            raise ValueError(f"{where}: sensor modality must be one of {sorted(modalities)}")
        row = {"modality": sensor.modality}
        if sensor.model is not None:
            if not isinstance(sensor.model, str):
                raise ValueError(f"{where}: sensor model must be a string")
            row["model"] = sensor.model
        rows.append(row)
    return rows


def _topic(component: str, topic: Topic) -> dict[str, object]:
    where = f"component {component!r} topic {topic.name!r}"
    path = f"status/{component}/{topic.name.replace('.', '/')}" if topic.path is None else topic.path
    _text(path, f"{where} path", 500)
    body: dict[str, object] = {
        "name": topic.name,
        "path": path,
        "dataType": "FLOAT",
        "type": "TELEMETRY",
        "qos": 0,
        "retained": False,
    }
    if topic.unit is not None:
        body["unit"] = _text(topic.unit, f"{where} unit", 50)
    metadata = _metadata(topic, where)
    if metadata:
        body["metadata"] = metadata
    return body


def _metadata(topic: Topic, where: str) -> dict[str, Any]:
    metadata = _merged(topic, where)
    if unknown := sorted(set(metadata) - set(_METADATA_CHECKS)):
        raise ValueError(f"{where}: unknown metadata keys {unknown}; the Hub keeps only {sorted(_METADATA_CHECKS)}")
    for key, value in metadata.items():
        valid, expected = _METADATA_CHECKS[key]
        if not valid(value):
            raise ValueError(f"{where}: metadata.{key} must be {expected}")
    if "stateMapping" in metadata and metadata.get("valueType") not in (None, "enum", "boolean"):
        raise ValueError(f"{where}: stateMapping goes with valueType enum or boolean, not {metadata['valueType']!r}")
    return metadata


def _merged(topic: Topic, where: str) -> dict[str, Any]:
    """The default metadata or the caller's, with ``label`` joined; live topics carry no derived-measurement keys."""

    if topic.metadata is None:
        metadata: dict[str, Any] = {"telemetryCategory": "SENSOR", "valueType": "float"}
    elif isinstance(topic.metadata, Mapping):
        metadata = dict(topic.metadata)
    else:
        raise TypeError(f"{where}: metadata must be a mapping")
    if topic.label is not None:
        if "label" in metadata:
            raise ValueError(f"{where}: give the label as Topic(label=...) or in metadata, not both")
        metadata["label"] = topic.label
    for forbidden in ("source", "dimensionality"):
        if forbidden in metadata:
            raise ValueError(f"{where}: metadata.{forbidden} is reserved for derived measurements, not live topics")
    return metadata


def _one_of(allowed: frozenset[str]) -> Callable[[object], bool]:
    return lambda value: isinstance(value, str) and value in allowed


def _is_domain(value: object) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(_finite_number(bound) for bound in value)


def _is_state_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and all(
        isinstance(state, str) and isinstance(row, Mapping) and isinstance(row.get("label"), str)
        for state, row in value.items()
    )


# The keys the Hub keeps of a live topic's metadata (AgentRegisteredTopicMetadataSchema, plus the display ``label``) and
# what each must be; the refine that ties stateMapping to valueType is in _metadata.
_METADATA_CHECKS: dict[str, tuple[Callable[[object], bool], str]] = {
    "telemetryCategory": (_one_of(_TELEMETRY_CATEGORIES), f"one of {sorted(_TELEMETRY_CATEGORIES)}"),
    "valueType": (_one_of(_VALUE_TYPES), f"one of {sorted(_VALUE_TYPES)}"),
    "description": (lambda value: isinstance(value, str), "a string"),
    "unit": (lambda value: isinstance(value, str), "a string"),
    "label": (lambda value: isinstance(value, str) and 1 <= len(value) <= 100, "a string of 1 to 100 characters"),
    "domain": (_is_domain, "[min, max], two finite numbers"),
    "stateMapping": (_is_state_mapping, "a mapping of each state to {'label': str}"),
}


def component_ids(payload: Mapping[str, object]) -> dict[str, str]:
    """Local identifiers to Hub UUIDs from the accepted authoritative register response."""

    rows = payload.get("components")
    ids: dict[str, str] = {}
    for row in rows if isinstance(rows, Sequence) and not isinstance(rows, str) else ():
        if not isinstance(row, Mapping):
            continue
        identifier, component_id = row.get("identifier"), row.get("id")
        if isinstance(identifier, str) and identifier and isinstance(component_id, str) and component_id:
            ids[identifier] = component_id
    return ids


def topic_ids(payload: Mapping[str, object]) -> dict[tuple[str, str], str]:
    """Topic ids from a register answer, keyed ``(component identifier, topic name)``; rows without both are skipped."""

    ids: dict[tuple[str, str], str] = {}
    rows = payload.get("components")
    for row in rows if isinstance(rows, Sequence) and not isinstance(rows, str) else ():
        if not isinstance(row, Mapping) or not isinstance(row.get("identifier"), str):
            continue
        topics = row.get("topics")
        for topic in topics if isinstance(topics, Sequence) and not isinstance(topics, str) else ():
            if isinstance(topic, Mapping) and isinstance(topic.get("name"), str) and topic.get("id"):
                ids[(str(row["identifier"]), str(topic["name"]))] = str(topic["id"])
    return ids


def telemetry_points(
    readings: Readings, at: datetime | None, topics: Mapping[tuple[str, str], str]
) -> list[tuple[tuple[str, dict[str, Any]], int]]:
    """Every reading as ``((topic id, point), serialized size)`` in the order given, or :class:`ValueError` for the
    first thing the Hub would refuse -- before anything is sent."""

    if not isinstance(readings, Mapping):
        raise TypeError("telemetry(readings) takes a mapping of topic name to a number or a list of (time, number)")
    if not readings:
        raise ValueError("no readings to send")
    if not topics:
        raise ValueError("this Device has no sensor topics yet: register(..., components=[Component(...)]) first")
    now = _now()
    default = _stamp(_moment(now if at is None else at, now, "at"))
    points: list[tuple[tuple[str, dict[str, Any]], int]] = []
    for key, reading in readings.items():
        topic = _resolve(key, topics)
        if isinstance(reading, (str, bytes)) or not (isinstance(reading, Sequence) or _is_number(reading)):
            raise ValueError(f"{key!r}: give a number or a list of (time, number) points")
        for stamp, value in [(default, reading)] if _is_number(reading) else _timed(key, reading, now):
            point = {"timestamp": stamp, "value": _value(key, value)}
            points.append(((topic, point), len(_json(point))))
    return points


def _timed(key: object, reading: object, now: datetime) -> list[tuple[str, object]]:
    if not isinstance(reading, Sequence) or not reading:
        raise ValueError(f"{key!r}: no points to send")
    timed: list[tuple[str, object]] = []
    for point in reading:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 2:
            raise ValueError(f"{key!r}: each point is (time, number)")
        when, value = point
        timed.append((_stamp(_moment(when, now, f"{key!r} time")), value))
    return timed


def _resolve(key: object, topics: Mapping[tuple[str, str], str]) -> str:
    if isinstance(key, tuple):
        if key not in topics:
            raise ValueError(f"no registered topic {key!r}; keys are (component identifier, topic name)")
        return topics[key]
    matches = [(component, topic_id) for (component, name), topic_id in topics.items() if name == key]
    if not matches:
        raise ValueError(f"no registered topic named {key!r}")
    if len(matches) > 1:
        owners = sorted(component for component, _id in matches)
        raise ValueError(f"topic {key!r} exists on components {owners}: use (component identifier, name)")
    return matches[0][1]


def _moment(value: object, now: datetime, what: str) -> datetime:
    """``value`` in UTC; a time without a zone or more than the Hub allows ahead of ``now`` is refused. The Hub reads the
    time as written (to the millisecond), so that is the one compared."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what}: give a timezone-aware datetime")
    moment = value.astimezone(UTC)
    if moment.replace(microsecond=moment.microsecond // 1000 * 1000) - now > _FUTURE_LIMIT:
        raise ValueError(f"{what}: more than {_FUTURE_LIMIT.seconds} s ahead of now; the Hub refuses it")
    return moment


def _value(key: object, value: object) -> float:
    if not _is_number(value):
        raise ValueError(f"{key!r}: a reading is a number, not {type(value).__name__}")
    try:
        number = float(value)  # type: ignore[arg-type]
    except OverflowError:
        raise ValueError(f"{key!r}: reading is out of range") from None
    if not math.isfinite(number):
        raise ValueError(f"{key!r}: a reading must be finite, not {number}")
    return number


def _is_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _text(value: object, what: str, longest: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= longest:
        raise ValueError(f"{what} must be a string of 1 to {longest} characters")
    return value


def _now() -> datetime:
    return datetime.now(UTC)
