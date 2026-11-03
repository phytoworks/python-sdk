"""Media preparation, validation and operation helpers shared by the operator facade and the device persona.

Internal: nothing here is public API. ``phytoworks.facade`` and ``phytoworks.device`` both import from this
module, so neither persona reaches into the other for them (INV-11).
"""

from __future__ import annotations

import contextlib
import math
import mimetypes
import os
import re
import stat
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import quote

from pydantic import BaseModel

from . import _depth, _multiband_write
from .errors import ValidationError
from .models import generated


@dataclass(frozen=True, slots=True)
class OperationSpec[ModelT: BaseModel]:
    """One checked Hub operation, including its response and pagination contract."""

    method: str
    path: str
    model: type[ModelT] | None
    pagination: bool = False
    waiter: bool = False


@dataclass(frozen=True, slots=True)
class BoundOperation[ModelT: BaseModel]:
    """An operation whose template has been safely filled for the request boundary."""

    spec: OperationSpec[ModelT]
    path: str


def _build_operation_table(specs: Mapping[str, OperationSpec[BaseModel]]) -> dict[str, OperationSpec[BaseModel]]:
    """Reject a facade operation before a client can use an unapproved route."""

    # Read at call time, not import time: a facade reload re-checks against the module's current allowlist.
    allowed = frozenset((method, path.removeprefix("/api/v1")) for method, path in generated.G3_OPERATION_ALLOWLIST)
    disallowed = sorted(
        (operation.method, operation.path)
        for operation in specs.values()
        if (operation.method, operation.path) not in allowed
    )
    if disallowed:
        operations = ", ".join(f"{method} {path}" for method, path in disallowed)
        raise RuntimeError(f"facade operation table contains operation outside the G3 allowlist: {operations}")
    return dict(specs)


def _validate_path_parameter(key: str, value: str) -> None:
    if value in ("", ".", ".."):
        raise ValidationError(f"path parameter {key!r} must not be empty or a dot segment")


def _operation[ModelT: BaseModel](spec: OperationSpec[ModelT], **params: str) -> BoundOperation[ModelT]:
    template = spec.path
    for key, value in params.items():
        _validate_path_parameter(key, value)
        template = template.replace("{" + key + "}", quote(value, safe="-_.~"))
    return BoundOperation(spec=spec, path=template)


@dataclass(frozen=True, slots=True)
class ArrayUploadResult:
    """SDK result for the Hub's currently untyped Zarr completion response."""

    media_asset_id: str
    success: bool
    message: str


_ARRAY_MODALITIES = ("DEPTH", "THERMAL", "MULTISPECTRAL")


_BAND_KEYS = ("radiometric_level", "calibration")


_BAND_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


_HOMOGRAPHY_DETERMINANT_EPSILON = 1e-12


_MISSING = object()


# Mirrors shared-types ``MediaAssetLabelsSchema`` and ``MediaAssetDerivedFromSchema`` (FC-Q3, media INV-13).
_LABEL_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")


_MAX_LABELS = 16


_MAX_DERIVED_FROM = 16


def _validated_labels(labels: object) -> dict[str, str]:
    """The media-asset labels (``MediaAssetLabelsSchema``) as a copy, or :class:`ValidationError`; image and array
    uploads share this one rule so it is refused before any reservation request."""

    if (
        not isinstance(labels, Mapping)
        or len(labels) > _MAX_LABELS
        or not all(isinstance(key, str) and _LABEL_KEY.fullmatch(key) for key in labels)
        or not all(isinstance(value, str) and 1 <= len(value) <= 64 for value in labels.values())
    ):
        raise ValidationError(
            f"labels are at most {_MAX_LABELS} keys matching ^[a-z][a-z0-9_]{{0,31}}$ with 1-64 character values"
        )
    return dict(labels)


