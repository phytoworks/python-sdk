"""Synchronous and asynchronous operator-facing resource facades."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import mimetypes
import os
import queue
import re
import secrets
import shutil
import tempfile
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import BaseModel, SecretStr

from . import _depth, _multiband, _multiband_write, _zarr_storage
from ._media_shared import (
    _MISSING,
    ArrayUploadResult,
    BoundOperation,
    OperationSpec,
    _array_provenance_declarations,
    _array_reservation,
    _array_reservation_extras,
    _array_result,
    _build_operation_table,
    _image_upload_body,
    _looks_like_uuid,
    _operation,
    _parse_model,
    _prepare_array,
    _PreparedArray,
    _registered_multispectral_declaration,
    _registered_provenance_declarations,
    _upload_source,
)
from ._multiband import MultibandData
from ._scalar_policy import depth_policy
from ._transport import AsyncTransport, Page, ProgressCallback, Transport
from .actions import ResolvedAction, resolve_action
from .auth import ApiKeyCredential, Credential, SessionCredential
from .config import DEFAULT_BASE_URL, Config, DeviceJwtStore
from .device_auth import DeviceSessionCredential
from .errors import (
    ActionFailed,
    ActionPreviewUnavailable,
    ActionTimeout,
    AuthError,
    NotFoundError,
    OrganizationScopeError,
    PermissionError,
    PWSError,
    RateLimitError,
    TransportError,
    ValidationError,
    _status_only,
)
from .models import (
    AccessInfo,
    AccessKey,
    ActionExecutionSearchResult,
    ActionExecutionStatus,
    Agent,
    BandProvenance,
    CaptureSession,
    CaptureSessionDetail,
    CaptureSessionDetailMedia,
    CompleteImageUploadResponse,
    Component,
    CreatedSpot,
    Device,
    DeviceStatus,
    ManualActionDryRun,
    ManualActionExecution,
    MediaAsset,
    MediaAssetPresignedUrl,
    Organization,
    Rule,
    RuleExecution,
    Spot,
    SpotStructure,
    Telemetry,
    TelemetryBatch,
    TelemetryBatchExport,
    TelemetryBatchRollup,
    TelemetryTopics,
)
from .models.generated import (
    ActionExecutionBatchStatus,
    ActionExecutionStatusError,
    UploadImageResponse,
    ZarrFiles,
)

if TYPE_CHECKING:
    import numpy as np


_OPERATION_TABLE = _build_operation_table(
    cast(
        dict[str, OperationSpec[BaseModel]],
        {
            "ORGANIZATIONS": OperationSpec("GET", "/organizations", Organization, pagination=True),
            "ORGANIZATION": OperationSpec("GET", "/organizations/{id}", Organization),
            "ORGANIZATION_BY_SLUG": OperationSpec("GET", "/organizations/slug/{slug}", Organization),
            "USER_ORGANIZATIONS": OperationSpec("GET", "/organizations/user/{userId}", Organization, pagination=True),
            "ACCESS_INFO": OperationSpec("GET", "/auth/access/me", AccessInfo),
            "SPOTS": OperationSpec("GET", "/spots", Spot, pagination=True),
            "SPOT": OperationSpec("GET", "/spots/{id}", Spot),
            "SPOT_BY_SLUG": OperationSpec("GET", "/spots/by-slug/{slug}", Spot),
            "SPOT_STRUCTURE": OperationSpec("GET", "/spots/{id}/structure", SpotStructure),
            "SPOT_CREATE": OperationSpec("POST", "/spots", CreatedSpot),
            "AGENTS": OperationSpec("GET", "/agents/management", Agent, pagination=True),
            "AGENT_CREATE": OperationSpec("POST", "/agents/management", Agent),
            "MANUAL_ACTION_PREVIEW": OperationSpec("POST", "/actions/executions/preview", ManualActionDryRun),
            "MANUAL_ACTION_RUN": OperationSpec("POST", "/actions/executions/manual", ManualActionExecution),
            "ACTION_EXECUTION": OperationSpec("GET", "/actions/executions/{id}", ActionExecutionStatus, waiter=True),
            "ACTION_EXECUTION_BATCH": OperationSpec(
                "GET", "/actions/executions/batch", ActionExecutionBatchStatus, waiter=True
            ),
            "ACTION_EXECUTIONS": OperationSpec("GET", "/actions/executions", ActionExecutionSearchResult),
            "DEVICES": OperationSpec("GET", "/devices", Device, pagination=True),
            "DEVICE": OperationSpec("GET", "/devices/{id}", Device),
            "DEVICE_STATUS": OperationSpec("GET", "/devices/{id}/status", DeviceStatus),
            "COMPONENTS": OperationSpec("GET", "/components", Component, pagination=True),
            "SPOT_RULES": OperationSpec("GET", "/spots/{spotId}/rules", Rule, pagination=True),
            "SPOT_RULE": OperationSpec("GET", "/spots/{spotId}/rules/{id}", Rule),
            "SPOT_RULE_EXECUTIONS": OperationSpec("GET", "/spots/{spotId}/rules/{id}/executions", RuleExecution),
            "TELEMETRY": OperationSpec("GET", "/agents/management/{id}/telemetry", Telemetry),
            "TELEMETRY_BATCH": OperationSpec("GET", "/agents/management/{id}/telemetry/batch", TelemetryBatch),
            "TELEMETRY_BATCH_EXPORT": OperationSpec(
                "GET", "/agents/management/{id}/telemetry/batch-export", TelemetryBatchExport
            ),
            "TELEMETRY_EXPORT": OperationSpec("POST", "/agents/management/{id}/telemetry/export", None),
            "TELEMETRY_BATCH_ROLLUP": OperationSpec(
                "GET", "/agents/management/{id}/telemetry/batch-rollup", TelemetryBatchRollup
            ),
            "TELEMETRY_TOPICS": OperationSpec("GET", "/agents/management/{id}/topics", TelemetryTopics),
            "ACCESS_KEYS": OperationSpec("GET", "/agents/management/{id}/access-keys", AccessKey),
            "ACCESS_KEY_ISSUE": OperationSpec("POST", "/agents/management/{id}/access-keys", AccessKey),
            "ACCESS_KEY_ROTATE": OperationSpec("POST", "/agents/management/{id}/access-keys/{keyId}/rotate", AccessKey),
            "ACCESS_KEY_REISSUE": OperationSpec(
                "POST", "/agents/management/{id}/access-keys/{keyId}/reissue", AccessKey
            ),
            "ACCESS_KEY_REVOKE": OperationSpec("DELETE", "/agents/management/{id}/access-keys/{keyId}", None),
            "ACCESS_KEY_PLAIN": OperationSpec("GET", "/agents/management/{id}/access-keys/{keyId}/plain-key", None),
            "CAPTURES": OperationSpec("GET", "/media/capture-sessions", CaptureSession, pagination=True),
            "CAPTURE": OperationSpec("GET", "/media/capture-sessions/{id}", CaptureSessionDetail),
            "MEDIA": OperationSpec("GET", "/media/assets", MediaAsset, pagination=True),
            "MEDIA_UPLOAD": OperationSpec("POST", "/media/assets/upload-image", UploadImageResponse),
            "MEDIA_COMPLETE_UPLOAD": OperationSpec(
                "POST", "/media/assets/complete-image-upload", CompleteImageUploadResponse
            ),
            "MEDIA_ASSET": OperationSpec("GET", "/media/assets/{id}", MediaAsset),
            "MEDIA_LATEST": OperationSpec("GET", "/media/assets/spots/{spotId}/latest", MediaAsset),
            "MEDIA_PRESIGNED_URL": OperationSpec("GET", "/media/assets/{id}/presigned-url", MediaAssetPresignedUrl),
            "MEDIA_ZARR_FILES": OperationSpec("GET", "/media/assets/{id}/zarr-files", ZarrFiles),
            "MEDIA_BAND_PROVENANCE": OperationSpec("GET", "/media/assets/{id}/band-provenance", BandProvenance),
            "MEDIA_ZARR_UPLOAD": OperationSpec("POST", "/media/assets/zarr/upload", None),
            "MEDIA_ZARR_COMPLETE": OperationSpec("POST", "/media/assets/zarr/complete", None),
        },
    )
)


class Route:
    """Every checked Hub operation the facades call under ``/api/v1``."""

    ORGANIZATIONS: OperationSpec[Organization] = cast(OperationSpec[Organization], _OPERATION_TABLE["ORGANIZATIONS"])
    ORGANIZATION: OperationSpec[Organization] = cast(OperationSpec[Organization], _OPERATION_TABLE["ORGANIZATION"])
    ORGANIZATION_BY_SLUG: OperationSpec[Organization] = cast(
        OperationSpec[Organization], _OPERATION_TABLE["ORGANIZATION_BY_SLUG"]
    )
    USER_ORGANIZATIONS: OperationSpec[Organization] = cast(
        OperationSpec[Organization], _OPERATION_TABLE["USER_ORGANIZATIONS"]
    )
    ACCESS_INFO: OperationSpec[AccessInfo] = cast(OperationSpec[AccessInfo], _OPERATION_TABLE["ACCESS_INFO"])
    SPOTS: OperationSpec[Spot] = cast(OperationSpec[Spot], _OPERATION_TABLE["SPOTS"])
    SPOT: OperationSpec[Spot] = cast(OperationSpec[Spot], _OPERATION_TABLE["SPOT"])
    SPOT_BY_SLUG: OperationSpec[Spot] = cast(OperationSpec[Spot], _OPERATION_TABLE["SPOT_BY_SLUG"])
    SPOT_STRUCTURE: OperationSpec[SpotStructure] = cast(
        OperationSpec[SpotStructure], _OPERATION_TABLE["SPOT_STRUCTURE"]
    )
    SPOT_CREATE: OperationSpec[CreatedSpot] = cast(OperationSpec[CreatedSpot], _OPERATION_TABLE["SPOT_CREATE"])
    AGENTS: OperationSpec[Agent] = cast(OperationSpec[Agent], _OPERATION_TABLE["AGENTS"])
    AGENT_CREATE: OperationSpec[Agent] = cast(OperationSpec[Agent], _OPERATION_TABLE["AGENT_CREATE"])
    MANUAL_ACTION_PREVIEW: OperationSpec[ManualActionDryRun] = cast(
        OperationSpec[ManualActionDryRun], _OPERATION_TABLE["MANUAL_ACTION_PREVIEW"]
    )
    MANUAL_ACTION_RUN: OperationSpec[ManualActionExecution] = cast(
        OperationSpec[ManualActionExecution], _OPERATION_TABLE["MANUAL_ACTION_RUN"]
    )
    ACTION_EXECUTION: OperationSpec[ActionExecutionStatus] = cast(
        OperationSpec[ActionExecutionStatus], _OPERATION_TABLE["ACTION_EXECUTION"]
    )
    ACTION_EXECUTION_BATCH: OperationSpec[ActionExecutionBatchStatus] = cast(
        OperationSpec[ActionExecutionBatchStatus], _OPERATION_TABLE["ACTION_EXECUTION_BATCH"]
    )
    ACTION_EXECUTIONS: OperationSpec[ActionExecutionSearchResult] = cast(
        OperationSpec[ActionExecutionSearchResult], _OPERATION_TABLE["ACTION_EXECUTIONS"]
    )
    DEVICES: OperationSpec[Device] = cast(OperationSpec[Device], _OPERATION_TABLE["DEVICES"])
    DEVICE: OperationSpec[Device] = cast(OperationSpec[Device], _OPERATION_TABLE["DEVICE"])
    DEVICE_STATUS: OperationSpec[DeviceStatus] = cast(OperationSpec[DeviceStatus], _OPERATION_TABLE["DEVICE_STATUS"])
    COMPONENTS: OperationSpec[Component] = cast(OperationSpec[Component], _OPERATION_TABLE["COMPONENTS"])
    SPOT_RULES: OperationSpec[Rule] = cast(OperationSpec[Rule], _OPERATION_TABLE["SPOT_RULES"])
    SPOT_RULE: OperationSpec[Rule] = cast(OperationSpec[Rule], _OPERATION_TABLE["SPOT_RULE"])
    SPOT_RULE_EXECUTIONS: OperationSpec[RuleExecution] = cast(
        OperationSpec[RuleExecution], _OPERATION_TABLE["SPOT_RULE_EXECUTIONS"]
    )
    TELEMETRY: OperationSpec[Telemetry] = cast(OperationSpec[Telemetry], _OPERATION_TABLE["TELEMETRY"])
    TELEMETRY_BATCH: OperationSpec[TelemetryBatch] = cast(
        OperationSpec[TelemetryBatch], _OPERATION_TABLE["TELEMETRY_BATCH"]
    )
    TELEMETRY_BATCH_EXPORT: OperationSpec[TelemetryBatchExport] = cast(
        OperationSpec[TelemetryBatchExport], _OPERATION_TABLE["TELEMETRY_BATCH_EXPORT"]
    )
    TELEMETRY_EXPORT: OperationSpec[BaseModel] = _OPERATION_TABLE["TELEMETRY_EXPORT"]
    TELEMETRY_BATCH_ROLLUP: OperationSpec[TelemetryBatchRollup] = cast(
        OperationSpec[TelemetryBatchRollup], _OPERATION_TABLE["TELEMETRY_BATCH_ROLLUP"]
    )
    TELEMETRY_TOPICS: OperationSpec[TelemetryTopics] = cast(
        OperationSpec[TelemetryTopics], _OPERATION_TABLE["TELEMETRY_TOPICS"]
    )
    ACCESS_KEYS: OperationSpec[AccessKey] = cast(OperationSpec[AccessKey], _OPERATION_TABLE["ACCESS_KEYS"])
    ACCESS_KEY_ISSUE: OperationSpec[AccessKey] = cast(OperationSpec[AccessKey], _OPERATION_TABLE["ACCESS_KEY_ISSUE"])
    ACCESS_KEY_ROTATE: OperationSpec[AccessKey] = cast(OperationSpec[AccessKey], _OPERATION_TABLE["ACCESS_KEY_ROTATE"])
    ACCESS_KEY_REISSUE: OperationSpec[AccessKey] = cast(
        OperationSpec[AccessKey], _OPERATION_TABLE["ACCESS_KEY_REISSUE"]
    )
    ACCESS_KEY_REVOKE: OperationSpec[BaseModel] = _OPERATION_TABLE["ACCESS_KEY_REVOKE"]
    ACCESS_KEY_PLAIN: OperationSpec[BaseModel] = _OPERATION_TABLE["ACCESS_KEY_PLAIN"]
    CAPTURES: OperationSpec[CaptureSession] = cast(OperationSpec[CaptureSession], _OPERATION_TABLE["CAPTURES"])
    CAPTURE: OperationSpec[CaptureSessionDetail] = cast(
        OperationSpec[CaptureSessionDetail], _OPERATION_TABLE["CAPTURE"]
    )
    MEDIA: OperationSpec[MediaAsset] = cast(OperationSpec[MediaAsset], _OPERATION_TABLE["MEDIA"])
    MEDIA_UPLOAD: OperationSpec[UploadImageResponse] = cast(
        OperationSpec[UploadImageResponse], _OPERATION_TABLE["MEDIA_UPLOAD"]
    )
    MEDIA_COMPLETE_UPLOAD: OperationSpec[CompleteImageUploadResponse] = cast(
        OperationSpec[CompleteImageUploadResponse], _OPERATION_TABLE["MEDIA_COMPLETE_UPLOAD"]
    )
    MEDIA_ASSET: OperationSpec[MediaAsset] = cast(OperationSpec[MediaAsset], _OPERATION_TABLE["MEDIA_ASSET"])
    MEDIA_LATEST: OperationSpec[MediaAsset] = cast(OperationSpec[MediaAsset], _OPERATION_TABLE["MEDIA_LATEST"])
    MEDIA_PRESIGNED_URL: OperationSpec[MediaAssetPresignedUrl] = cast(
        OperationSpec[MediaAssetPresignedUrl], _OPERATION_TABLE["MEDIA_PRESIGNED_URL"]
    )
    MEDIA_ZARR_FILES: OperationSpec[ZarrFiles] = cast(OperationSpec[ZarrFiles], _OPERATION_TABLE["MEDIA_ZARR_FILES"])
    MEDIA_BAND_PROVENANCE: OperationSpec[BandProvenance] = cast(
        OperationSpec[BandProvenance], _OPERATION_TABLE["MEDIA_BAND_PROVENANCE"]
    )
    MEDIA_ZARR_UPLOAD: OperationSpec[BaseModel] = _OPERATION_TABLE["MEDIA_ZARR_UPLOAD"]
    MEDIA_ZARR_COMPLETE: OperationSpec[BaseModel] = _OPERATION_TABLE["MEDIA_ZARR_COMPLETE"]

    @classmethod
    def all(cls) -> tuple[tuple[str, str], ...]:
        return tuple((operation.method, operation.path) for operation in _OPERATION_TABLE.values())


RESOURCE_NAMES = (
    "organizations",
    "spots",
    "devices",
    "components",
    "rules",
    "telemetry",
    "captures",
    "media",
    "actions",
    "agents",
    "access_keys",
)


@dataclass(frozen=True, slots=True)
class StatusBatchResult:
    """Best-effort device status fan-out result."""

    results: dict[str, DeviceStatus]
    failed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IssuedAccessKey:
    """A newly issued, rotated or reissued agent key: its metadata plus the secret, masked in repr/str."""

    key: AccessKey
    secret: SecretStr


@dataclass(slots=True)
class Execution:
    """An accepted manual execution; result is populated when a caller opts into waiting."""

    id: str
    model: ManualActionExecution
    timeout: float
    result: ActionExecutionStatus | None = None

    @property
    def status(self) -> str:
        return _execution_status(self.result) if self.result is not None else self.model.status


def _uuid7() -> str:
    """Generate an RFC 9562 UUID7 on Python 3.12 without another dependency."""

    millis = time.time_ns() // 1_000_000
    random_bits = secrets.randbits(74)
    value = ((millis & ((1 << 48) - 1)) << 80) | (7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 2 << 62
    value |= random_bits & ((1 << 62) - 1)
    return str(UUID(int=value))


def _manual_execution_body(execution_id: str, resolved: ResolvedAction) -> dict[str, object]:
    return {
        "executionId": execution_id,
        "actionDefId": resolved.action_def_id,
        "deviceId": resolved.device_id,
        "params": resolved.params,
    }


def _manual_retry_delay(exc: PWSError, attempt: int) -> float | None:
    if attempt >= 2:
        return None
    if isinstance(exc, RateLimitError):
        return float(exc.retry_after) if exc.retry_after is not None else 0.25 * (2.0**attempt)
    if isinstance(exc, TransportError) and (exc.status_code is None or exc.status_code >= 500):
        return 0.25 * (2.0**attempt)
    return None


def _execution_status(result: ActionExecutionStatus) -> str:
    root = result.root
    if isinstance(root, ActionExecutionStatusError):
        raise NotFoundError(root.error)
    return root.status


_TERMINAL_STATUSES = frozenset({"SUCCESS", "FAILED", "CANCELLED", "TIMEOUT"})


def _terminal_result(result: ActionExecutionStatus) -> bool:
    return _execution_status(result) in _TERMINAL_STATUSES


def _terminal_error(result: ActionExecutionStatus) -> ActionFailed | ActionTimeout | None:
    status = _execution_status(result)
    if status in {"FAILED", "CANCELLED", "TIMEOUT"}:
        root = result.root
        if isinstance(root, ActionExecutionStatusError):
            raise NotFoundError(root.error)
        message = root.error or f"Action execution {status.lower()}"
        if status == "TIMEOUT":
            return ActionTimeout(
                f"Hub gave up waiting for the device: {message}", execution_id=root.execution_id, status=status
            )
        return ActionFailed(message, execution_id=root.execution_id, status=status)
    return None


def _completed_wait(
    timeouts: dict[str, float], identifier: str, result: ActionExecutionStatus
) -> ActionExecutionStatus:
    timeouts.pop(identifier, None)
    error = _terminal_error(result)
    if error is not None:
        raise error
    return result


def _wait_deadline(timeout: float) -> float:
    if timeout < 0:
        raise ValueError("action wait timeout must be non-negative")
    return time.monotonic() + timeout


def _wait_deadlines(
    identifiers: Iterable[str], timeouts: Mapping[str, float], timeout: float | None
) -> dict[str, float]:
    keys = tuple(identifiers)
    if timeout is None and any(identifier not in timeouts for identifier in keys):
        raise ValidationError("Unknown action execution IDs require an explicit timeout")
    now = time.monotonic()
    return {
        identifier: now + _validated_timeout(timeout if timeout is not None else timeouts[identifier])
        for identifier in keys
    }


def _validated_timeout(timeout: float) -> float:
    if timeout < 0:
        raise ValueError("action wait timeout must be non-negative")
    return timeout


def _next_wait_delay(pending: Iterable[str], deadlines: Mapping[str, float], interval: float) -> float:
    identifier = min(pending, key=lambda item: deadlines[item])
    remaining = deadlines[identifier] - time.monotonic()
    return max(0.0, min(interval, remaining))


def _wait_expired(identifier: str, *, status: str | None = None) -> ActionTimeout:
    return ActionTimeout(
        f"Action execution {identifier} did not finish before the SDK deadline; "
        f"the device may still be running. Check with `pws edge actions get {identifier}`.",
        execution_id=identifier,
        status=status,
    )


def _wait_many_expired(
    pending: Mapping[str, None],
    deadlines: Mapping[str, float],
    results: Mapping[str, ActionExecutionStatus],
    statuses: Mapping[str, str],
) -> ActionTimeout:
    identifier = min(pending, key=lambda item: deadlines[item])
    return ActionTimeout(
        f"Action execution {identifier} did not finish before the SDK deadline; "
        f"pending: {', '.join(pending)}. Check with `pws edge actions get {identifier}`.",
        execution_id=identifier,
        status=statuses.get(identifier),
        results=results,
        pending=tuple(pending),
    )


def _definition_timeout(structure: SpotStructure, action_def_id: str) -> int | None:
    for device in structure.devices:
        for action in device.actions:
            if action.id == action_def_id:
                return action.timeout
        for component in device.components:
            for component_action in component.actions:
                if component_action.id == action_def_id:
                    return component_action.timeout
    return None


def _status_action_def_id(result: ActionExecutionStatus) -> str:
    if isinstance(result.root, ActionExecutionStatusError):
        raise NotFoundError(result.root.error)
    action_def_id = result.root.action_def_id
    if action_def_id is None:
        raise ValidationError("Execution has no action definition; pass timeout=")
    return action_def_id


def _remember_timeout(timeouts: dict[str, float], execution_id: str, timeout: float, status: str) -> None:
    if status in {"SUCCESS", "FAILED", "CANCELLED", "TIMEOUT"}:
        timeouts.pop(execution_id, None)
        return
    timeouts.pop(execution_id, None)
    if len(timeouts) >= 1024:
        timeouts.pop(next(iter(timeouts)))
    timeouts[execution_id] = timeout


@dataclass(frozen=True, slots=True)
class Identity:
    """The signed-in operator and every organization they belong to (``pws auth whoami``).

    ``user_id`` and ``email`` come from the session JWT the Hub minted; each
    organization's ``metadata["userRole"]`` is the caller's role in it.
    """

    user_id: str
    email: str | None
    token_expires_at: datetime | None
    organizations: list[Organization]


class RawResource:
    """Escape hatch for a stable Hub endpoint not yet modeled by the SDK."""

    def __init__(self, client: PWS) -> None:
        self._client = client

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json: object | None = None,
    ) -> object:
        _refuse_access_key_path(path)
        return self._client._raw_request(method, path, params=params, json_body=json)


class OrganizationResource:
    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, *, page: int | None = None, limit: int | None = None) -> Page[Organization]:
        params = _page_params(page, limit)
        return self._client._page_request(_operation(Route.ORGANIZATIONS), params=params, total_limit=limit)

    def for_user(self, user_id: str) -> Page[Organization]:
        """Every organization ``user_id`` belongs to; the Hub allows only the user themselves or an admin."""

        return self._client._page_request(_operation(Route.USER_ORGANIZATIONS, userId=user_id))

    def get(self, identifier: str) -> Organization:
        if _looks_like_uuid(identifier):
            return self._client._model_request(_operation(Route.ORGANIZATION, id=identifier))
        return self._client._model_request(_operation(Route.ORGANIZATION_BY_SLUG, slug=identifier))


class SpotResource:
    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, *, page: int | None = None, limit: int | None = None) -> Page[Spot]:
        return self._client._page_request(
            _operation(Route.SPOTS), params=_skip_take_page_params(page, limit), total_limit=limit
        )

    def get(self, identifier: str) -> SpotHandle:
        if _looks_like_uuid(identifier):
            spot = self._client._model_request(_operation(Route.SPOT, id=identifier))
        else:
            spot = self._client._model_request(_operation(Route.SPOT_BY_SLUG, slug=identifier))
        return SpotHandle(self._client, spot)

    def create(self, name: str, *, slug: str, description: str | None = None) -> CreatedSpot:
        operation = _operation(Route.SPOT_CREATE)
        return _parse_model(self._client._send(operation, _spot_body(name, slug, description)), CreatedSpot)


class AgentResource:
    """Device agents: list and create (a key is then issued with ``access_keys.issue``)."""

    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, *, spot: str | None = None) -> list[Agent]:
        """Every agent of the organization, or of one spot, read to the last page."""

        return list(self._client._page_request(_operation(Route.AGENTS), params=_agent_list_params(spot)))

    def create(self, name: str, *, identifier: str, spot: str) -> Agent:
        body = {"name": name, "identifier": identifier, "spotId": spot}
        return _parse_model(self._client._send(_operation(Route.AGENT_CREATE), body), Agent)


class SpotHandle:
    """A resolved spot with structure, action preview, and read-only rules."""

    def __init__(self, client: PWS, spot: Spot) -> None:
        self._client = client
        self._spot = spot
        self.rules = SpotRuleResource(client, spot.id)
        self.actions = SpotActionResource(self)

    @property
    def id(self) -> str:
        return self._spot.id

    @property
    def name(self) -> str:
        return self._spot.name

    @property
    def slug(self) -> str | None:
        return self._spot.slug

    @property
    def model(self) -> Spot:
        return self._spot

    def structure(self) -> SpotStructure:
        return self._client._model_request(_operation(Route.SPOT_STRUCTURE, id=self.id))

    def captures(self, **filters: str | int | None) -> Page[CaptureSession]:
        """Capture sessions scoped to this spot (same filters as ``pws.captures.list``)."""

        return self._client.captures.list(spot=self.id, **filters)  # type: ignore[arg-type]


class SpotActionResource:
    """Resolve action sugar and preview the exact manual request without executing it."""

    def __init__(self, spot: SpotHandle) -> None:
        self._spot = spot

    def resolve(
        self,
        name: str,
        params: Mapping[str, object] | None = None,
        *,
        device: str | None = None,
        component: str | None = None,
    ) -> ResolvedAction:
        return resolve_action(self._spot.structure(), name, params, device=device, component=component)

    def preview(
        self,
        name: str,
        params: Mapping[str, object] | None = None,
        *,
        device: str | None = None,
        component: str | None = None,
        capture_session_id: str | None = None,
        capture_session_options: Mapping[str, object] | None = None,
    ) -> ManualActionDryRun:
        resolved = self.resolve(name, params, device=device, component=component)
        body: dict[str, object] = {
            "actionDefId": resolved.action_def_id,
            "deviceId": resolved.device_id,
            "params": resolved.params,
        }
        if capture_session_id is not None:
            body["captureSessionId"] = capture_session_id
        if capture_session_options is not None:
            body["captureSessionOptions"] = dict(capture_session_options)
        try:
            payload = self._spot._client._raw_request(
                Route.MANUAL_ACTION_PREVIEW.method,
                Route.MANUAL_ACTION_PREVIEW.path,
                json_body=body,
            )
        except PWSError as exc:
            if isinstance(exc, NotFoundError) or exc.status_code == 405:
                raise ActionPreviewUnavailable(
                    "This Hub does not support action preview",
                    status_code=exc.status_code,
                    request_id=exc.request_id,
                ) from exc
            raise
        return _parse_model(payload, ManualActionDryRun)

    def run(
        self,
        name: str,
        params: Mapping[str, object] | None = None,
        *,
        device: str | None = None,
        component: str | None = None,
        wait: bool = False,
        execution_id: str | None = None,
    ) -> Execution:
        resolved = self.resolve(name, params, device=device, component=component)
        execution_id = _uuid7() if execution_id is None else execution_id
        body = _manual_execution_body(execution_id, resolved)
        retries = 0
        refreshed = False
        while True:
            try:
                payload = self._spot._client._raw_request(
                    Route.MANUAL_ACTION_RUN.method, Route.MANUAL_ACTION_RUN.path, json_body=body
                )
                break
            except NotFoundError as exc:
                if refreshed:
                    exc.execution_id = execution_id
                    raise
                resolved = self.resolve(name, params, device=device, component=component)
                body = _manual_execution_body(execution_id, resolved)
                refreshed = True
            except PWSError as exc:
                delay = _manual_retry_delay(exc, retries)
                if delay is None:
                    exc.execution_id = execution_id
                    raise
                time.sleep(delay)
                retries += 1
        model = _parse_model(payload, ManualActionExecution)
        if model.execution_id != execution_id:
            raise ValidationError("Hub returned a different action execution ID")
        execution = Execution(execution_id, model, resolved.timeout + 15)
        _remember_timeout(self._spot._client.actions._timeouts, execution_id, execution.timeout, model.status)
        if wait:
            execution.result = self._spot._client.actions.wait(execution_id)
        return execution


class ActionResource:
    """Status reads and bounded polling for accepted manual actions."""

    def __init__(self, client: PWS) -> None:
        self._client = client
        self._timeouts: dict[str, float] = {}

    def get(self, identifier: str) -> ActionExecutionStatus:
        result = self._client._model_request(_operation(Route.ACTION_EXECUTION, id=identifier))
        _execution_status(result)
        return result

    def _definition_budget(self, result: ActionExecutionStatus) -> float:
        action_def_id = _status_action_def_id(result)
        for spot in self._client.spots.list():
            structure = self._client._model_request(_operation(Route.SPOT_STRUCTURE, id=spot.id))
            timeout = _definition_timeout(structure, action_def_id)
            if timeout is not None:
                return timeout + 15
        raise ValidationError(f"Action definition {action_def_id!r} is unavailable; pass timeout=")

    def list(
        self,
        *,
        device: str | None = None,
        action: str | None = None,
        status: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> ActionExecutionSearchResult:
        params: dict[str, object] = {**_page_params(page, limit)}
        if device is not None:
            params["deviceId"] = device
        if action is not None:
            params["actionDefId"] = action
        if status is not None:
            params["status"] = status
        return _parse_model(
            self._client._request(_operation(Route.ACTION_EXECUTIONS), params=params), ActionExecutionSearchResult
        )

    def wait(self, identifier: str, *, timeout: float | None = None) -> ActionExecutionStatus:
        first = None
        budget = timeout if timeout is not None else self._timeouts.get(identifier)
        if budget is None:
            first = self.get(identifier)
            if _terminal_result(first):
                return _completed_wait(self._timeouts, identifier, first)
            budget = self._definition_budget(first)
        deadline = _wait_deadline(budget)
        interval = 2.0
        result = first
        while True:
            if result is None:
                result = self.get(identifier)
            if _terminal_result(result):
                return _completed_wait(self._timeouts, identifier, result)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _wait_expired(identifier, status=_execution_status(result))
            time.sleep(min(interval, remaining))
            interval = min(interval * 1.3, 5.0)
            result = None

    wait_for_execution = wait

    def wait_many(
        self, identifiers: Iterable[str], *, timeout: float | None = None
    ) -> dict[str, ActionExecutionStatus]:
        pending = dict.fromkeys(identifiers)
        if not pending:
            return {}
        deadlines = _wait_deadlines(pending, self._timeouts, timeout)
        results: dict[str, ActionExecutionStatus] = {}
        latest: dict[str, str] = {}
        interval = 2.0
        while pending:
            payload = self._client._request(_operation(Route.ACTION_EXECUTION_BATCH), params={"ids": ",".join(pending)})
            batch = _parse_model(payload, ActionExecutionBatchStatus).executions
            for identifier in tuple(pending):
                # A batch item does not say which store answered it; the single
                # status route does, so it supplies every returned status.
                item = batch.get(identifier)
                if item is not None and item.status not in _TERMINAL_STATUSES:
                    latest[identifier] = item.status
                    continue
                result = self.get(identifier)
                latest[identifier] = _execution_status(result)
                if _terminal_result(result):
                    results[identifier] = result
                    del pending[identifier]
                    self._timeouts.pop(identifier, None)
            if not pending:
                break
            delay = _next_wait_delay(pending, deadlines, interval)
            if delay == 0:
                raise _wait_many_expired(pending, deadlines, results, latest)
            time.sleep(delay)
            interval = min(interval * 1.3, 5.0)
        return results


class DeviceResource:
    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, spot_id: str, *, page: int | None = None, limit: int | None = None) -> Page[Device]:
        params = {"spotId": spot_id, **_page_params(page, limit)}
        return self._client._page_request(_operation(Route.DEVICES), params=params, total_limit=limit)

    def get(self, identifier: str) -> Device:
        return self._client._model_request(_operation(Route.DEVICE, id=identifier))

    def status(self, identifier: str) -> DeviceStatus:
        return self._client._model_request(_operation(Route.DEVICE_STATUS, id=identifier))

    def status_by_spot(self, device_ids: Iterable[str], *, max_devices: int = 100) -> StatusBatchResult:
        identifiers = tuple(device_ids)
        if max_devices > 100:
            raise ValueError("status fan-out has a maximum of 100 devices")
        if len(identifiers) > 100:
            raise ValueError("status fan-out has a maximum of 100 devices")
        if len(identifiers) > max_devices:
            raise ValueError(f"status fan-out accepts at most {max_devices} devices")
        results: dict[str, DeviceStatus] = {}
        failed: list[str] = []
        for identifier in identifiers:
            try:
                results[identifier] = self.status(identifier)
            except PWSError:
                failed.append(identifier)
        return StatusBatchResult(results=results, failed=tuple(failed))


class TelemetryResource:
    """Read-only time-series telemetry resolved from an operator device id."""

    def __init__(self, client: PWS) -> None:
        self._client = client

    def topics(self, device: str) -> TelemetryTopics:
        agent_id = self._agent_id(device)
        return self._client._model_request(_operation(Route.TELEMETRY_TOPICS, id=agent_id))

    def query(
        self,
        device: str,
        topic: str,
        since: str | datetime | timedelta,
        *,
        step: str | None = None,
        until: str | datetime | timedelta | None = None,
    ) -> Telemetry:
        agent_id = self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=(topic,), step=step, single=True)
        return _parse_model(self._client._request(_operation(Route.TELEMETRY, id=agent_id), params=params), Telemetry)

    def batch(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        *,
        step: str | None = None,
        until: str | datetime | timedelta | None = None,
    ) -> TelemetryBatch:
        agent_id = self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=topics, step=step)
        return _parse_model(
            self._client._request(_operation(Route.TELEMETRY_BATCH, id=agent_id), params=params),
            TelemetryBatch,
        )

    def rollup(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        *,
        step: str,
        until: str | datetime | timedelta | None = None,
    ) -> TelemetryBatchRollup:
        agent_id = self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=topics, step=step)
        return _parse_model(
            self._client._request(_operation(Route.TELEMETRY_BATCH_ROLLUP, id=agent_id), params=params),
            TelemetryBatchRollup,
        )

    def batch_export(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        *,
        until: str | datetime | timedelta | None = None,
    ) -> TelemetryBatchExport:
        agent_id = self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=topics)
        return _parse_model(
            self._client._request(_operation(Route.TELEMETRY_BATCH_EXPORT, id=agent_id), params=params),
            TelemetryBatchExport,
        )

    def export(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        dest: str | Path = "telemetry.csv",
        *,
        until: str | datetime | timedelta | None = None,
        aggregation: str = "rollup",
        include_boundary: bool = True,
        sample_interval: str = "15s",
        timestamp_time_zone: str = "UTC",
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        agent_id = self._agent_id(device)
        start_time, end_time = _telemetry_range(since, until=until)
        body = {
            "topicIds": list(topics),
            "startTime": start_time,
            "endTime": end_time,
            "format": "csv",
            "aggregation": aggregation,
            "includeBoundary": include_boundary,
            "sampleInterval": sample_interval,
            "timestampTimeZone": timestamp_time_zone,
        }
        target = Path(dest)
        return self._client._file_request(
            _operation(Route.TELEMETRY_EXPORT, id=agent_id),
            target=target,
            json_body=body,
            headers={"Accept": "text/csv, application/zip"},
            expected_content_type="text/csv",
            on_progress=on_progress,
        )

    def _agent_id(self, device: str) -> str:
        detail = self._client.devices.get(device)
        return _device_agent_id(detail, device)


class ComponentResource:
    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, device_id: str, *, page: int | None = None, limit: int | None = None) -> Page[Component]:
        params = {"deviceId": device_id, **_page_params(page, limit)}
        return self._client._page_request(_operation(Route.COMPONENTS), params=params, total_limit=limit)


class AccessKeyResource:
    """An agent's device API keys: the six approved routes, no update or hard delete.

    The secret comes back only as :class:`pydantic.SecretStr`; ``key`` metadata never carries it.
    """

    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, agent_id: str) -> list[AccessKey]:
        return _access_keys(self._client._request(_operation(Route.ACCESS_KEYS, id=agent_id)))

    def issue(
        self, agent_id: str, name: str, *, description: str | None = None, expires_at: datetime | str | None = None
    ) -> IssuedAccessKey:
        body = _access_key_body(name, description, expires_at)
        return _issued_access_key(self._client._send(_operation(Route.ACCESS_KEY_ISSUE, id=agent_id), body))

    def rotate(self, agent_id: str, key_id: str, *, expires_at: datetime | str | None = None) -> IssuedAccessKey:
        operation = _operation(Route.ACCESS_KEY_ROTATE, id=agent_id, keyId=key_id)
        return _issued_access_key(self._client._send(operation, _access_key_body(None, None, expires_at)))

    def reissue(self, agent_id: str, key_id: str, *, expires_at: datetime | str | None = None) -> IssuedAccessKey:
        operation = _operation(Route.ACCESS_KEY_REISSUE, id=agent_id, keyId=key_id)
        return _issued_access_key(self._client._send(operation, _access_key_body(None, None, expires_at)))

    def revoke(self, agent_id: str, key_id: str) -> None:
        self._client._request(_operation(Route.ACCESS_KEY_REVOKE, id=agent_id, keyId=key_id))

    def plain_key(self, agent_id: str, key_id: str) -> SecretStr | None:
        """The stored key, or ``None`` when the Hub keeps no recoverable copy (rotate or reissue instead)."""

        return _revealed_secret(self._client._request(_operation(Route.ACCESS_KEY_PLAIN, id=agent_id, keyId=key_id)))


class SpotRuleResource:
    def __init__(self, client: PWS, spot_id: str) -> None:
        self._client = client
        self._spot_id = spot_id

    def list(self, *, page: int | None = None, limit: int | None = None) -> Page[Rule]:
        return self._client._page_request(
            _operation(Route.SPOT_RULES, spotId=self._spot_id),
            params=_skip_take_page_params(page, limit),
            total_limit=limit,
        )

    def get(self, identifier: str) -> Rule:
        return self._client._model_request(_operation(Route.SPOT_RULE, spotId=self._spot_id, id=identifier))

    def executions(self, identifier: str) -> Sequence[RuleExecution]:
        """Return the 10 most recent executions; Hub applies its default limit."""

        operation = _operation(Route.SPOT_RULE_EXECUTIONS, spotId=self._spot_id, id=identifier)
        payload = self._client._request(operation)
        if not isinstance(payload, list):
            raise TypeError(f"expected an array response from {operation.path}")
        return [_parse_model(item, RuleExecution) for item in payload]


class RuleResource:
    """Read-only rule root that requires an explicit spot scope."""

    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(self, spot_id: str, *, page: int | None = None, limit: int | None = None) -> Page[Rule]:
        return SpotRuleResource(self._client, spot_id).list(page=page, limit=limit)

    def get(self, spot_id: str, identifier: str) -> Rule:
        return SpotRuleResource(self._client, spot_id).get(identifier)

    def executions(self, spot_id: str, identifier: str) -> Sequence[RuleExecution]:
        """Return the 10 most recent executions for a rule in this spot."""

        return SpotRuleResource(self._client, spot_id).executions(identifier)


class CaptureResource:
    """Read-only capture sessions (``GET /media/capture-sessions``)."""

    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(
        self,
        *,
        spot: str | None = None,
        device: str | None = None,
        status: str | None = None,
        since: str | datetime | timedelta | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> Page[CaptureSession]:
        params = _capture_params(spot=spot, device=device, status=status, since=since, page=page, limit=limit)
        return self._client._page_request(_operation(Route.CAPTURES), params=params, total_limit=limit)

    def get(self, identifier: str) -> CaptureSessionHandle:
        detail = self._client._model_request(_operation(Route.CAPTURE, id=identifier))
        return CaptureSessionHandle(self._client, detail)

    def latest(self, *, spot: str | None = None, status: str | None = None) -> CaptureSessionHandle | None:
        """The most recently created session (optionally per spot), or ``None``."""

        params = _capture_params(spot=spot, status=status, limit=1, latest=True)
        page = self._client._page_request(_operation(Route.CAPTURES), params=params, total_limit=1)
        if not page.items:
            return None
        return self.get(page.items[0].id)


class CaptureSessionHandle:
    """A resolved capture session whose media can be downloaded in one call (A.5 (3))."""

    def __init__(self, client: PWS, detail: CaptureSessionDetail) -> None:
        self._client = client
        self._detail = detail

    @property
    def id(self) -> str:
        return self._detail.id

    @property
    def name(self) -> str:
        return self._detail.name

    @property
    def status(self) -> str:
        return self._detail.status

    @property
    def model(self) -> CaptureSessionDetail:
        return self._detail

    @property
    def media(self) -> list[CaptureSessionDetailMedia]:
        return list(self._detail.media)

    def download(self, dest: str | Path = ".", *, on_progress: ProgressCallback | None = None) -> list[Path]:
        """Download every media asset of the session into the directory ``dest`` and return the paths.

        ``dest`` is always a directory: it is created when missing (a dotted name such as ``run.1`` included)
        and :class:`ValidationError` is raised when it exists as a file.
        """

        directory = _prepare_download_directory(dest)
        return [
            self._client.media.download(item.id, directory, on_progress=on_progress, _format=item.format)
            for item in self._detail.media
        ]


_UPLOAD_CANCELLED = object()
_UPLOAD_FINISHED = object()


class _ArrayWorkerChannel:
    """The two-way handoff between an async array upload and the worker thread that owns its temporary store.

    The worker reports each finished stage through a ``concurrent.futures.Future`` the event loop can await and
    reads what the loop did next from ``inbox``; neither side calls into the other's scheduler. ``finished`` is
    settled last, after the store is removed.
    """

    def __init__(self) -> None:
        self.prepared: concurrent.futures.Future[_PreparedArray] = concurrent.futures.Future()
        self.members: concurrent.futures.Future[None] = concurrent.futures.Future()
        self.finished: concurrent.futures.Future[None] = concurrent.futures.Future()
        self.inbox: queue.Queue[object] = queue.Queue()
        self.cancel = threading.Event()

    def abandon(self) -> None:
        """Tell the worker to stop: it admits no further PUT, removes the store and exits. Never blocks."""

        self.cancel.set()
        self.inbox.put(_UPLOAD_CANCELLED)


def _array_worker(
    channel: _ArrayWorkerChannel,
    modality: str,
    data: object,
    session: str,
    extras: Mapping[str, object],
    descriptor: Mapping[str, object],
    declarations: Mapping[str, object] | None,
) -> None:
    """Prepare, upload and clean up one array store; the store's whole life is inside this thread.

    A thread cannot be interrupted, so removing the directory from the event loop (a ``TemporaryDirectory`` exit
    on cancellation or at ``asyncio.run`` shutdown) would race the writer and let it recreate the files. Here the
    thread that writes the store also creates and removes it, in its own ``finally``, and removes only a directory
    it did create. The outcome of each stage, including a failure to allocate the directory, reaches the caller
    through ``channel``; this function never raises.
    """

    directory: Path | None = None
    try:
        directory = Path(tempfile.mkdtemp(prefix=f"pws-{modality.lower()}-"))
        if channel.cancel.is_set():
            raise TransportError(f"{modality} upload cancelled")
        prepared = _prepare_array(modality, data, directory, session, extras, descriptor, declarations)
        channel.prepared.set_result(prepared)
        reservation = channel.inbox.get()
        if reservation is _UPLOAD_CANCELLED:
            raise TransportError(f"{modality} upload cancelled")
        _upload_array_members(prepared, cast(Mapping[str, object], reservation), channel.cancel)
        channel.members.set_result(None)
        channel.inbox.get()  # the preview lives in the directory until its PUT has finished (or the call was cancelled)
    except BaseException as error:  # noqa: BLE001 - delivered to whichever stage the caller still awaits
        for stage in (channel.prepared, channel.members):
            if not stage.done():
                stage.set_exception(error)
    finally:
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
        channel.finished.set_result(None)


def _start_array_worker(channel: _ArrayWorkerChannel, modality: str, *arguments: object) -> threading.Thread:
    """Run :func:`_array_worker` on a thread of its own, never on the event loop's default executor.

    The worker blocks on ``channel.inbox`` while the loop sends the preview, and that send needs the default
    executor (``asyncio.to_thread`` reads the file; asynchronous name resolution runs there too). A worker parked
    in a bounded default executor would occupy the slot the loop is waiting for, so one upload on a one-worker
    pool, or N uploads on an N-worker pool, would never finish.

    The thread is not a daemon: a daemon thread is killed at interpreter exit, possibly halfway through removing the
    store, whereas this one finishes its cleanup first. The price is that interpreter exit waits for a worker that
    is still running, which a cancelled call has already told to stop.
    """

    thread = threading.Thread(
        target=_array_worker, args=(channel, modality, *arguments), name=f"pws-{modality.lower()}-upload", daemon=False
    )
    thread.start()
    return thread


def _join_when_the_loop_shuts_down(thread: threading.Thread) -> None:
    """Let ``asyncio.run`` wait for a worker the caller no longer awaits, as it does for default-executor threads.

    The caller of a cancelled upload returns at once and the thread finishes by itself. The loop runner's shutdown
    joins its default executor, so a job there that only joins the worker makes ``asyncio.run`` return after the
    store is gone. The job lasts as long as the cancelled worker, which has no fixed wall-clock bound (it ends when
    the PUT in flight completes, fails or stalls for the inactivity timeout, plus local cleanup), and it holds one
    default-executor slot meanwhile. It never waits for the loop (the worker has been told to stop and no longer
    needs it), so it cannot recreate the dependency cycle the dedicated thread avoids. Without a running loop, or
    once the executor refuses work, the thread simply finishes on its own.
    """

    with contextlib.suppress(RuntimeError):
        asyncio.get_running_loop().run_in_executor(None, thread.join)


def _upload_array_members(
    prepared: _PreparedArray, reservation: Mapping[str, object], cancel: threading.Event | None = None
) -> None:
    # A synchronous caller has no cancellation; it passes none, so its call shape is the one it always had.
    if prepared.modality == "DEPTH":
        if cancel is None:
            _depth.upload_members(prepared.root, reservation)
        else:
            _depth.upload_members(prepared.root, reservation, cancel=cancel)
    elif cancel is None:
        _zarr_storage.upload_store(prepared.root, reservation, prepared.modality)
    else:
        _zarr_storage.upload_store(prepared.root, reservation, prepared.modality, cancel=cancel)


def _depth_metadata(asset: MediaAsset) -> dict[str, object]:
    if asset.modality != "DEPTH" or not _is_zarr_format(asset.format):
        raise ValidationError("Media asset is not a DEPTH Zarr")
    metadata = asset.metadata
    if not isinstance(metadata, Mapping) or metadata.get("representation") != "scalarField":
        raise ValidationError("DEPTH scalar representation is missing")
    fields = metadata.get("scalarFields")
    descriptor = fields.get("depth") if isinstance(fields, Mapping) else None
    if not isinstance(descriptor, Mapping) or not {"version", "unit", "scale", "offset", "noData", "colormap"} <= set(
        descriptor
    ):
        raise ValidationError("DEPTH stored descriptor is incomplete")
    return dict(descriptor)


def _multiband_metadata(asset: MediaAsset, *, band_id: str | None = None) -> dict[str, object]:
    if not _is_zarr_format(asset.format):
        raise ValidationError("Media asset is not a bands.v1 Zarr")
    metadata = asset.metadata
    if not isinstance(metadata, Mapping):
        raise ValidationError("bands.v1 media descriptor is missing")
    return _multiband.validate_media_descriptor(metadata.get("mediaDescriptor"), band_id=band_id)


class MediaResource:
    """Media assets with presigned upload and download hidden behind file operations."""

    def __init__(self, client: PWS) -> None:
        self._client = client

    def list(
        self,
        *,
        capture: str | None = None,
        spot: str | None = None,
        device: str | None = None,
        modality: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> Page[MediaAsset]:
        params = _media_params(session=capture, spot=spot, device=device, modality=modality, page=page, limit=limit)
        return self._client._page_request(_operation(Route.MEDIA), params=params, total_limit=limit)

    def get(self, identifier: str) -> MediaAsset:
        return self._client._model_request(_operation(Route.MEDIA_ASSET, id=identifier))

    def band_provenance(self, identifier: str) -> BandProvenance:
        """Read Hub-verified MULTISPECTRAL records through the media lookup route."""

        return self._client._model_request(_operation(Route.MEDIA_BAND_PROVENANCE, id=identifier))

    def upload(
        self,
        file: str | Path,
        *,
        thumbnail: str | Path,
        capture: str,
        width: int,
        height: int,
        modality: str = "RGB",
        spot: str | None = None,
        device: str | None = None,
    ) -> CompleteImageUploadResponse:
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
                session=capture,
                width=width,
                height=height,
                modality=modality,
                spot=spot,
                device=device,
            )
            issued = _parse_model(
                self._client._raw_request(Route.MEDIA_UPLOAD.method, Route.MEDIA_UPLOAD.path, json_body=body),
                UploadImageResponse,
            )
            self._client._transport.upload_opened(
                issued.upload_url, image_source, size=image_size, content_type=image_type
            )
            self._client._transport.upload_opened(
                issued.thumbnail_upload_url, preview_source, size=preview_size, content_type=preview_type
            )
        return _parse_model(
            self._client._raw_request(
                Route.MEDIA_COMPLETE_UPLOAD.method,
                Route.MEDIA_COMPLETE_UPLOAD.path,
                json_body={"mediaAssetId": issued.media_asset_id, "width": width, "height": height},
            ),
            CompleteImageUploadResponse,
        )

    def upload_registered_multispectral(
        self,
        source_asset_id: str,
        aligned_bands: object,
        *,
        capture: str,
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
        """Upload physical band-align output as a new, Hub-registered MULTISPECTRAL asset.

        ``aligned_bands`` may be the ordered physical ``BandInput`` list or the image-lib result object with
        ``bands`` and ``recordFragment``. Result objects need ``band_metadata`` copied from the source descriptor;
        flat image-lib band arrays are reshaped from their ``width`` and ``height``. The Hub reservation still needs
        ``capture`` and the source ``derivedFrom`` id. Source interpretation and normalization declarations are
        inherited by default; either can be overridden explicitly. Pass ``calibration`` for radiance or reflectance.
        Registration and declaration checks run before reserve.
        """

        bands, registration = _registered_multispectral_declaration(
            source_asset_id,
            aligned_bands,
            record_fragment=record_fragment,
            path=path,
            profile=profile,
            band_metadata=band_metadata,
        )
        source_provenance: object = _MISSING
        if normalization is None or interpretation is None:
            try:
                source_provenance = self.band_provenance(source_asset_id)
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
            capture=capture,
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
        capture: str,
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
        """Upload a 2D array as a Zarr v3 asset of ``modality`` with one scoped grant.

        DEPTH takes the raw array and an explicit descriptor (the remaining
        keyword arguments). THERMAL takes float degC only, stored as native
        uint16 centi-kelvin with Hub's policy descriptor; integer input is
        refused. MULTISPECTRAL takes an ordered list of :class:`BandInput` (the
        list order is the band order) with ``radiometric_level`` and, above
        ``raw``, ``calibration``; Hub refuses it unless its release switch is on. ``labels`` and ``derived_from`` (completed same-session source
        asset UUIDs) ride on the reservation. Every client check runs before the
        first request; Hub decides switches, session state and provenance.
        ``capture_parameters`` (string keys to ``str``, ``bool``, ``int`` or finite ``float``) rides on the
        reservation as ``captureParameters``.
        MULTISPECTRAL ``registration``, ``normalization`` and ``interpretation`` declarations use Hub wire keys and
        pass through unchanged with completion; Hub verifies and stamps the server-owned records.
        """

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
        extras = _array_reservation_extras(modality, capture, labels, derived_from, descriptor, capture_parameters)
        declarations = _array_provenance_declarations(modality, registration, normalization, interpretation)
        with tempfile.TemporaryDirectory(prefix=f"pws-{modality.lower()}-") as temporary:
            prepared = _prepare_array(modality, data, Path(temporary), capture, extras, descriptor, declarations)
            reservation = _array_reservation(
                self._client._raw_request(
                    Route.MEDIA_ZARR_UPLOAD.method, Route.MEDIA_ZARR_UPLOAD.path, json_body=prepared.reservation
                ),
                modality,
            )
            reserved_id = cast(str, reservation["mediaAssetId"])
            try:
                _upload_array_members(prepared, reservation)
                self._client._transport.upload(
                    cast(str, reservation["thumbnailUploadUrl"]), prepared.preview, content_type="image/jpeg"
                )
                completed = self._client._raw_request(
                    Route.MEDIA_ZARR_COMPLETE.method,
                    Route.MEDIA_ZARR_COMPLETE.path,
                    json_body={"mediaAssetId": reserved_id, **prepared.completion},
                )
                return _array_result(completed, reserved_id, modality)
            except PWSError:
                raise
            except Exception:
                raise TransportError(f"{modality} upload failed after reservation") from None

    def upload_depth(
        self,
        array: object,
        *,
        unit: str | None = None,
        scale: float | None = None,
        offset: float | None = None,
        no_data: float | None = None,
        display_range: tuple[float, float] | None = None,
        colormap: str | None = None,
        intrinsics: Mapping[str, float] | None = None,
        source_sensor: str | None = None,
        capture: str,
    ) -> ArrayUploadResult:
        """``upload_array("DEPTH", array, ...)``: write a verified Zarr v3 store, then upload with one scoped grant."""

        return self.upload_array(
            "DEPTH",
            array,
            capture=capture,
            unit=unit,
            scale=scale,
            offset=offset,
            no_data=no_data,
            display_range=display_range,
            colormap=colormap,
            intrinsics=intrinsics,
            source_sensor=source_sensor,
        )

    def download_depth(self, identifier: str) -> tuple[np.ndarray, dict[str, object]]:
        """Return a copied raw NumPy array and the Hub-frozen logical depth descriptor."""

        _depth._require_depth_extra()
        asset = self.get(identifier)
        metadata = _depth_metadata(asset)
        with tempfile.TemporaryDirectory(prefix="pws-depth-") as temporary:
            root = self.download(
                identifier,
                Path(temporary),
                _format=asset.format,
                _array_paths=(_depth._array_path(depth_policy()),),
                _admit=_depth.admit_download,
            )
            return _depth.read_depth(root), metadata

    def download_multiband(self, identifier: str, *, band_id: str | None = None) -> MultibandData:
        """Read a Zarr `bands.v1` asset using its Hub-frozen order and descriptors."""

        _depth._require_depth_extra("bands.v1")
        asset = self.get(identifier)
        descriptor = _multiband_metadata(asset, band_id=band_id)
        with tempfile.TemporaryDirectory(prefix="pws-multiband-") as temporary:
            root = self.download(
                identifier,
                Path(temporary),
                _format=asset.format,
                _array_paths=tuple(
                    f"bands/{band['id']}" for band in cast(list[dict[str, object]], descriptor["bands"])
                ),
                _admit=lambda staged, members: _multiband.admit_download(staged, descriptor, members),
            )
            return _multiband.read_multiband_store(root, descriptor, band_id=band_id)

    def latest(self, spot: str) -> MediaAsset | None:
        payload = self._client._request(_operation(Route.MEDIA_LATEST, spotId=spot))
        return None if payload is None else _parse_model(payload, MediaAsset)

    def presigned_url(self, identifier: str, *, expires_in: int | None = None) -> MediaAssetPresignedUrl:
        params = {"expiresIn": expires_in} if expires_in is not None else None
        payload = self._client._request(_operation(Route.MEDIA_PRESIGNED_URL, id=identifier), params=params)
        return _parse_model(payload, MediaAssetPresignedUrl)

    def download(
        self,
        identifier: str,
        dest: str | Path = ".",
        *,
        on_progress: ProgressCallback | None = None,
        _format: str | None = None,
        _array_paths: tuple[str, ...] | None = None,
        _admit: _zarr_storage.DownloadAdmission | None = None,
    ) -> Path:
        """Resolve a presigned URL and stream the object to disk; returns the written path.

        ``dest`` is a directory or a file path.  An existing directory, a string ending in a path separator, or a
        path that does not exist yet and has no file suffix (``output``) means a directory; any other path
        (``capture.png``, an existing file) is a file.  Zarr assets are materialised as ``<dest>/<id>.zarr/`` from
        the Hub's per-file presigned map.
        """

        trailing_separator = _separator_intent(dest)
        asset_format = _format if _format is not None else self.get(identifier).format
        if _is_zarr_format(asset_format):
            return self._download_zarr(
                identifier,
                Path(dest),
                array_paths=_array_paths,
                admit=_admit,
                trailing_separator=trailing_separator,
            )
        presigned = self.presigned_url(identifier)
        target = _resolve_target(
            Path(dest), identifier, asset_format, presigned.url, trailing_separator=trailing_separator
        )
        self._client._transport.download(
            presigned.url,
            target,
            on_progress=on_progress,
            expected_content_type=_media_content_type(asset_format),
        )
        return target

    def _download_zarr(
        self,
        identifier: str,
        dest: Path,
        *,
        array_paths: tuple[str, ...] | None = None,
        admit: _zarr_storage.DownloadAdmission | None = None,
        trailing_separator: bool = False,
    ) -> Path:
        directory = _is_directory(dest, trailing_separator=trailing_separator)
        root = dest / f"{_safe_identifier(identifier)}.zarr" if directory else dest
        _zarr_storage.validate_download_root(root)
        listing_started = time.monotonic()
        payload = self._client._request(_operation(Route.MEDIA_ZARR_FILES, id=identifier))
        listing = _parse_model(payload, ZarrFiles)
        deadline = listing_started + listing.expires_in
        with _zarr_storage.staged_download_store(
            root,
            listing.files,
            listing.member_sizes,
            listing.total_files,
            listing.total_bytes,
            listing.download_ready,
            listing.completed_bytes,
            array_paths=array_paths,
        ) as (staged, members):
            for member in _zarr_storage.admitted_download_members(staged, members, admit):
                target = staged / member.relative
                written = self._client._transport.download(
                    member.url,
                    target,
                    expected_content_type="application/octet-stream",
                    max_bytes=member.expected_bytes,
                    deadline=deadline,
                )
                if written != member.expected_bytes:
                    raise ValidationError(f"Zarr member {member.relative!r} changed during download")
        return root


class PWS:
    """Operator SDK entry point with discovery-backed authentication."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        org: str | None = None,
        profile: str = "default",
        credential: Credential | None = None,
        transport: Transport | None = None,
        timeout: float | None = None,
        _config: Config | None = None,
        _owns_transport: bool | None = None,
    ) -> None:
        if _config is not None:
            config = _config
        elif credential is None:
            config = Config.resolve(
                api_key=api_key,
                base_url=transport.base_url if transport is not None else base_url,
                org=org,
                profile=profile,
                timeout=timeout,
            )
        else:
            config = Config(
                api_key=api_key or "",
                base_url=base_url or (transport.base_url if transport is not None else DEFAULT_BASE_URL),
                org=org,
                timeout=timeout or 30.0,
                profile=profile,
            )
        self.config = config
        self._transport = transport or Transport(config.base_url, timeout=config.timeout)
        self._owns_transport = transport is None if _owns_transport is None else _owns_transport
        self._credential: Credential | None = credential or _credential_from_config(config)
        self._authenticated = False

        self.organizations = OrganizationResource(self)
        self.spots = SpotResource(self)
        self.devices = DeviceResource(self)
        self.components = ComponentResource(self)
        self.rules = RuleResource(self)
        self.telemetry = TelemetryResource(self)
        self.captures = CaptureResource(self)
        self.media = MediaResource(self)
        self.actions = ActionResource(self)
        self.agents = AgentResource(self)
        self.access_keys = AccessKeyResource(self)
        self.raw = RawResource(self)

    @classmethod
    def resource_names(cls) -> tuple[str, ...]:
        return RESOURCE_NAMES

    def me(self) -> Identity:
        """Who the session belongs to and which organizations it can use, without any identity route."""

        credential = _session_credential(self._credential)
        self._ensure_auth()
        user_id = _session_user_id(credential)
        organizations = list(self.organizations.for_user(user_id))
        return Identity(user_id, credential.user_email, credential.expires_at, organizations)

    def my_organizations(self) -> Page[Organization]:
        """The organizations this session's user belongs to. Any member can read this; ``organizations.list`` is the
        admin listing of every organization."""

        credential = _session_credential(self._credential)
        self._ensure_auth()
        return self.organizations.for_user(_session_user_id(credential))

    def access_info(self) -> AccessInfo:
        """Read this session's access summary for the selected organization."""

        organization_id = self.config.org
        if organization_id is None:
            raise OrganizationScopeError(
                "no organization scope is set; check the scope: --org/org=, else PWS_ORG, else the profile's org"
            )
        payload = self._request(_operation(Route.ACCESS_INFO), params={"organizationId": organization_id})
        return _parse_model(payload, AccessInfo)

    def with_org(self, org: str) -> PWS:
        return PWS(
            base_url=self.config.base_url,
            org=org,
            credential=self._credential,
            transport=self._transport,
            timeout=self.config.timeout,
            _owns_transport=False,
        )

    def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
    ) -> object:
        self._ensure_auth()
        for attempt in range(2):
            try:
                return self._transport.request(
                    method,
                    path,
                    headers=self._headers(),
                    params=params,
                    json_body=json_body,
                )
            except PWSError as exc:
                if exc.status_code == 401:
                    _invalidate(self._credential)
                if attempt == 0 and _can_reauthenticate(self._credential, exc, method):
                    self._reauthenticate()
                    continue
                raise _scope_error(exc, self.config.org) from exc
        raise AssertionError("unreachable")

    def _request[ModelT: BaseModel](
        self,
        operation: BoundOperation[ModelT],
        *,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
    ) -> object:
        try:
            return self._raw_request(operation.spec.method, operation.path, params=params)
        except PWSError as exc:
            error = _public_error(operation, exc)
        raise error  # outside the handler, so a key route's raw failure is not chained

    def _send[ModelT: BaseModel](self, operation: BoundOperation[ModelT], body: Mapping[str, object]) -> object:
        try:
            return self._raw_request(operation.spec.method, operation.path, json_body=body)
        except PWSError as exc:
            error = _public_error(operation, exc)
        raise error

    def _model_request[ModelT: BaseModel](self, operation: BoundOperation[ModelT]) -> ModelT:
        payload = self._request(operation)
        model = operation.spec.model
        if model is None:
            raise TypeError(f"expected a modelled operation, got {operation.spec.method} {operation.path}")
        return _parse_model(payload, model)

    def _file_request(
        self,
        operation: BoundOperation[BaseModel],
        *,
        target: Path,
        json_body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
        expected_content_type: str | None = None,
    ) -> Path:
        self._ensure_auth()
        for attempt in range(2):
            try:
                self._transport.download_request(
                    operation.spec.method,
                    operation.path,
                    target,
                    headers={**self._headers(), **(headers or {})},
                    json_body=json_body,
                    on_progress=on_progress,
                    expected_content_type=expected_content_type,
                )
            except PWSError as exc:
                if exc.status_code == 401:
                    _invalidate(self._credential)
                if attempt == 0 and _can_reauthenticate(self._credential, exc, operation.spec.method):
                    self._reauthenticate()
                    continue
                raise _scope_error(exc, self.config.org) from exc
            return target
        raise AssertionError("unreachable")

    def _page_request[ModelT: BaseModel](
        self,
        operation: BoundOperation[ModelT],
        *,
        params: Mapping[str, object] | None = None,
        total_limit: int | None = None,
        _walk: frozenset[frozenset[tuple[str, str]]] = frozenset(),
    ) -> Page[ModelT]:
        if not operation.spec.pagination:
            raise TypeError(f"expected a paginated operation, got {operation.spec.method} {operation.path}")
        walk = _record_request(params, _walk)
        payload = self._request(operation, params=params)
        if not isinstance(payload, Page):
            raise TypeError(f"expected a paginated response from {operation.path}")
        model = operation.spec.model
        if model is None:
            raise TypeError(f"expected a modelled operation, got {operation.spec.method} {operation.path}")
        result = Page(
            items=[_parse_model(item, model) for item in payload.items],
            pagination=payload.pagination,
            meta=payload.meta,
            _total_limit=total_limit,
        )
        _require_requested_page(params, result)
        next_params = _next_page_params(params, result)
        if next_params is not None:
            result._next = lambda: self._page_request(
                operation, params=next_params, total_limit=total_limit, _walk=walk
            )
        return result

    def _ensure_auth(self) -> None:
        if self._credential is None:
            if self._authenticated:
                return
            raise RuntimeError("no credential is configured")
        self._credential.refresh(self._transport)
        self._authenticated = True

    def _reauthenticate(self) -> None:
        """After a 401 (the rejected JWT is already dropped), mint a new one from the stored session."""

        self._ensure_auth()

    def _headers(self) -> Mapping[str, str]:
        headers = dict(self._credential.headers()) if self._credential is not None else {}
        if self.config.org:
            headers["X-Organization-Id"] = self.config.org
        return headers

    def close(self) -> None:
        if self._owns_transport:
            self._transport.close()

    def __enter__(self) -> PWS:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


class AsyncRawResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json: object | None = None,
    ) -> object:
        _refuse_access_key_path(path)
        return await self._client._raw_request(method, path, params=params, json_body=json)


class AsyncOrganizationResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(self, *, page: int | None = None, limit: int | None = None) -> Page[Organization]:
        params = _page_params(page, limit)
        return await self._client._page_request(_operation(Route.ORGANIZATIONS), params=params, total_limit=limit)

    async def for_user(self, user_id: str) -> Page[Organization]:
        """Every organization ``user_id`` belongs to; the Hub allows only the user themselves or an admin."""

        return await self._client._page_request(_operation(Route.USER_ORGANIZATIONS, userId=user_id))

    async def get(self, identifier: str) -> Organization:
        if _looks_like_uuid(identifier):
            return await self._client._model_request(_operation(Route.ORGANIZATION, id=identifier))
        return await self._client._model_request(_operation(Route.ORGANIZATION_BY_SLUG, slug=identifier))


class AsyncSpotRuleResource:
    def __init__(self, client: AsyncPWS, spot_id: str) -> None:
        self._client = client
        self._spot_id = spot_id

    async def list(self, *, page: int | None = None, limit: int | None = None) -> Page[Rule]:
        return await self._client._page_request(
            _operation(Route.SPOT_RULES, spotId=self._spot_id),
            params=_skip_take_page_params(page, limit),
            total_limit=limit,
        )

    async def get(self, identifier: str) -> Rule:
        return await self._client._model_request(_operation(Route.SPOT_RULE, spotId=self._spot_id, id=identifier))

    async def executions(self, identifier: str) -> Sequence[RuleExecution]:
        """Return the 10 most recent executions; Hub applies its default limit."""

        operation = _operation(Route.SPOT_RULE_EXECUTIONS, spotId=self._spot_id, id=identifier)
        payload = await self._client._request(operation)
        if not isinstance(payload, list):
            raise TypeError(f"expected an array response from {operation.path}")
        return [_parse_model(item, RuleExecution) for item in payload]


