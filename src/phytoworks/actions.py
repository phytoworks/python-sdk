"""Resolve named operator actions against the current spot structure."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped,unused-ignore]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped,unused-ignore]
from jsonschema.exceptions import ValidationError as JsonSchemaError

from .errors import AmbiguousAction, UnknownAction, ValidationError
from .models import SpotStructure
from .models.generated import SpotStructureDeviceAction, SpotStructureDeviceComponentAction


@dataclass(frozen=True, slots=True)
class SugarSpec:
    pattern: str
    mode: str
    input_key: str
    output_key: str


# Keep named modes in step with ProfileParams::to_driver_json_inner in agent-rs.
SUGAR_SPECS = (
    SugarSpec("led.*.control", "percent", "brightness", "value"),
    SugarSpec("pump.control", "discrete", "state", "state"),
    SugarSpec("pump.timed", "timed", "duration", "duration"),
    SugarSpec("peltier.control", "discrete", "mode", "state"),
    SugarSpec("ventilation_fan.control", "discrete", "state", "state"),
    SugarSpec("internal_fan.control", "discrete", "state", "state"),
    SugarSpec("device.environment.set_temperature", "setpoint", "targetValue", "value"),
    SugarSpec("device.environment.set_humidity", "setpoint", "targetValue", "value"),
    SugarSpec("device.manual_mode", "discrete", "enabled", "state"),
)
PASS_THROUGH_NAMES = frozenset({"lcd.display", "lcd.message", "lcd.clear", "device.capture"})


@dataclass(frozen=True, slots=True)
class ResolvedAction:
    """A discovered Hub manual-action target and its schema-checked canonical params."""

    action_def_id: str
    device_id: str
    params: dict[str, Any]
    timeout: int
    name: str


def resolve_action(
    structure: SpotStructure,
    name: str,
    params: Mapping[str, object] | None = None,
    *,
    device: str | None = None,
    component: str | None = None,
) -> ResolvedAction:
    """Use runtime definitions as authority; component="" selects a device-level action."""

    device_id, _, _, action = _find_one(structure, name, device=device, component=component)
    input_params = dict(params or {})
    spec = _sugar_spec(action.name)
    if spec is not None and name == action.name:
        # The shortcut is optional: params already in the declared shape go to the schema check as they are.
        declared = set(input_params) == {"profile"} and isinstance(input_params["profile"], Mapping)
        canonical = input_params if declared else _canonical_params(spec, input_params)
    elif action.name in PASS_THROUGH_NAMES or name == action.id:
        canonical = input_params
    else:
        raise UnknownAction(f"{name!r} has no known sugar mapping; use action UUID for generic schema access")

    # A missing runtime schema skips local validation; Hub's preview path still validates.
    if action.parameters is not None:
        try:
            validator = Draft202012Validator(action.parameters)
            validator.check_schema(action.parameters)
            validator.validate(canonical)
        except (SchemaError, JsonSchemaError) as exc:
            raise ValidationError(
                f"action {action.name!r} params do not match the discovered schema: {exc.message}"
            ) from exc
    return ResolvedAction(action.id, device_id, canonical, action.timeout, action.name)


def describe_action(
    structure: SpotStructure, name: str, *, device: str | None = None, component: str | None = None
) -> dict[str, object]:
    """What an action accepts, read from the structure: declared schema, UI placement, shortcut and how to run it."""

    device_id, identifier, component_identifier, action = _find_one(structure, name, device=device, component=component)
    spec = _sugar_spec(action.name)
    shortcut = None
    if spec is not None:
        value = "ON|OFF" if spec.pattern == "device.manual_mode" else f"<{spec.input_key}>"
        expands_to = {"profile": {"mode": spec.mode, spec.output_key: value}}
        shortcut = {"key": spec.input_key, "type": _shortcut_type(spec), "expandsTo": expands_to}
    ui = action.metadata.ui if action.metadata is not None else None
    return {
        "id": action.id,
        "name": action.name,
        "description": action.description,
        "deviceId": device_id,
        "device": identifier,
        "component": component_identifier,
        "actionType": action.action_type,
        "handlerType": action.handler_type,
        "timeout": action.timeout,
        "ui": ui.model_dump(mode="json", by_alias=True, exclude_unset=True) if ui is not None else None,
        "parameters": action.parameters,
        "shortcut": shortcut,
        # resolve_action takes a name only for a shortcut or a pass-through action; any other needs its id.
        "runBy": "name" if spec is not None or action.name in PASS_THROUGH_NAMES else "id",
    }


def _find_one(
    structure: SpotStructure, name: str, *, device: str | None, component: str | None
) -> tuple[str, str, str | None, SpotStructureDeviceAction | SpotStructureDeviceComponentAction]:
    candidates = _find_candidates(structure, name, device=device, component=component)
    if not candidates:
        raise UnknownAction(f"{name!r} is not available in this spot's current structure")
    if len(candidates) > 1:
        matches = ", ".join(
            f"{component_id or identifier} ({action.id})" for _, identifier, component_id, action in candidates
        )
        selector = "component=" if len({candidate[0] for candidate in candidates}) == 1 else "device= or component="
        if selector == "component=" and any(candidate[2] is None for candidate in candidates):
            selector += " (component='' selects the device-level action)"
        raise AmbiguousAction(f"{name!r} matches multiple actions; pass {selector}. Candidates: {matches}")
    return candidates[0]


def _find_candidates(
    structure: SpotStructure, name: str, *, device: str | None, component: str | None
) -> list[tuple[str, str, str | None, SpotStructureDeviceAction | SpotStructureDeviceComponentAction]]:
    candidates: list[tuple[str, str, str | None, SpotStructureDeviceAction | SpotStructureDeviceComponentAction]] = []
    for discovered_device in structure.devices:
        if discovered_device.deleted_at or (
            device and device not in {discovered_device.id, discovered_device.identifier}
        ):
            continue
        if component is None or component == "":
            candidates.extend(
                (discovered_device.id, discovered_device.identifier, None, action)
                for action in discovered_device.actions
                if not action.deleted_at and name in {action.name, action.id}
            )
        # component="" explicitly selects device-level actions when names overlap.
        if component == "":
            continue
        for discovered_component in discovered_device.components:
            if discovered_component.deleted_at or (
                component and component not in {discovered_component.id, discovered_component.identifier}
            ):
                continue
            candidates.extend(
                (discovered_device.id, discovered_device.identifier, discovered_component.identifier, action)
                for action in discovered_component.actions
                if not action.deleted_at and name in {action.name, action.id}
            )
    return candidates


def _sugar_spec(name: str) -> SugarSpec | None:
    for spec in SUGAR_SPECS:
        if name == spec.pattern or (
            spec.pattern == "led.*.control" and name.startswith("led.") and name.endswith(".control")
        ):
            return spec
    return None


def _shortcut_type(spec: SugarSpec) -> str:
    """The JSON type the shortcut key takes; ``_canonical_params`` checks exactly this."""

    if spec.pattern == "device.manual_mode":
        return "boolean"
    if spec.mode in {"percent", "setpoint"}:
        return "number"
    if spec.mode == "timed":
        return "integer"
    return "string"


_SHORTCUT_TYPES: dict[str, type | tuple[type, ...]] = {
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "string": str,
}


def _canonical_params(spec: SugarSpec, params: dict[str, object]) -> dict[str, Any]:
    kind = _shortcut_type(spec)
    if set(params) != {spec.input_key}:
        declared = '"ON"|"OFF"' if spec.pattern == "device.manual_mode" else f"<{kind}>"
        raise ValidationError(
            f'{spec.pattern} takes {{"{spec.input_key}": <{kind}>}} or its declared shape '
            f'{{"profile": {{"mode": "{spec.mode}", "{spec.output_key}": {declared}}}}}; '
            "`pws edge actions describe` prints the declared schema"
        )
    value = params[spec.input_key]
    # bool is an int subclass: only a boolean shortcut takes one.
    if isinstance(value, bool) is not (kind == "boolean") or not isinstance(value, _SHORTCUT_TYPES[kind]):
        raise ValidationError(f"{spec.pattern} requires a {kind} {spec.input_key}")
    if spec.pattern == "device.manual_mode":
        value = "ON" if value else "OFF"
    return {"profile": {"mode": spec.mode, spec.output_key: value}}