def _validated_capture_parameters(parameters: object) -> dict[str, str | int | float | bool]:
    """The ``captureParameters`` of a Zarr reservation as a copy, or :class:`ValidationError`. The Hub takes any
    string-keyed record; the SDK narrows it to the JSON scalars agent-rs sends (exposure, gain, frames averaged)
    so a nested or non-finite value is refused before any reservation request."""

    if (
        not isinstance(parameters, Mapping)
        or not all(isinstance(key, str) and key for key in parameters)
        or not all(
            isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))
            for value in parameters.values()
        )
    ):
        raise ValidationError("capture_parameters must map non-empty string keys to str, bool, int or finite float")
    return dict(parameters)


def _check_descriptor_arguments(modality: object, descriptor: Mapping[str, object]) -> None:
    """Refuse a modality the array path does not take, and descriptor arguments that modality does not accept."""

    if modality not in _ARRAY_MODALITIES:
        raise ValidationError("upload_array accepts DEPTH, THERMAL or MULTISPECTRAL; upload images with media.upload")
    scalar_arguments = [value for key, value in descriptor.items() if key not in _BAND_KEYS]
    if modality == "MULTISPECTRAL":
        if any(value is not None for value in scalar_arguments):
            raise ValidationError(
                "MULTISPECTRAL takes no DEPTH descriptor arguments; describe each band with BandInput"
            )
        return
    if any(descriptor.get(key) is not None for key in _BAND_KEYS):
        raise ValidationError(f"{modality} takes no band arguments (radiometric_level, calibration)")
    if modality != "DEPTH" and any(value is not None for value in scalar_arguments):
        raise ValidationError(f"{modality} takes no descriptor arguments; Hub stamps its policy descriptor")


def _array_reservation_extras(
    modality: object,
    session: str,
    labels: Mapping[str, str] | None,
    derived_from: Sequence[str] | None,
    descriptor: Mapping[str, object],
    capture_parameters: Mapping[str, str | int | float | bool] | None = None,
) -> dict[str, object]:
    """Check everything that needs no array or Hub; return the optional reservation fields."""

    _check_descriptor_arguments(modality, descriptor)
    if not isinstance(session, str) or not session:
        raise ValidationError(f"{modality} upload requires a capture session")
    extras: dict[str, object] = {}
    if labels is not None:
        extras["labels"] = _validated_labels(labels)
    if derived_from is not None:
        if (
            isinstance(derived_from, (str, bytes))
            or not isinstance(derived_from, Sequence)
            or not 1 <= len(derived_from) <= _MAX_DERIVED_FROM
            or not all(isinstance(item, str) and _looks_like_uuid(item) for item in derived_from)
            or len(set(derived_from)) != len(derived_from)
        ):
            raise ValidationError(f"derived_from must list 1-{_MAX_DERIVED_FROM} distinct media asset UUIDs")
        extras["derivedFrom"] = list(derived_from)
    if capture_parameters is not None:
        extras["captureParameters"] = _validated_capture_parameters(capture_parameters)
    return extras


def _array_provenance_declarations(
    modality: object,
    registration: Mapping[str, object] | None,
    normalization: Mapping[str, object] | None,
    interpretation: Sequence[Mapping[str, object]] | None,
) -> dict[str, object]:
    """Pass caller declarations to MULTISPECTRAL completion without putting them in the Zarr store."""

    if modality != "MULTISPECTRAL" and any(
        value is not None for value in (registration, normalization, interpretation)
    ):
        raise ValidationError("band provenance declarations require MULTISPECTRAL")
    declarations: dict[str, object] = {}
    if registration is not None:
        declarations["registration"] = registration
    if normalization is not None:
        declarations["normalization"] = normalization
    if interpretation is not None:
        if isinstance(interpretation, (str, bytes)) or not isinstance(interpretation, Sequence):
            raise ValidationError("interpretation must be a sequence of band declarations")
        declarations["interpretation"] = list(interpretation)
    return declarations


def _registered_field(value: object, *names: str) -> object:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        try:
            return getattr(value, name)
        except AttributeError:
            continue
    return _MISSING