class AsyncSpotHandle:
    def __init__(self, client: AsyncPWS, spot: Spot) -> None:
        self._client = client
        self._spot = spot
        self.rules = AsyncSpotRuleResource(client, spot.id)
        self.actions = AsyncSpotActionResource(self)

    @property
    def id(self) -> str:
        return self._spot.id

    @property
    def name(self) -> str:
        return self._spot.name

    @property
    def slug(self) -> str | None:
        return self._spot.slug

    @property
    def model(self) -> Spot:
        return self._spot

    async def structure(self) -> SpotStructure:
        return await self._client._model_request(_operation(Route.SPOT_STRUCTURE, id=self.id))

    async def captures(self, **filters: str | int | None) -> Page[CaptureSession]:
        return await self._client.captures.list(spot=self.id, **filters)  # type: ignore[arg-type]


class AsyncSpotActionResource:
    """Async counterpart of :class:`SpotActionResource`."""

    def __init__(self, spot: AsyncSpotHandle) -> None:
        self._spot = spot

    async def resolve(
        self,
        name: str,
        params: Mapping[str, object] | None = None,
        *,
        device: str | None = None,
        component: str | None = None,
    ) -> ResolvedAction:
        return resolve_action(await self._spot.structure(), name, params, device=device, component=component)

    async def preview(
        self,
        name: str,
        params: Mapping[str, object] | None = None,
        *,
        device: str | None = None,
        component: str | None = None,
        capture_session_id: str | None = None,
        capture_session_options: Mapping[str, object] | None = None,
    ) -> ManualActionDryRun:
        resolved = await self.resolve(name, params, device=device, component=component)
        body: dict[str, object] = {
            "actionDefId": resolved.action_def_id,
            "deviceId": resolved.device_id,
            "params": resolved.params,
        }
        if capture_session_id is not None:
            body["captureSessionId"] = capture_session_id
        if capture_session_options is not None:
            body["captureSessionOptions"] = dict(capture_session_options)
        try:
            payload = await self._spot._client._raw_request(
                Route.MANUAL_ACTION_PREVIEW.method,
                Route.MANUAL_ACTION_PREVIEW.path,
                json_body=body,
            )
        except PWSError as exc:
            if isinstance(exc, NotFoundError) or exc.status_code == 405:
                raise ActionPreviewUnavailable(
                    "This Hub does not support action preview",
                    status_code=exc.status_code,
                    request_id=exc.request_id,
                ) from exc
            raise
        return _parse_model(payload, ManualActionDryRun)

    async def run(
        self,
        name: str,
        params: Mapping[str, object] | None = None,
        *,
        device: str | None = None,
        component: str | None = None,
        wait: bool = False,
        execution_id: str | None = None,
    ) -> Execution:
        resolved = await self.resolve(name, params, device=device, component=component)
        execution_id = _uuid7() if execution_id is None else execution_id
        body = _manual_execution_body(execution_id, resolved)
        retries = 0
        refreshed = False
        while True:
            try:
                payload = await self._spot._client._raw_request(
                    Route.MANUAL_ACTION_RUN.method, Route.MANUAL_ACTION_RUN.path, json_body=body
                )
                break
            except NotFoundError as exc:
                if refreshed:
                    exc.execution_id = execution_id
                    raise
                resolved = await self.resolve(name, params, device=device, component=component)
                body = _manual_execution_body(execution_id, resolved)
                refreshed = True
            except PWSError as exc:
                delay = _manual_retry_delay(exc, retries)
                if delay is None:
                    exc.execution_id = execution_id
                    raise
                await asyncio.sleep(delay)
                retries += 1
        model = _parse_model(payload, ManualActionExecution)
        if model.execution_id != execution_id:
            raise ValidationError("Hub returned a different action execution ID")
        execution = Execution(execution_id, model, resolved.timeout + 15)
        _remember_timeout(self._spot._client.actions._timeouts, execution_id, execution.timeout, model.status)
        if wait:
            execution.result = await self._spot._client.actions.wait(execution_id)
        return execution