def _registered_sequence(value: object, label: str) -> list[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValidationError(f"registered MULTISPECTRAL {label} must be a sequence")
    return list(value)


def _registered_integer(value: object, label: str, *, positive: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < (1 if positive else 0):
        adjective = "positive" if positive else "non-negative"
        raise ValidationError(f"registered MULTISPECTRAL {label} must be a {adjective} integer")
    return value


def _registered_nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"registered MULTISPECTRAL {label} must be non-empty text")
    return value


def _registered_profile(value: object) -> dict[str, str]:
    device_id = _registered_nonempty_text(_registered_field(value, "deviceId", "device_id"), "profile.deviceId")
    profile_key = _registered_nonempty_text(_registered_field(value, "profileKey", "profile_key"), "profile.profileKey")
    revision = _registered_field(value, "revision")
    if isinstance(revision, int) and not isinstance(revision, bool):
        revision_text = str(revision)
    elif isinstance(revision, str):
        revision_text = revision
    else:
        raise ValidationError("registered MULTISPECTRAL profile.revision must be non-empty text or an integer")
    if not revision_text:
        raise ValidationError("registered MULTISPECTRAL profile.revision must be non-empty text")
    return {"deviceId": device_id, "profileKey": profile_key, "revision": revision_text}


def _registered_homography(value: object, label: str) -> list[float]:
    matrix = _registered_sequence(value, f"{label}.matrix")
    if len(matrix) != 9:
        raise ValidationError(f"registered MULTISPECTRAL {label}.matrix must have nine values")
    numbers = [_multiband_write._number(item, f"{label}.matrix") for item in matrix]
    scale = max(abs(number) for number in numbers)
    normalized = [number / scale for number in numbers] if scale > 0 else []
    if scale == 0 or not normalized:
        raise ValidationError(
            f"registered MULTISPECTRAL {label}.matrix determinant must exceed {_HOMOGRAPHY_DETERMINANT_EPSILON}"
        )
    a, b, c, d, e, f, g, h, i = normalized
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant) or abs(determinant) <= _HOMOGRAPHY_DETERMINANT_EPSILON:
        raise ValidationError(
            f"registered MULTISPECTRAL {label}.matrix determinant must exceed {_HOMOGRAPHY_DETERMINANT_EPSILON}"
        )
    return numbers


def _registered_grid(fragment: object) -> tuple[list[int], list[float], list[int]]:
    grid = _registered_field(fragment, "grid")
    if grid is _MISSING:
        raise ValidationError("registered MULTISPECTRAL record_fragment.grid is required")
    shape_values = _registered_sequence(_registered_field(grid, "shape"), "grid.shape")
    if len(shape_values) != 2:
        raise ValidationError("registered MULTISPECTRAL grid.shape must contain height and width")
    shape = [_registered_integer(value, "grid.shape", positive=True) for value in shape_values]
    transform_values = _registered_sequence(_registered_field(grid, "transform"), "grid.transform")
    if len(transform_values) != 6:
        raise ValidationError("registered MULTISPECTRAL grid.transform must have six values")
    transform = [_multiband_write._number(value, "grid.transform") for value in transform_values]

    valid_region = _registered_field(fragment, "validRegion", "valid_region")
    if isinstance(valid_region, Mapping) or valid_region is not _MISSING and not isinstance(valid_region, Sequence):
        x_min = _registered_integer(_registered_field(valid_region, "x"), "validRegion.x")
        y_min = _registered_integer(_registered_field(valid_region, "y"), "validRegion.y")
        width = _registered_integer(_registered_field(valid_region, "width"), "validRegion.width", positive=True)
        height = _registered_integer(_registered_field(valid_region, "height"), "validRegion.height", positive=True)
        region = [x_min, y_min, x_min + width, y_min + height]
    else:
        region_values = _registered_sequence(valid_region, "validRegion")
        if len(region_values) != 4:
            raise ValidationError("registered MULTISPECTRAL validRegion must contain four values")
        region = [_registered_integer(value, "validRegion") for value in region_values]

    x_min, y_min, x_max, y_max = region
    if x_max <= x_min or y_max <= y_min or x_max > shape[1] or y_max > shape[0]:
        raise ValidationError("registered MULTISPECTRAL validRegion must have positive area inside grid.shape")
    return shape, transform, region


def _registered_physical_pixels(
    data: object,
    width: object,
    height: object,
    band_id: str,
    grid_shape: Sequence[int],
) -> object:
    if (width is _MISSING) != (height is _MISSING):
        raise ValidationError(f"registered MULTISPECTRAL output band {band_id!r} needs both width and height")
    if width is not _MISSING:
        output_width = _registered_integer(width, f"band {band_id!r}.width", positive=True)
        output_height = _registered_integer(height, f"band {band_id!r}.height", positive=True)
        if (output_height, output_width) != tuple(grid_shape):
            raise ValidationError(f"registered MULTISPECTRAL output band {band_id!r} dimensions disagree with grid")

    _depth._require_depth_extra("MULTISPECTRAL")
    import numpy as np

    try:
        pixels = np.asarray(data, dtype=np.float32)
        output_height, output_width = grid_shape
        if pixels.ndim == 1 and pixels.size == output_height * output_width:
            pixels = pixels.reshape((output_height, output_width))
        if pixels.ndim != 2 or tuple(pixels.shape) != tuple(grid_shape):
            raise ValidationError(f"registered MULTISPECTRAL output band {band_id!r} dimensions disagree with grid")
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(f"registered MULTISPECTRAL output band {band_id!r} data is invalid") from None
    return pixels


def _registered_result_band_inputs(
    output_values: list[object],
    metadata: list[_multiband_write.BandInput],
    grid_shape: Sequence[int],
    *,
    has_result_shape: bool,
) -> list[_multiband_write.BandInput]:
    if len(output_values) != len(metadata):
        raise ValidationError("registered MULTISPECTRAL output bands must cover band_metadata exactly")
    metadata_by_id = {item.id: item for item in metadata}
    if len(metadata_by_id) != len(metadata):
        raise ValidationError("registered MULTISPECTRAL band_metadata contains duplicate band ids")

    output_by_id: dict[str, object] = {}
    for index, output in enumerate(output_values):
        band_id = _registered_field(output, "bandId", "band_id", "id") if has_result_shape else metadata[index].id
        if band_id is _MISSING and has_result_shape:
            band_id = metadata[index].id
        if not isinstance(band_id, str) or band_id not in metadata_by_id or band_id in output_by_id:
            raise ValidationError("registered MULTISPECTRAL output bands must have unique known band ids")
        data = _registered_field(output, "data", "array") if has_result_shape else output
        if data is _MISSING:
            raise ValidationError(f"registered MULTISPECTRAL output band {band_id!r} has no data")
        width = _registered_field(output, "width") if has_result_shape else _MISSING
        height = _registered_field(output, "height") if has_result_shape else _MISSING
        output_by_id[band_id] = _registered_physical_pixels(data, width, height, band_id, grid_shape)

    if set(output_by_id) != set(metadata_by_id):
        raise ValidationError("registered MULTISPECTRAL output bands must cover band_metadata exactly")
    return [replace(item, array=output_by_id[item.id]) for item in metadata]