class AsyncActionResource:
    """Async status reads and bounded polling for accepted manual actions."""

    def __init__(self, client: AsyncPWS) -> None:
        self._client = client
        self._timeouts: dict[str, float] = {}

    async def get(self, identifier: str) -> ActionExecutionStatus:
        result = await self._client._model_request(_operation(Route.ACTION_EXECUTION, id=identifier))
        _execution_status(result)
        return result

    async def _definition_budget(self, result: ActionExecutionStatus) -> float:
        action_def_id = _status_action_def_id(result)
        async for spot in await self._client.spots.list():
            structure = await self._client._model_request(_operation(Route.SPOT_STRUCTURE, id=spot.id))
            timeout = _definition_timeout(structure, action_def_id)
            if timeout is not None:
                return timeout + 15
        raise ValidationError(f"Action definition {action_def_id!r} is unavailable; pass timeout=")

    async def list(
        self,
        *,
        device: str | None = None,
        action: str | None = None,
        status: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> ActionExecutionSearchResult:
        params: dict[str, object] = {**_page_params(page, limit)}
        if device is not None:
            params["deviceId"] = device
        if action is not None:
            params["actionDefId"] = action
        if status is not None:
            params["status"] = status
        payload = await self._client._request(_operation(Route.ACTION_EXECUTIONS), params=params)
        return _parse_model(payload, ActionExecutionSearchResult)

    async def wait(self, identifier: str, *, timeout: float | None = None) -> ActionExecutionStatus:
        first = None
        budget = timeout if timeout is not None else self._timeouts.get(identifier)
        if budget is None:
            first = await self.get(identifier)
            if _terminal_result(first):
                return _completed_wait(self._timeouts, identifier, first)
            budget = await self._definition_budget(first)
        deadline = _wait_deadline(budget)
        interval = 2.0
        result = first
        while True:
            if result is None:
                result = await self.get(identifier)
            if _terminal_result(result):
                return _completed_wait(self._timeouts, identifier, result)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _wait_expired(identifier, status=_execution_status(result))
            await asyncio.sleep(min(interval, remaining))
            interval = min(interval * 1.3, 5.0)
            result = None

    wait_for_execution = wait

    async def wait_many(
        self, identifiers: Iterable[str], *, timeout: float | None = None
    ) -> dict[str, ActionExecutionStatus]:
        pending = dict.fromkeys(identifiers)
        if not pending:
            return {}
        deadlines = _wait_deadlines(pending, self._timeouts, timeout)
        results: dict[str, ActionExecutionStatus] = {}
        latest: dict[str, str] = {}
        interval = 2.0
        while pending:
            payload = await self._client._request(
                _operation(Route.ACTION_EXECUTION_BATCH), params={"ids": ",".join(pending)}
            )
            batch = _parse_model(payload, ActionExecutionBatchStatus).executions
            for identifier in tuple(pending):
                # A batch item does not say which store answered it; the single
                # status route does, so it supplies every returned status.
                item = batch.get(identifier)
                if item is not None and item.status not in _TERMINAL_STATUSES:
                    latest[identifier] = item.status
                    continue
                result = await self.get(identifier)
                latest[identifier] = _execution_status(result)
                if _terminal_result(result):
                    results[identifier] = result
                    del pending[identifier]
                    self._timeouts.pop(identifier, None)
            if not pending:
                break
            delay = _next_wait_delay(pending, deadlines, interval)
            if delay == 0:
                raise _wait_many_expired(pending, deadlines, results, latest)
            await asyncio.sleep(delay)
            interval = min(interval * 1.3, 5.0)
        return results


class AsyncSpotResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def get(self, identifier: str) -> AsyncSpotHandle:
        if _looks_like_uuid(identifier):
            spot = await self._client._model_request(_operation(Route.SPOT, id=identifier))
        else:
            spot = await self._client._model_request(_operation(Route.SPOT_BY_SLUG, slug=identifier))
        return AsyncSpotHandle(self._client, spot)

    async def list(self, *, page: int | None = None, limit: int | None = None) -> Page[Spot]:
        params = _skip_take_page_params(page, limit)
        return await self._client._page_request(_operation(Route.SPOTS), params=params, total_limit=limit)

    async def create(self, name: str, *, slug: str, description: str | None = None) -> CreatedSpot:
        operation = _operation(Route.SPOT_CREATE)
        return _parse_model(await self._client._send(operation, _spot_body(name, slug, description)), CreatedSpot)


class AsyncAgentResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(self, *, spot: str | None = None) -> list[Agent]:
        page = await self._client._page_request(_operation(Route.AGENTS), params=_agent_list_params(spot))
        return [agent async for agent in page]

    async def create(self, name: str, *, identifier: str, spot: str) -> Agent:
        body = {"name": name, "identifier": identifier, "spotId": spot}
        return _parse_model(await self._client._send(_operation(Route.AGENT_CREATE), body), Agent)


class AsyncComponentResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(self, device_id: str, *, page: int | None = None, limit: int | None = None) -> Page[Component]:
        params = {"deviceId": device_id, **_page_params(page, limit)}
        return await self._client._page_request(_operation(Route.COMPONENTS), params=params, total_limit=limit)


class AsyncAccessKeyResource:
    """Async equivalent of :class:`AccessKeyResource`."""

    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(self, agent_id: str) -> list[AccessKey]:
        return _access_keys(await self._client._request(_operation(Route.ACCESS_KEYS, id=agent_id)))

    async def issue(
        self, agent_id: str, name: str, *, description: str | None = None, expires_at: datetime | str | None = None
    ) -> IssuedAccessKey:
        body = _access_key_body(name, description, expires_at)
        return _issued_access_key(await self._client._send(_operation(Route.ACCESS_KEY_ISSUE, id=agent_id), body))

    async def rotate(self, agent_id: str, key_id: str, *, expires_at: datetime | str | None = None) -> IssuedAccessKey:
        operation = _operation(Route.ACCESS_KEY_ROTATE, id=agent_id, keyId=key_id)
        return _issued_access_key(await self._client._send(operation, _access_key_body(None, None, expires_at)))

    async def reissue(self, agent_id: str, key_id: str, *, expires_at: datetime | str | None = None) -> IssuedAccessKey:
        operation = _operation(Route.ACCESS_KEY_REISSUE, id=agent_id, keyId=key_id)
        return _issued_access_key(await self._client._send(operation, _access_key_body(None, None, expires_at)))

    async def revoke(self, agent_id: str, key_id: str) -> None:
        await self._client._request(_operation(Route.ACCESS_KEY_REVOKE, id=agent_id, keyId=key_id))

    async def plain_key(self, agent_id: str, key_id: str) -> SecretStr | None:
        """The stored key, or ``None`` when the Hub keeps no recoverable copy (rotate or reissue instead)."""

        return _revealed_secret(
            await self._client._request(_operation(Route.ACCESS_KEY_PLAIN, id=agent_id, keyId=key_id))
        )


class AsyncRuleResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(self, spot_id: str, *, page: int | None = None, limit: int | None = None) -> Page[Rule]:
        return await AsyncSpotRuleResource(self._client, spot_id).list(page=page, limit=limit)

    async def get(self, spot_id: str, identifier: str) -> Rule:
        return await AsyncSpotRuleResource(self._client, spot_id).get(identifier)

    async def executions(self, spot_id: str, identifier: str) -> Sequence[RuleExecution]:
        """Return the 10 most recent executions for a rule in this spot."""

        return await AsyncSpotRuleResource(self._client, spot_id).executions(identifier)


class AsyncDeviceResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def status(self, identifier: str) -> DeviceStatus:
        return await self._client._model_request(_operation(Route.DEVICE_STATUS, id=identifier))

    async def list(self, spot_id: str, *, page: int | None = None, limit: int | None = None) -> Page[Device]:
        params = {"spotId": spot_id, **_page_params(page, limit)}
        return await self._client._page_request(_operation(Route.DEVICES), params=params, total_limit=limit)

    async def get(self, identifier: str) -> Device:
        return await self._client._model_request(_operation(Route.DEVICE, id=identifier))

    async def status_by_spot(self, device_ids: Iterable[str], *, max_devices: int = 100) -> StatusBatchResult:
        identifiers = tuple(device_ids)
        if max_devices > 100:
            raise ValueError("status fan-out has a maximum of 100 devices")
        if len(identifiers) > 100:
            raise ValueError("status fan-out has a maximum of 100 devices")
        if len(identifiers) > max_devices:
            raise ValueError(f"status fan-out accepts at most {max_devices} devices")
        results: dict[str, DeviceStatus] = {}
        failed: list[str] = []
        for identifier in identifiers:
            try:
                results[identifier] = await self.status(identifier)
            except PWSError:
                failed.append(identifier)
        return StatusBatchResult(results=results, failed=tuple(failed))


class AsyncTelemetryResource:
    """Async twin of :class:`TelemetryResource`."""

    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def topics(self, device: str) -> TelemetryTopics:
        agent_id = await self._agent_id(device)
        return await self._client._model_request(_operation(Route.TELEMETRY_TOPICS, id=agent_id))

    async def query(
        self,
        device: str,
        topic: str,
        since: str | datetime | timedelta,
        *,
        step: str | None = None,
        until: str | datetime | timedelta | None = None,
    ) -> Telemetry:
        agent_id = await self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=(topic,), step=step, single=True)
        return _parse_model(
            await self._client._request(_operation(Route.TELEMETRY, id=agent_id), params=params), Telemetry
        )

    async def batch(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        *,
        step: str | None = None,
        until: str | datetime | timedelta | None = None,
    ) -> TelemetryBatch:
        agent_id = await self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=topics, step=step)
        return _parse_model(
            await self._client._request(_operation(Route.TELEMETRY_BATCH, id=agent_id), params=params),
            TelemetryBatch,
        )

    async def rollup(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        *,
        step: str,
        until: str | datetime | timedelta | None = None,
    ) -> TelemetryBatchRollup:
        agent_id = await self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=topics, step=step)
        return _parse_model(
            await self._client._request(_operation(Route.TELEMETRY_BATCH_ROLLUP, id=agent_id), params=params),
            TelemetryBatchRollup,
        )

    async def batch_export(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        *,
        until: str | datetime | timedelta | None = None,
    ) -> TelemetryBatchExport:
        agent_id = await self._agent_id(device)
        params = _telemetry_params(since, until=until, topic_ids=topics)
        return _parse_model(
            await self._client._request(_operation(Route.TELEMETRY_BATCH_EXPORT, id=agent_id), params=params),
            TelemetryBatchExport,
        )

    async def export(
        self,
        device: str,
        topics: Sequence[str],
        since: str | datetime | timedelta,
        dest: str | Path = "telemetry.csv",
        *,
        until: str | datetime | timedelta | None = None,
        aggregation: str = "rollup",
        include_boundary: bool = True,
        sample_interval: str = "15s",
        timestamp_time_zone: str = "UTC",
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        agent_id = await self._agent_id(device)
        start_time, end_time = _telemetry_range(since, until=until)
        body = {
            "topicIds": list(topics),
            "startTime": start_time,
            "endTime": end_time,
            "format": "csv",
            "aggregation": aggregation,
            "includeBoundary": include_boundary,
            "sampleInterval": sample_interval,
            "timestampTimeZone": timestamp_time_zone,
        }
        target = Path(dest)
        return await self._client._file_request(
            _operation(Route.TELEMETRY_EXPORT, id=agent_id),
            target=target,
            json_body=body,
            headers={"Accept": "text/csv, application/zip"},
            expected_content_type="text/csv",
            on_progress=on_progress,
        )

    async def _agent_id(self, device: str) -> str:
        detail = await self._client.devices.get(device)
        return _device_agent_id(detail, device)


class AsyncCaptureResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(
        self,
        *,
        spot: str | None = None,
        device: str | None = None,
        status: str | None = None,
        since: str | datetime | timedelta | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> Page[CaptureSession]:
        params = _capture_params(spot=spot, device=device, status=status, since=since, page=page, limit=limit)
        return await self._client._page_request(_operation(Route.CAPTURES), params=params, total_limit=limit)

    async def get(self, identifier: str) -> AsyncCaptureSessionHandle:
        detail = await self._client._model_request(_operation(Route.CAPTURE, id=identifier))
        return AsyncCaptureSessionHandle(self._client, detail)

    async def latest(self, *, spot: str | None = None, status: str | None = None) -> AsyncCaptureSessionHandle | None:
        params = _capture_params(spot=spot, status=status, limit=1, latest=True)
        page = await self._client._page_request(_operation(Route.CAPTURES), params=params, total_limit=1)
        if not page.items:
            return None
        return await self.get(page.items[0].id)


class AsyncCaptureSessionHandle:
    def __init__(self, client: AsyncPWS, detail: CaptureSessionDetail) -> None:
        self._client = client
        self._detail = detail

    @property
    def id(self) -> str:
        return self._detail.id

    @property
    def name(self) -> str:
        return self._detail.name

    @property
    def status(self) -> str:
        return self._detail.status

    @property
    def model(self) -> CaptureSessionDetail:
        return self._detail

    @property
    def media(self) -> list[CaptureSessionDetailMedia]:
        return list(self._detail.media)

    async def download(self, dest: str | Path = ".", *, on_progress: ProgressCallback | None = None) -> list[Path]:
        """Download every media asset of the session into the directory ``dest`` and return the paths.

        ``dest`` is always a directory: it is created when missing (a dotted name such as ``run.1`` included)
        and :class:`ValidationError` is raised when it exists as a file.
        """

        directory = _prepare_download_directory(dest)
        paths: list[Path] = []
        for item in self._detail.media:
            paths.append(
                await self._client.media.download(item.id, directory, on_progress=on_progress, _format=item.format)
            )
        return paths


class AsyncMediaResource:
    def __init__(self, client: AsyncPWS) -> None:
        self._client = client

    async def list(
        self,
        *,
        capture: str | None = None,
        spot: str | None = None,
        device: str | None = None,
        modality: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> Page[MediaAsset]:
        params = _media_params(session=capture, spot=spot, device=device, modality=modality, page=page, limit=limit)
        return await self._client._page_request(_operation(Route.MEDIA), params=params, total_limit=limit)

    async def get(self, identifier: str) -> MediaAsset:
        return await self._client._model_request(_operation(Route.MEDIA_ASSET, id=identifier))

    async def band_provenance(self, identifier: str) -> BandProvenance:
        """Async twin of :meth:`MediaResource.band_provenance`."""

        return await self._client._model_request(_operation(Route.MEDIA_BAND_PROVENANCE, id=identifier))

    async def upload(
        self,
        file: str | Path,
        *,
        thumbnail: str | Path,
        capture: str,
        width: int,
        height: int,
        modality: str = "RGB",
        spot: str | None = None,
        device: str | None = None,
    ) -> CompleteImageUploadResponse:
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
                session=capture,
                width=width,
                height=height,
                modality=modality,
                spot=spot,
                device=device,
            )
            issued = _parse_model(
                await self._client._raw_request(Route.MEDIA_UPLOAD.method, Route.MEDIA_UPLOAD.path, json_body=body),
                UploadImageResponse,
            )
            await self._client._transport.upload_opened(
                issued.upload_url, image_source, size=image_size, content_type=image_type
            )
            await self._client._transport.upload_opened(
                issued.thumbnail_upload_url, preview_source, size=preview_size, content_type=preview_type
            )
        return _parse_model(
            await self._client._raw_request(
                Route.MEDIA_COMPLETE_UPLOAD.method,
                Route.MEDIA_COMPLETE_UPLOAD.path,
                json_body={"mediaAssetId": issued.media_asset_id, "width": width, "height": height},
            ),
            CompleteImageUploadResponse,
        )

    async def upload_registered_multispectral(
        self,
        source_asset_id: str,
        aligned_bands: object,
        *,
        capture: str,
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
        """Async twin of :meth:`MediaResource.upload_registered_multispectral`."""

        bands, registration = _registered_multispectral_declaration(
            source_asset_id,
            aligned_bands,
            record_fragment=record_fragment,
            path=path,
            profile=profile,
            band_metadata=band_metadata,
        )
        source_provenance: object = _MISSING
        if normalization is None or interpretation is None:
            try:
                source_provenance = await self.band_provenance(source_asset_id)
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
        return await self.upload_array(
            "MULTISPECTRAL",
            bands,
            capture=capture,
            labels=labels,
            derived_from=[source_asset_id],
            radiometric_level=radiometric_level,
            calibration=calibration,
            registration=registration,
            normalization=normalization,
            interpretation=interpretation,
        )

    async def upload_array(
        self,
        modality: str,
        data: object,
        *,
        capture: str,
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
        """Async twin of :meth:`MediaResource.upload_array`."""

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
        extras = _array_reservation_extras(modality, capture, labels, derived_from, descriptor, capture_parameters)
        declarations = _array_provenance_declarations(modality, registration, normalization, interpretation)
        channel = _ArrayWorkerChannel()
        worker = _start_array_worker(channel, modality, data, capture, extras, descriptor, declarations)
        try:
            prepared = await asyncio.wrap_future(channel.prepared)
            reservation = _array_reservation(
                await self._client._raw_request(
                    Route.MEDIA_ZARR_UPLOAD.method, Route.MEDIA_ZARR_UPLOAD.path, json_body=prepared.reservation
                ),
                modality,
            )
            reserved_id = cast(str, reservation["mediaAssetId"])
            try:
                channel.inbox.put(reservation)
                await asyncio.wrap_future(channel.members)
                await self._client._transport.upload(
                    cast(str, reservation["thumbnailUploadUrl"]), prepared.preview, content_type="image/jpeg"
                )
                channel.inbox.put(_UPLOAD_FINISHED)
                # The store is gone before the completion request. Shielded: a cancel arriving during the cleanup
                # must not cancel the worker-owned future, whose set_result in the worker's finally would then raise.
                await asyncio.shield(asyncio.wrap_future(channel.finished))
                completed = await self._client._raw_request(
                    Route.MEDIA_ZARR_COMPLETE.method,
                    Route.MEDIA_ZARR_COMPLETE.path,
                    json_body={"mediaAssetId": reserved_id, **prepared.completion},
                )
                return _array_result(completed, reserved_id, modality)
            except PWSError:
                raise
            except Exception:
                raise TransportError(f"{modality} upload failed after reservation") from None
        finally:
            # On every exit, including cancellation and event-loop shutdown: the worker removes the store itself
            # and no PUT starts after this. The call settles now; it does not wait for the worker.
            channel.abandon()
            if not channel.finished.done():
                _join_when_the_loop_shuts_down(worker)

    async def upload_depth(
        self,
        array: object,
        *,
        unit: str | None = None,
        scale: float | None = None,
        offset: float | None = None,
        no_data: float | None = None,
        display_range: tuple[float, float] | None = None,
        colormap: str | None = None,
        intrinsics: Mapping[str, float] | None = None,
        source_sensor: str | None = None,
        capture: str,
    ) -> ArrayUploadResult:
        """Async twin of :meth:`MediaResource.upload_depth`."""

        return await self.upload_array(
            "DEPTH",
            array,
            capture=capture,
            unit=unit,
            scale=scale,
            offset=offset,
            no_data=no_data,
            display_range=display_range,
            colormap=colormap,
            intrinsics=intrinsics,
            source_sensor=source_sensor,
        )

    async def download_depth(self, identifier: str) -> tuple[np.ndarray, dict[str, object]]:
        _depth._require_depth_extra()
        asset = await self.get(identifier)
        metadata = _depth_metadata(asset)
        with tempfile.TemporaryDirectory(prefix="pws-depth-") as temporary:
            root = await self.download(
                identifier,
                Path(temporary),
                _format=asset.format,
                _array_paths=(_depth._array_path(depth_policy()),),
                _admit=_depth.admit_download,
            )
            return await asyncio.to_thread(_depth.read_depth, root), metadata

    async def download_multiband(self, identifier: str, *, band_id: str | None = None) -> MultibandData:
        """Async twin of :meth:`MediaResource.download_multiband`."""

        _depth._require_depth_extra("bands.v1")
        asset = await self.get(identifier)
        descriptor = _multiband_metadata(asset, band_id=band_id)
        with tempfile.TemporaryDirectory(prefix="pws-multiband-") as temporary:
            root = await self.download(
                identifier,
                Path(temporary),
                _format=asset.format,
                _array_paths=tuple(
                    f"bands/{band['id']}" for band in cast(list[dict[str, object]], descriptor["bands"])
                ),
                _admit=lambda staged, members: _multiband.admit_download(staged, descriptor, members),
            )
            return await asyncio.to_thread(_multiband.read_multiband_store, root, descriptor, band_id=band_id)

    async def latest(self, spot: str) -> MediaAsset | None:
        payload = await self._client._request(_operation(Route.MEDIA_LATEST, spotId=spot))
        return None if payload is None else _parse_model(payload, MediaAsset)

    async def presigned_url(self, identifier: str, *, expires_in: int | None = None) -> MediaAssetPresignedUrl:
        params = {"expiresIn": expires_in} if expires_in is not None else None
        payload = await self._client._request(_operation(Route.MEDIA_PRESIGNED_URL, id=identifier), params=params)
        return _parse_model(payload, MediaAssetPresignedUrl)

    async def download(
        self,
        identifier: str,
        dest: str | Path = ".",
        *,
        on_progress: ProgressCallback | None = None,
        _format: str | None = None,
        _array_paths: tuple[str, ...] | None = None,
        _admit: _zarr_storage.DownloadAdmission | None = None,
    ) -> Path:
        """Resolve a presigned URL and stream the object to disk; returns the written path.

        ``dest`` is a directory or a file path.  An existing directory, a string ending in a path separator, or a
        path that does not exist yet and has no file suffix (``output``) means a directory; any other path
        (``capture.png``, an existing file) is a file.  Zarr assets are materialised as ``<dest>/<id>.zarr/`` from
        the Hub's per-file presigned map.
        """

        trailing_separator = _separator_intent(dest)
        asset_format = _format if _format is not None else (await self.get(identifier)).format
        if _is_zarr_format(asset_format):
            destination = Path(dest)
            directory = _is_directory(destination, trailing_separator=trailing_separator)
            root = destination / f"{_safe_identifier(identifier)}.zarr" if directory else destination
            _zarr_storage.validate_download_root(root)
            listing_started = time.monotonic()
            payload = await self._client._request(_operation(Route.MEDIA_ZARR_FILES, id=identifier))
            listing = _parse_model(payload, ZarrFiles)
            deadline = listing_started + listing.expires_in
            with _zarr_storage.staged_download_store(
                root,
                listing.files,
                listing.member_sizes,
                listing.total_files,
                listing.total_bytes,
                listing.download_ready,
                listing.completed_bytes,
                array_paths=_array_paths,
            ) as (staged, members):
                for member in _zarr_storage.admitted_download_members(staged, members, _admit):
                    target = staged / member.relative
                    written = await self._client._transport.download(
                        member.url,
                        target,
                        expected_content_type="application/octet-stream",
                        max_bytes=member.expected_bytes,
                        deadline=deadline,
                    )
                    if written != member.expected_bytes:
                        raise ValidationError(f"Zarr member {member.relative!r} changed during download")
            return root
        presigned = await self.presigned_url(identifier)
        target = _resolve_target(
            Path(dest), identifier, asset_format, presigned.url, trailing_separator=trailing_separator
        )
        await self._client._transport.download(
            presigned.url,
            target,
            on_progress=on_progress,
            expected_content_type=_media_content_type(asset_format),
        )
        return target


class AsyncPWS:
    """Async facade exposing the same resource names as :class:`PWS`."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        org: str | None = None,
        profile: str = "default",
        credential: Credential | None = None,
        transport: AsyncTransport | None = None,
        timeout: float | None = None,
        _config: Config | None = None,
        _owns_transport: bool | None = None,
    ) -> None:
        if _config is not None:
            config = _config
        elif credential is None:
            config = Config.resolve(
                api_key=api_key,
                base_url=transport.base_url if transport is not None else base_url,
                org=org,
                profile=profile,
                timeout=timeout,
            )
        else:
            config = Config(
                api_key=api_key or "",
                base_url=base_url or (transport.base_url if transport is not None else DEFAULT_BASE_URL),
                org=org,
                timeout=timeout or 30.0,
                profile=profile,
            )
        self.config = config
        self._transport = transport or AsyncTransport(config.base_url, timeout=config.timeout)
        self._owns_transport = transport is None if _owns_transport is None else _owns_transport
        self._credential: Credential | None = credential or _credential_from_config(config)
        self._authenticated = False
        self.organizations = AsyncOrganizationResource(self)
        self.spots = AsyncSpotResource(self)
        self.devices = AsyncDeviceResource(self)
        self.components = AsyncComponentResource(self)
        self.rules = AsyncRuleResource(self)
        self.telemetry = AsyncTelemetryResource(self)
        self.captures = AsyncCaptureResource(self)
        self.media = AsyncMediaResource(self)
        self.actions = AsyncActionResource(self)
        self.agents = AsyncAgentResource(self)
        self.access_keys = AsyncAccessKeyResource(self)
        self.raw = AsyncRawResource(self)

    @classmethod
    def resource_names(cls) -> tuple[str, ...]:
        return PWS.resource_names()

    async def me(self) -> Identity:
        """Async equivalent of :meth:`PWS.me`."""

        credential = _session_credential(self._credential)
        await self._ensure_auth()
        user_id = _session_user_id(credential)
        organizations = [item async for item in await self.organizations.for_user(user_id)]
        return Identity(user_id, credential.user_email, credential.expires_at, organizations)

    async def my_organizations(self) -> Page[Organization]:
        """Async equivalent of :meth:`PWS.my_organizations`."""

        credential = _session_credential(self._credential)
        await self._ensure_auth()
        return await self.organizations.for_user(_session_user_id(credential))

    async def access_info(self) -> AccessInfo:
        """Async equivalent of :meth:`PWS.access_info`."""

        organization_id = self.config.org
        if organization_id is None:
            raise OrganizationScopeError(
                "no organization scope is set; check the scope: --org/org=, else PWS_ORG, else the profile's org"
            )
        payload = await self._request(_operation(Route.ACCESS_INFO), params={"organizationId": organization_id})
        return _parse_model(payload, AccessInfo)

    def with_org(self, org: str) -> AsyncPWS:
        return AsyncPWS(
            credential=self._credential,
            transport=self._transport,
            _config=Config(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                org=org,
                timeout=self.config.timeout,
                profile=self.config.profile,
                session_token=self.config.session_token,
                device_session_token=self.config.device_session_token,
                credentials_file=self.config.credentials_file,
            ),
            _owns_transport=False,
        )

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
    ) -> object:
        await self._ensure_auth()
        for attempt in range(2):
            try:
                return await self._transport.request(
                    method,
                    path,
                    headers=self._headers(),
                    params=params,
                    json_body=json_body,
                )
            except PWSError as exc:
                if exc.status_code == 401:
                    _invalidate(self._credential)
                if attempt == 0 and _can_reauthenticate(self._credential, exc, method):
                    await self._reauthenticate()
                    continue
                raise _scope_error(exc, self.config.org) from exc
        raise AssertionError("unreachable")

    async def _request[ModelT: BaseModel](
        self,
        operation: BoundOperation[ModelT],
        *,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
    ) -> object:
        try:
            return await self._raw_request(operation.spec.method, operation.path, params=params)
        except PWSError as exc:
            error = _public_error(operation, exc)
        raise error

    async def _send[ModelT: BaseModel](self, operation: BoundOperation[ModelT], body: Mapping[str, object]) -> object:
        try:
            return await self._raw_request(operation.spec.method, operation.path, json_body=body)
        except PWSError as exc:
            error = _public_error(operation, exc)
        raise error

    async def _model_request[ModelT: BaseModel](self, operation: BoundOperation[ModelT]) -> ModelT:
        payload = await self._request(operation)
        model = operation.spec.model
        if model is None:
            raise TypeError(f"expected a modelled operation, got {operation.spec.method} {operation.path}")
        return _parse_model(payload, model)

    async def _file_request(
        self,
        operation: BoundOperation[BaseModel],
        *,
        target: Path,
        json_body: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
        expected_content_type: str | None = None,
    ) -> Path:
        await self._ensure_auth()
        for attempt in range(2):
            try:
                await self._transport.download_request(
                    operation.spec.method,
                    operation.path,
                    target,
                    headers={**self._headers(), **(headers or {})},
                    json_body=json_body,
                    on_progress=on_progress,
                    expected_content_type=expected_content_type,
                )
            except PWSError as exc:
                if exc.status_code == 401:
                    _invalidate(self._credential)
                if attempt == 0 and _can_reauthenticate(self._credential, exc, operation.spec.method):
                    await self._reauthenticate()
                    continue
                raise _scope_error(exc, self.config.org) from exc
            return target
        raise AssertionError("unreachable")

    async def _page_request[ModelT: BaseModel](
        self,
        operation: BoundOperation[ModelT],
        *,
        params: Mapping[str, object] | None = None,
        total_limit: int | None = None,
        _walk: frozenset[frozenset[tuple[str, str]]] = frozenset(),
    ) -> Page[ModelT]:
        if not operation.spec.pagination:
            raise TypeError(f"expected a paginated operation, got {operation.spec.method} {operation.path}")
        walk = _record_request(params, _walk)
        payload = await self._request(operation, params=params)
        if not isinstance(payload, Page):
            raise TypeError(f"expected a paginated response from {operation.path}")
        model = operation.spec.model
        if model is None:
            raise TypeError(f"expected a modelled operation, got {operation.spec.method} {operation.path}")
        result = Page(
            items=[_parse_model(item, model) for item in payload.items],
            pagination=payload.pagination,
            meta=payload.meta,
            _total_limit=total_limit,
        )
        _require_requested_page(params, result)
        next_params = _next_page_params(params, result)
        if next_params is not None:
            result._anext = lambda: self._page_request(
                operation, params=next_params, total_limit=total_limit, _walk=walk
            )
        return result

    async def _ensure_auth(self) -> None:
        if self._credential is None:
            if self._authenticated:
                return
            raise RuntimeError("no credential is configured")
        await self._credential.async_refresh(self._transport)
        self._authenticated = True

    async def _reauthenticate(self) -> None:
        await self._ensure_auth()

    def _headers(self) -> Mapping[str, str]:
        headers = dict(self._credential.headers()) if self._credential is not None else {}
        if self.config.org:
            headers["X-Organization-Id"] = self.config.org
        return headers

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> AsyncPWS:
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        await self.aclose()


class _Invalidatable(Protocol):
    def invalidate(self) -> None: ...


_REPLAYABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _invalidate(credential: Credential | None) -> None:
    """Any 401 drops the rejected JWT (memory and cache), whether or not the request is replayed."""

    invalidate = getattr(credential, "invalidate", None)
    if callable(invalidate):
        cast(_Invalidatable, credential).invalidate()


def _can_reauthenticate(credential: Credential | None, error: PWSError, method: str) -> bool:
    """Replay once after a 401 only for reads, and only for credentials that re-mint JWTs from a session.

    A write is never replayed: the Hub may have acted on it.  Writes rely on the
    proactive refresh before the JWT expires and surface a 401 otherwise.
    """

    return (
        error.status_code == 401
        and method.upper() in _REPLAYABLE_METHODS
        and callable(getattr(credential, "invalidate", None))
    )


def _credential_from_config(config: Config) -> Credential | None:
    """An operator session wins over an agent key: only a session reaches operator routes.

    ``config.session_token`` comes only from ``PWS_SESSION_TOKEN`` or an explicit
    argument; a stored session is always a device session (``pws auth login``).
    """

    if config.device_session_token:
        store = (
            DeviceJwtStore(config.credentials_file, config.profile, config.device_session_token)
            if config.credentials_file is not None
            else None
        )
        return DeviceSessionCredential(config.device_session_token, hub_url=config.base_url, store=store)
    if config.session_token:
        return SessionCredential(session_token=config.session_token)
    if config.api_key:
        return ApiKeyCredential(config.api_key)
    return None


MAX_PAGE_SIZE = 100
"""The largest ``limit``/``take`` the Hub's list routes accept; ``limit=`` stays a total cap."""


def _page_params(page: int | None, limit: int | None) -> dict[str, int]:
    params: dict[str, int] = {}
    if page is not None:
        params["page"] = page
    if limit is not None:
        params["limit"] = min(limit, MAX_PAGE_SIZE)
    return params


def _agent_list_params(spot: str | None) -> dict[str, object]:
    """The agents route pages by ``limit``/``offset``; start at the largest page and let the walk advance."""

    params: dict[str, object] = {"limit": MAX_PAGE_SIZE, "offset": 0}
    if spot is not None:
        params["spotId"] = spot
    return params


def _skip_take_page_params(page: int | None, limit: int | None) -> dict[str, int]:
    take = min(limit or 20, MAX_PAGE_SIZE)
    return {"skip": ((page or 1) - 1) * take, "take": take}


def _capture_params(
    *,
    spot: str | None = None,
    device: str | None = None,
    status: str | None = None,
    since: str | datetime | timedelta | None = None,
    page: int | None = None,
    limit: int | None = None,
    latest: bool = False,
) -> dict[str, object]:
    params: dict[str, object] = {**_page_params(page, limit)}
    if spot is not None:
        params["spotId"] = spot
    if device is not None:
        params["deviceId"] = device
    if status is not None:
        params["status"] = status
    if since is not None:
        params["createdAfter"] = _since_to_iso(since)
    if latest:
        params["sortBy"] = "createdAt"
        params["sortOrder"] = "desc"
    return params


def _media_params(
    *,
    session: str | None = None,
    spot: str | None = None,
    device: str | None = None,
    modality: str | None = None,
    page: int | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {**_page_params(page, limit)}
    if session is not None:
        params["captureSessionId"] = session
    if spot is not None:
        params["spotId"] = spot
    if device is not None:
        params["deviceId"] = device
    if modality is not None:
        params["modality"] = modality
    return params


def _telemetry_range(
    since: str | datetime | timedelta,
    *,
    until: str | datetime | timedelta | None = None,
) -> tuple[str, str]:
    return _since_to_iso(since), _since_to_iso(until or datetime.now(UTC))


def _telemetry_params(
    since: str | datetime | timedelta,
    *,
    until: str | datetime | timedelta | None = None,
    topic_ids: Sequence[str],
    step: str | None = None,
    single: bool = False,
) -> dict[str, object]:
    start_time, end_time = _telemetry_range(since, until=until)
    identifiers = (topic_ids[0],) if single and topic_ids else tuple(topic_ids)
    params: dict[str, object] = {
        "startTime": start_time,
        "endTime": end_time,
        ("topicId" if single else "topicIds"): identifiers[0] if single else ",".join(identifiers),
    }
    if step is not None:
        params["step"] = step
    return params


_SINCE_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def _since_to_iso(value: str | datetime | timedelta) -> str:
    """Accept ``"30d"``-style windows, ``timedelta`` or an absolute ``datetime``."""

    now = datetime.now(UTC)
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    elif isinstance(value, timedelta):
        moment = now - value
    else:
        match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", value)
        if match is None:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
        else:
            moment = now - timedelta(**{_SINCE_UNITS[match.group(2)]: int(match.group(1))})
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _separator_intent(dest: str | os.PathLike[str]) -> bool:
    """Whether the caller spelled ``dest`` with a trailing path separator.

    ``Path()`` drops the separator, so the intent has to be read from the original argument.
    """

    return os.fspath(dest).endswith(("/", "\\"))


def _is_directory(dest: Path, *, trailing_separator: bool = False) -> bool:
    """A destination is a directory when it exists as one, the caller ended it with a separator, or, for a
    path that does not exist yet, it carries no file suffix."""

    if dest.is_dir() or trailing_separator:
        return True
    if dest.is_file():
        return False
    return dest.suffix == ""


def _prepare_download_directory(dest: str | os.PathLike[str]) -> Path:
    """Create the directory a bulk download writes into; refuse a path that already exists as a file.

    A bulk download always targets a directory, so a not-yet-existing name such as ``run.1`` is a directory
    too, never a file whose suffix says otherwise.
    """

    directory = Path(dest)
    if directory.exists() and not directory.is_dir():
        raise ValidationError(f"download destination exists and is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _extension(candidate: str | None) -> str | None:
    """A filename extension, or nothing when the candidate cannot safely be one.

    The format arrives from the Hub, so it is server-controlled input that lands
    in a path this SDK writes to. Stripping dots is not enough: a value carrying
    a separator survives into ``dest / f"{id}.{suffix}"``, and the ``parents=True``
    mkdir in the transport then resolves any ``..`` segments at the OS level,
    which puts the write outside ``dest`` entirely. The zarr branch already
    refuses that shape through canonical member-path validation and a single asset has to
    refuse it too. Requiring an alphanumeric token is stricter than the escape
    needs; no real media format is anything else.
    """

    token = (candidate or "").strip().lower().strip(".")
    return token if token.isalnum() else None


_UNSAFE_IDENTIFIER = re.compile(r"[/\\:\x00]")


def _safe_identifier(identifier: str) -> str:
    """The asset id, once it is safe to use as a filename.

    :func:`_extension` guards one half of ``dest / f"{id}.{suffix}"``; this is the
    half that was left open. The id looks caller-supplied, but the ordinary shape
    of this SDK is to list assets and download what the listing returned, so it is
    Hub-controlled in exactly the loop that writes files. A separator, a drive
    prefix, or a bare ``..`` survives into the path, and the transport's
    ``mkdir(parents=True)`` resolves it at the OS level, which puts the write
    outside ``dest``. Only the escape is refused, not the id alphabet: a stricter
    rule would break the first id format the Hub changes to.
    """

    if not identifier or identifier in {".", ".."} or _UNSAFE_IDENTIFIER.search(identifier):
        raise TransportError(f"asset id is not usable as a filename: {identifier!r}")
    return identifier


def _resolve_target(
    dest: Path, identifier: str, asset_format: str | None, url: str, *, trailing_separator: bool = False
) -> Path:
    if not _is_directory(dest, trailing_separator=trailing_separator):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    suffix = _extension(asset_format) or _extension(Path(urlsplit(url).path).suffix) or "bin"
    return dest / f"{_safe_identifier(identifier)}.{suffix}"


def _media_content_type(asset_format: str | None) -> str | None:
    if not asset_format:
        return None
    return mimetypes.guess_type(f"asset.{asset_format}")[0]


def _is_zarr_format(asset_format: str | None) -> bool:
    return bool(asset_format and "zarr" in asset_format.lower())


def _session_credential(credential: Credential | None) -> SessionCredential | DeviceSessionCredential:
    if not isinstance(credential, SessionCredential | DeviceSessionCredential):
        raise AuthError("whoami needs an operator session; run `pws auth login`")
    return credential


def _session_user_id(credential: SessionCredential | DeviceSessionCredential) -> str:
    user_id = credential.user_id
    if user_id is None:
        raise AuthError("the Hub session token carries no user id (`sub`); run `pws auth login` again")
    return user_id


def _scope_error(error: PWSError, org: str | None) -> PWSError:
    """Turn a missing/rejected organization scope into a one-line fix-it exception."""

    if isinstance(error, OrganizationScopeError):
        return error
    if org is None and error.status_code in (400, 403) and _mentions_organization(error):
        return OrganizationScopeError.from_response(error, org=None)
    if org is not None and isinstance(error, PermissionError):
        return OrganizationScopeError.from_response(error, org=org)
    return error


def _mentions_organization(error: PWSError) -> bool:
    text = f"{error} {error.details}".lower()
    return "organization" in text or "x-organization-id" in text


def _next_page_params[T](params: Mapping[str, object] | None, page: Page[T]) -> dict[str, object] | None:
    pagination = page.pagination
    if pagination.next_cursor:
        next_params = dict(params or {})
        next_params["cursor"] = pagination.next_cursor
        return next_params
    if pagination.has_next is False:
        return None
    if pagination.total_pages is None or pagination.total_pages <= 1:
        return None
    current_page = pagination.page or 1
    if current_page >= pagination.total_pages:
        return None
    next_params = dict(params or {})
    take = next_params.get("take")
    if isinstance(take, int):
        next_params["skip"] = current_page * take
        return next_params
    limit = next_params.get("limit")
    if isinstance(next_params.get("offset"), int) and isinstance(limit, int):
        next_params["offset"] = current_page * limit
        return next_params
    next_params["page"] = current_page + 1
    if "limit" not in next_params and pagination.limit is not None:
        # The Hub counts `page` only together with `limit`; alone it reads the first page again.
        next_params["limit"] = pagination.limit
    return next_params


def _require_requested_page[T](params: Mapping[str, object] | None, page: Page[T]) -> None:
    """Refuse a page other than the one requested; never hand back page 1's rows as page N."""

    requested = (params or {}).get("page")
    returned = page.pagination.page
    if isinstance(requested, int) and returned is not None and returned != requested:
        raise TransportError(
            f"the Hub answered page {requested} with page {returned}, so the same page would be read again: "
            "it counts a page only together with a page size; pass one (`--limit`, or `limit=` in Python)"
        )


def _record_request(
    params: Mapping[str, object] | None, walk: frozenset[frozenset[tuple[str, str]]]
) -> frozenset[frozenset[tuple[str, str]]]:
    """This walk's requests plus ``params``; a request the walk already sent means the Hub is not advancing.

    The record is immutable and handed down the page chain, so walking the same Page again starts from that page.
    """

    request = frozenset((name, repr(value)) for name, value in (params or {}).items())
    if request in walk:
        raise TransportError(
            "the Hub led this listing back to a page it already sent; stopping before the same page again"
        )
    return walk | {request}


def _spot_body(name: str, slug: str, description: str | None) -> dict[str, object]:
    body: dict[str, object] = {"name": name, "slug": slug}
    if description is not None:
        body["description"] = description
    return body


def _access_key_body(name: str | None, description: str | None, expires_at: datetime | str | None) -> dict[str, object]:
    """Send only what the caller set: a rotate that names an expiry must match the old one."""

    body: dict[str, object] = {}
    if name is not None:
        body["keyName"] = name
    if description is not None:
        body["description"] = description
    if isinstance(expires_at, datetime):
        moment = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
        body["expiresAt"] = moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    elif expires_at is not None:
        body["expiresAt"] = expires_at
    return body


_ACCESS_KEY_SECRET_FIELDS = frozenset({"plainkey", "keyhash", "lookuphash", "encryptedkey"})


def _access_key(item: object) -> AccessKey:
    """Metadata only: secret-bearing fields go before validation, and a non-object is refused unechoed."""

    if not isinstance(item, Mapping):
        raise TransportError("access key item is not an object")
    return AccessKey.model_validate(
        {key: value for key, value in item.items() if str(key).lower() not in _ACCESS_KEY_SECRET_FIELDS}
    )


def _access_keys(payload: object) -> list[AccessKey]:
    if not isinstance(payload, list):
        raise TransportError("expected an array of access keys")
    return [_access_key(item) for item in payload]


def _issued_access_key(payload: object) -> IssuedAccessKey:
    """Split the secret off before validation so neither the metadata nor an error can carry it."""

    if not isinstance(payload, Mapping) or not isinstance(payload.get("plainKey"), str):
        raise TransportError("access key response carried no plainKey")
    return IssuedAccessKey(key=_access_key(payload), secret=SecretStr(payload["plainKey"]))


def _public_error[ModelT: BaseModel](operation: BoundOperation[ModelT], error: PWSError) -> PWSError:
    """A key route's failure keeps its class and status only: its body, code or request id may echo a secret."""

    return error if "/access-keys" not in operation.spec.path else _status_only(error, "access-key request")


def _refuse_access_key_path(path: str) -> None:
    """Keep ``raw`` off the key routes , however the path is spelled.

    Only path segments count. The query and fragment go first, on the raw string, so an encoded ``%3F`` cannot hide
    a later segment; the rest is decoded until stable, lower-cased and split on ``/`` with ``;`` parameters dropped.
    An ``access-keys`` segment anywhere after ``agents/management`` is refused, both as written and with dot segments
    resolved, so an encoded ``/`` in the id or decoded ``..`` cannot move it out of view.
    """

    decoded = re.split(r"[?#]", path, maxsplit=1)[0]
    while (once := unquote(decoded)) != decoded:
        decoded = once
    written = [segment.split(";", 1)[0] for segment in decoded.lower().replace("\\", "/").split("/")]
    resolved: list[str] = []
    for segment in written:
        if segment == "..":
            del resolved[-1:]
        elif segment not in ("", "."):
            resolved.append(segment)
    if _names_key_route(written) or _names_key_route(resolved):
        raise ValueError(
            "access-key routes are reachable only through pws.access_keys "
            "(list, issue, rotate, reissue, revoke, plain_key)"
        )


def _names_key_route(segments: list[str]) -> bool:
    names = [segment for segment in segments if segment not in ("", ".")]
    return any(
        names[index : index + 2] == ["agents", "management"] and "access-keys" in names[index + 2 :]
        for index in range(len(names) - 1)
    )


def _revealed_secret(payload: object) -> SecretStr | None:
    if not isinstance(payload, Mapping):
        raise TransportError("plain-key response is not an object")
    secret = payload.get("plainKey")
    return SecretStr(secret) if isinstance(secret, str) else None


def _device_agent_id(device: Device, identifier: str) -> str:
    """Resolve the management-plane Agent.id without exposing it in the facade."""

    extra = device.model_extra or {}
    candidate = extra.get("agentId")
    if isinstance(candidate, str) and candidate:
        return candidate
    owner = extra.get("agent")
    if isinstance(owner, Mapping):
        candidate = owner.get("id")
        if isinstance(candidate, str) and candidate:
            return candidate
    raise TransportError(f"device {identifier!r} has no assigned agent")