def _registered_band_inputs(
    aligned_bands: object,
    band_metadata: Sequence[_multiband_write.BandInput] | None,
    grid_shape: Sequence[int],
) -> list[_multiband_write.BandInput]:
    if (
        isinstance(aligned_bands, Sequence)
        and not isinstance(aligned_bands, (str, bytes))
        and all(isinstance(item, _multiband_write.BandInput) for item in aligned_bands)
    ):
        bands = cast(list[_multiband_write.BandInput], list(aligned_bands))
    else:
        if band_metadata is None or isinstance(band_metadata, (str, bytes)):
            raise ValidationError("registered MULTISPECTRAL result objects require band_metadata")
        metadata = list(band_metadata)
        if not all(isinstance(item, _multiband_write.BandInput) for item in metadata):
            raise ValidationError("registered MULTISPECTRAL band_metadata must contain BandInput values")
        result_bands = _registered_field(aligned_bands, "bands")
        has_result_shape = result_bands is not _MISSING
        output_values = _registered_sequence(result_bands if has_result_shape else aligned_bands, "bands")
        bands = _registered_result_band_inputs(output_values, metadata, grid_shape, has_result_shape=has_result_shape)

    if not 2 <= len(bands) <= 8:
        raise ValidationError("registered MULTISPECTRAL takes between two and eight bands")
    normalized = [replace(band, scale_factor=1.0, add_offset=0.0, fill_value=float("nan")) for band in bands]
    pixels = _multiband_write._pixels(normalized)
    if any(array.dtype.name != "float32" for array in pixels):
        raise ValidationError("registered MULTISPECTRAL bands must contain float32 physical values")
    if list(pixels[0].shape) != list(grid_shape):
        raise ValidationError("registered MULTISPECTRAL band dimensions disagree with grid.shape")
    return normalized


def _registered_transforms(fragment: object, reference_band_id: str) -> tuple[list[dict[str, object]], set[str]]:
    values = _registered_sequence(_registered_field(fragment, "transforms"), "transforms")
    transforms: list[dict[str, object]] = []
    band_ids: set[str] = set()
    for index, value in enumerate(values):
        band_id = _registered_nonempty_text(
            _registered_field(value, "bandId", "band_id"), f"transforms[{index}].bandId"
        )
        if not _BAND_ID.fullmatch(band_id) or band_id == reference_band_id or band_id in band_ids:
            raise ValidationError("registered MULTISPECTRAL transforms must name unique non-reference bands")
        band_ids.add(band_id)
        matrix = _registered_homography(_registered_field(value, "matrix"), f"transforms[{index}]")
        transforms.append({"bandId": band_id, "matrix": matrix})
    return transforms, band_ids


def _registered_fragment_fields(
    fragment: object,
    source_asset_id: str,
    path: str,
) -> tuple[dict[str, object], str, list[int], set[str]]:
    fragment_path = _registered_field(fragment, "path")
    if fragment_path is not _MISSING and fragment_path != path:
        raise ValidationError("registered MULTISPECTRAL path disagrees with record_fragment.path")
    declared_source = _registered_field(fragment, "derivedFrom", "derived_from")
    if declared_source is not _MISSING and declared_source != source_asset_id:
        raise ValidationError("registered MULTISPECTRAL derivedFrom must match source_asset_id")

    reference_band_id = _registered_nonempty_text(
        _registered_field(fragment, "referenceBandId", "reference_band_id"), "referenceBandId"
    )
    if not _BAND_ID.fullmatch(reference_band_id):
        raise ValidationError("registered MULTISPECTRAL referenceBandId has invalid band id syntax")
    grid_shape, grid_transform, valid_region = _registered_grid(fragment)
    resampling = _registered_field(fragment, "resampling")
    if resampling not in ("nearest", "bilinear", "cubic"):
        raise ValidationError("registered MULTISPECTRAL resampling must be nearest, bilinear or cubic")
    aligner = _registered_field(fragment, "aligner")
    aligner_fields = {
        "operation": _registered_nonempty_text(_registered_field(aligner, "operation"), "aligner.operation"),
        "policyVersion": _registered_nonempty_text(
            _registered_field(aligner, "policyVersion", "policy_version"), "aligner.policyVersion"
        ),
    }
    transforms, transformed_ids = _registered_transforms(fragment, reference_band_id)
    return (
        {
            "referenceBandId": reference_band_id,
            "grid": {"shape": grid_shape, "transform": grid_transform},
            "resampling": resampling,
            "validRegion": valid_region,
            "aligner": aligner_fields,
            "transforms": transforms,
        },
        reference_band_id,
        grid_shape,
        transformed_ids,
    )


def _registered_profile_declaration(
    fragment: object,
    profile: Mapping[str, object] | None,
    path: str,
) -> dict[str, str] | None:
    fragment_profile = _registered_field(fragment, "profile")
    if profile is not None and fragment_profile is not _MISSING:
        if _registered_profile(profile) != _registered_profile(fragment_profile):
            raise ValidationError("registered MULTISPECTRAL profile disagrees with record_fragment.profile")
    if path == "camera-metadata":
        if profile is not None or fragment_profile is not _MISSING:
            raise ValidationError("registered MULTISPECTRAL camera-metadata path does not take a profile")
        return None
    profile_value = profile if profile is not None else fragment_profile
    if profile_value is _MISSING:
        raise ValidationError("registered MULTISPECTRAL manual-profile path requires profile")
    return _registered_profile(profile_value)


def _registered_multispectral_declaration(
    source_asset_id: str,
    aligned_bands: object,
    *,
    record_fragment: object | None,
    path: str,
    profile: Mapping[str, object] | None,
    band_metadata: Sequence[_multiband_write.BandInput] | None,
) -> tuple[list[_multiband_write.BandInput], dict[str, object]]:
    if not isinstance(source_asset_id, str) or not _looks_like_uuid(source_asset_id):
        raise ValidationError("source_asset_id must be a media asset UUID")
    if path not in ("camera-metadata", "manual-profile"):
        raise ValidationError("registered MULTISPECTRAL path must be camera-metadata or manual-profile")
    if record_fragment is None:
        record_fragment = _registered_field(aligned_bands, "recordFragment", "record_fragment")
    if record_fragment is _MISSING:
        raise ValidationError("registered MULTISPECTRAL record_fragment is required")

    fields, reference_band_id, grid_shape, transformed_ids = _registered_fragment_fields(
        record_fragment, source_asset_id, path
    )
    bands = _registered_band_inputs(aligned_bands, band_metadata, grid_shape)
    band_ids = [band.id for band in bands]
    if any(not _BAND_ID.fullmatch(band_id) for band_id in band_ids) or len(set(band_ids)) != len(band_ids):
        raise ValidationError("registered MULTISPECTRAL bands must have unique valid band ids")
    if reference_band_id not in band_ids or transformed_ids != set(band_ids) - {reference_band_id}:
        raise ValidationError("registered MULTISPECTRAL transforms must cover every non-reference band")

    declaration: dict[str, object] = {"state": "registered", "path": path, "derivedFrom": source_asset_id, **fields}
    profile_fields = _registered_profile_declaration(record_fragment, profile, path)
    if profile_fields is not None:
        declaration["profile"] = profile_fields
    return bands, declaration


def _registered_wire_mapping(value: object, label: str) -> dict[str, object]:
    if isinstance(value, BaseModel):
        return cast(dict[str, object], value.model_dump(by_alias=True, exclude_none=True))
    if isinstance(value, Mapping):
        return dict(value)
    raise ValidationError(f"registered MULTISPECTRAL source {label} record is invalid")


def _registered_inherited_interpretation(
    bands: Sequence[_multiband_write.BandInput], source_provenance: object
) -> list[dict[str, object]]:
    source_interpretation = _registered_field(source_provenance, "bandInterpretation", "band_interpretation")
    record = _registered_field(source_interpretation, "record")
    if record is _MISSING:
        record = source_interpretation
    source_bands = _registered_field(record, "bands")
    if source_bands is _MISSING or source_bands is None:
        raise ValidationError("source MULTISPECTRAL asset has no band interpretation record; pass interpretation=")

    by_id: dict[str, dict[str, object]] = {}
    for entry in _registered_sequence(source_bands, "source band interpretation"):
        declared = _registered_wire_mapping(entry, "band interpretation")
        band_id = declared.get("bandId")
        if not isinstance(band_id, str) or band_id in by_id:
            raise ValidationError("source MULTISPECTRAL band interpretation has invalid or duplicate band ids")
        by_id[band_id] = declared

    inherited: list[dict[str, object]] = []
    for band in bands:
        if band.id not in by_id:
            raise ValidationError(f"source band interpretation is missing aligned band '{band.id}'")
        inherited.append(by_id[band.id])
    return inherited


def _registered_inherited_normalization(source_provenance: object) -> dict[str, object] | None:
    source_normalization = _registered_field(source_provenance, "normalization")
    record = _registered_field(source_normalization, "record")
    if record is _MISSING or record is None:
        return None
    inherited = _registered_wire_mapping(record, "normalization")
    inherited.pop("layout", None)
    return inherited


def _validate_registered_normalization(
    normalization: Mapping[str, object] | None,
    radiometric_level: str,
    calibration: Mapping[str, object] | None,
) -> None:
    if normalization is None:
        if radiometric_level != "raw" or calibration is not None:
            raise ValidationError(
                f"registered MULTISPECTRAL {radiometric_level} upload requires source normalization or normalization="
            )
        return
    processing_level = _registered_field(normalization, "processingLevel", "processing_level")
    if processing_level != radiometric_level:
        raise ValidationError(f"normalization processingLevel must match radiometric_level {radiometric_level!r}")


def _registered_provenance_declarations(
    bands: Sequence[_multiband_write.BandInput],
    radiometric_level: str,
    calibration: Mapping[str, object] | None,
    source_provenance: object,
    *,
    normalization: Mapping[str, object] | None,
    interpretation: Sequence[Mapping[str, object]] | None,
) -> tuple[Mapping[str, object] | None, Sequence[Mapping[str, object]] | None]:
    if interpretation is None:
        interpretation = _registered_inherited_interpretation(bands, source_provenance)
    if normalization is None:
        normalization = _registered_inherited_normalization(source_provenance)
    _validate_registered_normalization(normalization, radiometric_level, calibration)
    return normalization, interpretation


@dataclass(frozen=True, slots=True)
class _PreparedArray:
    modality: str
    root: Path
    preview: Path
    reservation: dict[str, object]
    completion: dict[str, object]


def _prepare_array(
    modality: str,
    data: object,
    directory: Path,
    session: str,
    extras: Mapping[str, object],
    descriptor: Mapping[str, object],
    declarations: Mapping[str, object] | None = None,
) -> _PreparedArray:
    """Write and verify the local store; build both request bodies (no network)."""

    root = directory / f"{modality.lower()}.zarr"
    metadata: dict[str, object] = {}
    channels = 1
    if modality == "MULTISPECTRAL":
        preview, width, height, dtype, file_size, media_descriptor = _multiband_write.prepare_multispectral(
            cast("Sequence[_multiband_write.BandInput]", data),
            root,
            radiometric_level=cast("str | None", descriptor["radiometric_level"]),
            calibration=cast("Mapping[str, object] | None", descriptor["calibration"]),
        )
        channels = len(cast("Sequence[object]", data))
        metadata = {"metadata": {"mediaDescriptor": media_descriptor}}
    elif modality == "DEPTH":
        preview, scalar, width, height, dtype, file_size = _depth.prepare_depth(
            data,
            root,
            unit=cast("str | None", descriptor["unit"]),
            scale=cast("float | None", descriptor["scale"]),
            offset=cast("float | None", descriptor["offset"]),
            no_data=cast("float | None", descriptor["no_data"]),
            display_range=cast("tuple[float, float] | None", descriptor["display_range"]),
            colormap=cast("str | None", descriptor["colormap"]),
            intrinsics=cast("Mapping[str, float] | None", descriptor["intrinsics"]),
            source_sensor=cast("str | None", descriptor["source_sensor"]),
        )
        metadata = {"metadata": {"scalarFields": {"depth": scalar}}}
    else:
        # Native THERMAL: Hub stamps the policy descriptor and refuses a client one.
        preview, width, height, dtype, file_size = _depth.prepare_thermal(data, root)
    preview_size = preview.stat().st_size
    reservation: dict[str, object] = {
        "captureSessionId": session,
        "modality": modality,
        "fileName": root.name,
        "contentType": "application/x-zarr",
        "fileSizeBytes": file_size,
        "thumbnailFileName": preview.name,
        "thumbnailContentType": "image/jpeg",
        "thumbnailFileSizeBytes": preview_size,
        "format": "zarr-v3",
        **extras,
    }
    completion: dict[str, object] = {
        "width": width,
        "height": height,
        "depth": 1,
        "channels": channels,
        "dataType": dtype,
        **metadata,
        "thumbnailFileSizeBytes": preview_size,
        "thumbnailContentType": "image/jpeg",
        **(declarations or {}),
    }
    return _PreparedArray(modality, root, preview, reservation, completion)


def _array_result(payload: object, reserved_id: str, modality: str) -> ArrayUploadResult:
    if not isinstance(payload, Mapping):
        raise ValidationError(f"Hub returned an invalid {modality} completion")
    identifier = payload.get("mediaAssetId")
    success = payload.get("success")
    message = payload.get("message")
    if identifier != reserved_id or success is not True or not isinstance(message, str):
        raise ValidationError(f"Hub returned an invalid {modality} completion")
    return ArrayUploadResult(media_asset_id=reserved_id, success=True, message=message)


def _array_reservation(payload: object, modality: str) -> Mapping[str, object]:
    invalid = f"Hub returned an invalid {modality} upload reservation"
    if not isinstance(payload, Mapping):
        raise ValidationError(invalid)
    if not isinstance(payload.get("mediaAssetId"), str) or not payload["mediaAssetId"]:
        raise ValidationError(invalid)
    if not isinstance(payload.get("thumbnailUploadUrl"), str) or not payload["thumbnailUploadUrl"]:
        raise ValidationError(invalid)
    return cast(Mapping[str, object], payload)


@contextlib.contextmanager
def _upload_source(path: Path) -> Iterator[tuple[BinaryIO, int]]:
    """Open an image upload source once, before its reservation, and yield it with its ``fstat`` size.

    The reserved size and the PUT bytes both come from this descriptor, so replacing the path afterwards
    cannot change what is uploaded. A symlink is followed once, here; ``O_NONBLOCK`` lets a FIFO reach the
    regular-file check instead of blocking the open.
    """

    refused = f"upload file must be a readable, non-empty regular file: {path}"
    try:
        handle = open(path, "rb", opener=lambda name, flags: os.open(name, flags | getattr(os, "O_NONBLOCK", 0)))
    except OSError:
        raise ValidationError(refused) from None
    with handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_size <= 0:
            raise ValidationError(refused)
        yield handle, opened.st_size


def _image_upload_body(
    image: Path,
    thumbnail: Path,
    image_size: int,
    thumbnail_size: int,
    *,
    session: str,
    width: int,
    height: int,
    modality: str,
    spot: str | None,
    device: str | None,
) -> tuple[dict[str, object], str, str]:
    """The reservation body; the sizes come from the open sources (:func:`_upload_source`), never the paths."""

    if not session or width <= 0 or height <= 0:
        raise ValidationError("upload requires a capture session and positive width and height")
    image_type = mimetypes.guess_type(image.name)[0]
    thumbnail_type = mimetypes.guess_type(thumbnail.name)[0]
    if (
        image_type is None
        or thumbnail_type is None
        or not image_type.startswith("image/")
        or not thumbnail_type.startswith("image/")
    ):
        raise ValidationError("upload files must have recognized image extensions")
    body: dict[str, object] = {
        "captureSessionId": session,
        "modality": modality,
        "fileName": image.name,
        "contentType": image_type,
        "fileSizeBytes": image_size,
        "thumbnailFileName": thumbnail.name,
        "thumbnailContentType": thumbnail_type,
        "thumbnailFileSizeBytes": thumbnail_size,
    }
    if spot is not None:
        body["spotId"] = spot
    if device is not None:
        body["deviceId"] = device
    return body, image_type, thumbnail_type


def _looks_like_uuid(value: str) -> bool:
    return (
        re.fullmatch(
            r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
            r"|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)",
            value,
        )
        is not None
    )


def _parse_model[T: BaseModel](payload: object, model: type[T]) -> T:
    if isinstance(payload, model):
        return payload
    return model.model_validate(payload)
