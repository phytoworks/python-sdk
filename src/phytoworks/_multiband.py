"""Read-only support for the versioned Zarr `bands.v1` layout."""

from __future__ import annotations

import copy
import math
import os
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, cast

from . import _depth, _zarr_storage
from .errors import ValidationError

if TYPE_CHECKING:
    import numpy as np


_BAND_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}")
_ATTRIBUTE_KEYS = {"scale_factor", "add_offset", "_FillValue", "units", "standard_name"}
_UINT16_MAX = 65_535
_FLOAT32_MAX = 3.4028234663852886e38
# The shared Zod schema and worker validator count Unicode code points.
_LABEL_MAX_LENGTH = 128


@dataclass(frozen=True, slots=True)
class MultibandData:
    """Raw bands in descriptor order and their frozen asset interpretation."""

    raw_bands: dict[str, np.ndarray]
    descriptor: dict[str, object]

    def physical_band(self, band_id: str) -> np.ma.MaskedArray:
        """Decode one loaded band; `_FillValue` is compared before scaling."""

        raw = self.raw_bands.get(band_id)
        if raw is None:
            raise ValidationError(f"bands.v1 band id {band_id!r} was not selected")
        descriptors = cast(list[object], self.descriptor["bands"])
        band = next(
            (cast(dict[str, object], item) for item in descriptors if cast(dict[str, object], item)["id"] == band_id),
            None,
        )
        if band is None:
            raise ValidationError(f"bands.v1 band id {band_id!r} is not in the descriptor")

        import numpy as np

        # Retained raw arrays, float64 output, fill mask, and physical-range mask coexist.
        mask_buffers = 2
        decode_bytes = sum(array.nbytes for array in self.raw_bands.values()) + raw.size * (8 + mask_buffers)
        if decode_bytes > _zarr_storage.DECODE_MAX_BYTES:
            _fail("physical band is outside the decode budget (bytes)")
        fill_value = band["_FillValue"]
        mask = np.isnan(raw) if fill_value == "NaN" else raw == fill_value
        if raw.dtype.kind == "f" and fill_value != "NaN":
            np.logical_or(mask, np.isnan(raw), out=mask)
        values = raw.astype(np.float64)
        scale_factor = float(cast(Real, band["scale_factor"]))
        add_offset = float(cast(Real, band["add_offset"]))
        with np.errstate(over="ignore", invalid="ignore"):
            np.multiply(values, scale_factor, out=values)
            np.add(values, add_offset, out=values)
            invalid = np.isfinite(values)
            np.logical_not(invalid, out=invalid)
            np.logical_or(mask, invalid, out=mask)
            np.greater(values, _FLOAT32_MAX, out=invalid)
            np.logical_or(mask, invalid, out=mask)
            np.less(values, -_FLOAT32_MAX, out=invalid)
            np.logical_or(mask, invalid, out=mask)
        return np.ma.array(values, mask=mask, copy=False)


@dataclass(frozen=True, slots=True)
class _ArrayMetadata:
    band_id: str
    shape: tuple[int, int]
    data_type: str
    chunk_shape: tuple[int, int]


def _fail(message: str) -> NoReturn:
    raise ValidationError(f"bands.v1 {message}")


def bands_v1_physical_range_fits_float32(scale_factor: float, add_offset: float, data_type: str) -> bool:
    """Whether every raw value in this supported dtype unpacks within Float32 range."""

    raw_max: float
    if data_type == "uint16":
        raw_max = _UINT16_MAX
    elif data_type == "float32":
        raw_max = _FLOAT32_MAX
    else:
        return False

    try:
        scale_factor = float(scale_factor)
        add_offset = float(add_offset)
    except (OverflowError, TypeError, ValueError):
        return False

    return (
        math.isfinite(scale_factor)
        and math.isfinite(add_offset)
        and abs(scale_factor) * raw_max + abs(add_offset) <= _FLOAT32_MAX
    )


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _float32_fill(value: object) -> bool:
    if isinstance(value, str):
        return value == "NaN"
    if not _finite_number(value):
        return False
    try:
        number = float(cast(Real, value))
        return bool(struct.unpack("f", struct.pack("f", number))[0] == number)
    except (OverflowError, struct.error):
        return False


def _strict_mapping(value: object, required: set[str], optional: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        _fail(f"{label} must be an object")
    mapping = cast(Mapping[str, object], value)
    keys = set(mapping)
    if not required.issubset(keys) or keys - required - optional:
        _fail(f"{label} has missing or unsupported fields")
    return mapping


def _validate_band_labels(band: Mapping[str, object], band_id: str) -> None:
    for key in ("name", "eo:common_name", "standard_name"):
        if key in band and not _bounded_label(band[key]):
            _fail(f"band {band_id!r} {key} is invalid")


def _bounded_label(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= _LABEL_MAX_LENGTH


def _validate_band_values(band: Mapping[str, object], band_id: str) -> None:
    if not _finite_number(band["centerWavelengthUm"]) or cast(float, band["centerWavelengthUm"]) <= 0:
        _fail(f"band {band_id!r} centerWavelengthUm is invalid")
    if "fwhmUm" in band and (not _finite_number(band["fwhmUm"]) or cast(float, band["fwhmUm"]) <= 0):
        _fail(f"band {band_id!r} fwhmUm is invalid")
    if not _finite_number(band["scale_factor"]) or cast(float, band["scale_factor"]) <= 0:
        _fail(f"band {band_id!r} scale_factor is invalid")
    if not _finite_number(band["add_offset"]):
        _fail(f"band {band_id!r} CF numeric attributes are invalid")
    if not _float32_fill(band["_FillValue"]):
        _fail(f"band {band_id!r} _FillValue must be exactly representable as float32 or the native string 'NaN'")


def _validate_band(value: object, level: str) -> tuple[Mapping[str, object], str]:
    required = {"id", "name", "centerWavelengthUm", "scale_factor", "add_offset", "_FillValue", "units"}
    optional = {"eo:common_name", "fwhmUm", "standard_name"}
    band = _strict_mapping(value, required, optional, "band descriptor")
    raw_id = band["id"]
    if not isinstance(raw_id, str) or _BAND_ID.fullmatch(raw_id) is None:
        _fail("band id is invalid")
    band_id = raw_id
    _validate_band_labels(band, band_id)
    _validate_band_values(band, band_id)

    units = band["units"]
    expected_units = {
        "raw": "1",
        "radiance": "W m-2 sr-1 m-1",
        "reflectance": "1",
    }[level]
    if units != expected_units:
        _fail(f"band {band_id!r} units disagree with radiometricLevel")
    if level == "raw" and (
        cast(float, band["scale_factor"]) != 1 or cast(float, band["add_offset"]) != 0 or "standard_name" in band
    ):
        _fail(f"raw band {band_id!r} requires identity scaling and no standard_name")
    return band, band_id


def _validate_calibration(descriptor: Mapping[str, object], level: str) -> None:
    calibration = descriptor.get("calibration")
    if "calibration" in descriptor and calibration is None:
        _fail("calibration must be omitted or an object")
    if level in {"radiance", "reflectance"} and calibration is None:
        _fail("radiance and reflectance require calibration metadata")
    if calibration is None:
        return
    calibration_map = _strict_mapping(calibration, {"method", "version"}, {"referenceSha256"}, "calibration")
    for key in ("method", "version"):
        item = calibration_map[key]
        if not _bounded_label(item):
            _fail(f"calibration {key} is invalid")
    digest = calibration_map.get("referenceSha256")
    if "referenceSha256" in calibration_map and (not isinstance(digest, str) or _SHA256.fullmatch(digest) is None):
        _fail("calibration referenceSha256 is invalid")


def _validate_bands(value: object, level: str) -> None:
    if not isinstance(value, list) or not 2 <= len(value) <= 8:
        _fail("bands must contain between two and eight ordered bands")
    seen: set[str] = set()
    for item in value:
        _, band_id = _validate_band(item, level)
        if band_id in seen:
            _fail(f"duplicate band id {band_id!r}")
        seen.add(band_id)


def _validate_descriptor(value: object) -> dict[str, object]:
    descriptor = _strict_mapping(
        value,
        {"version", "layout", "representation", "bands", "radiometricLevel"},
        {"calibration"},
        "mediaDescriptor",
    )
    if type(descriptor["version"]) is not int or descriptor["version"] != 1:
        _fail("mediaDescriptor version is unsupported")
    if descriptor["layout"] != "bands.v1" or descriptor["representation"] != "multiband":
        _fail("mediaDescriptor version or layout is unsupported")
    level = descriptor["radiometricLevel"]
    if level not in ("raw", "radiance", "reflectance"):
        _fail("radiometricLevel is unsupported")
    level = cast(str, level)
    _validate_calibration(descriptor, level)
    _validate_bands(descriptor["bands"], level)
    return copy.deepcopy(dict(descriptor))


def validate_media_descriptor(
    value: object, *, band_id: str | None = None, data_type: str | None = None
) -> dict[str, object]:
    """Validate the frozen descriptor and optional dtype and band selection."""

    descriptor = _validate_descriptor(value)
    bands = [cast(dict[str, object], band) for band in cast(list[object], descriptor["bands"])]
    if data_type is not None and any(
        not bands_v1_physical_range_fits_float32(
            cast(float, band["scale_factor"]), cast(float, band["add_offset"]), data_type
        )
        for band in bands
    ):
        _fail("physical value range exceeds float32")
    band_ids = [cast(str, band["id"]) for band in bands]
    if band_id is not None and band_id not in band_ids:
        _fail(f"band id {band_id!r} is not in the descriptor")
    return descriptor


def _read_document(root: Path, relative: str) -> dict[str, object]:
    try:
        return _zarr_storage.read_metadata_document(root / relative)
    except ValidationError as exc:
        _fail(f"metadata document {relative!r} is invalid ({exc})")


def _group_attributes(root: Path, relative: str) -> Mapping[str, object]:
    document = _read_document(root, relative)
    if document.get("zarr_format") != 3 or document.get("node_type") != "group":
        _fail(f"{relative!r} is not a Zarr v3 group")
    if document.get("consolidated_metadata") is not None:
        _fail(f"{relative!r} consolidated group metadata is unsupported")
    _zarr_storage.validate_group_metadata(document)
    attributes = document.get("attributes", {})
    if not isinstance(attributes, Mapping):
        _fail(f"{relative!r} attributes are invalid")
    return cast(Mapping[str, object], attributes)


def _array_shape(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or not all(_positive_integer(extent) for extent in value):
        _fail(f"band {label!r} must be a non-empty 2D array")
    return cast(tuple[int, int], tuple(value))


def _array_chunk_shape(document: Mapping[str, object], band_id: str) -> tuple[int, int]:
    chunk_grid = document.get("chunk_grid")
    if not isinstance(chunk_grid, Mapping) or chunk_grid.get("name") != "regular":
        _fail(f"band {band_id!r} chunk grid is unsupported")
    configuration = chunk_grid.get("configuration")
    if not isinstance(configuration, Mapping):
        _fail(f"band {band_id!r} chunk grid is invalid")
    chunk_shape = _array_shape(configuration.get("chunk_shape"), band_id)
    key_encoding = document.get("chunk_key_encoding")
    encoding_configuration = key_encoding.get("configuration", {}) if isinstance(key_encoding, Mapping) else None
    if (
        not isinstance(key_encoding, Mapping)
        or key_encoding.get("name") != "default"
        or not isinstance(encoding_configuration, Mapping)
        or encoding_configuration.get("separator", "/") != "/"
        or document.get("storage_transformers") not in (None, [])
    ):
        _fail(f"band {band_id!r} chunk layout is unsupported")
    return chunk_shape


def _validate_cf_attributes(document: Mapping[str, object], band: Mapping[str, object], band_id: str) -> None:
    attributes = document.get("attributes")
    if not isinstance(attributes, Mapping):
        _fail(f"band {band_id!r} attributes are invalid")
    expected_keys = {key for key in _ATTRIBUTE_KEYS if key in band}
    if set(attributes) != expected_keys:
        _fail(f"band {band_id!r} CF attributes disagree with its descriptor")
    for key in expected_keys:
        actual = attributes[key]
        expected = band[key]
        if key in {"units", "standard_name"} or expected == "NaN":
            matches = isinstance(actual, str) and actual == expected
        else:
            matches = _finite_number(actual) and float(actual) == float(cast(Real, expected))
        if not matches:
            _fail(f"band {band_id!r} CF attribute {key!r} disagrees with its descriptor")


def _validate_fill_value(band: Mapping[str, object], band_id: str, data_type: str) -> None:
    fill_value = band["_FillValue"]
    if data_type == "uint16" and (
        not _finite_number(fill_value)
        or not 0 <= cast(float, fill_value) <= _UINT16_MAX
        or cast(float, fill_value) != int(cast(float, fill_value))
    ):
        _fail(f"band {band_id!r} _FillValue does not fit uint16")
    if data_type == "float32" and not _float32_fill(fill_value):
        _fail(f"band {band_id!r} _FillValue does not fit float32")


def _array_metadata(root: Path, band: Mapping[str, object], band_id: str) -> _ArrayMetadata:
    relative = f"bands/{band_id}/zarr.json"
    document = _read_document(root, relative)
    if document.get("zarr_format") != 3 or document.get("node_type") != "array":
        _fail(f"band {band_id!r} is not a Zarr v3 array")
    shape = _array_shape(document.get("shape"), band_id)
    data_type = document.get("data_type")
    if data_type not in ("uint16", "float32"):
        _fail(f"band {band_id!r} dtype is unsupported")
    dimensions = document.get("dimension_names")
    # Fixed [y, x]: a square array with swapped axes passes every shape check.
    if dimensions != ["y", "x"]:
        _fail(f"band {band_id!r} dimension names must be ['y', 'x']")
    chunk_shape = _array_chunk_shape(document, band_id)
    if not _zarr_storage.bounded_codecs(document.get("codecs"), cast(int, _zarr_storage.dtype_bytes(data_type))):
        _fail(f"band {band_id!r} codecs must contain only a bytes codec with explicit endian")
    _validate_cf_attributes(document, band, band_id)
    _validate_fill_value(band, band_id, cast(str, data_type))
    fill_value = document.get("fill_value")
    if (
        not _float32_fill(fill_value)
        or fill_value != band["_FillValue"]
        or (isinstance(fill_value, str) and data_type != "float32")
    ):
        _fail(f"band {band_id!r} storage fill_value disagrees with CF _FillValue")
    from zarr.core.common import JSON
    from zarr.core.metadata.v3 import ArrayV3Metadata

    # Parse every band's complete metadata, including bands omitted from the decode selection.
    # Only the admitted bytes codec is constructed here; no chunks or pixel buffers are loaded.
    try:
        ArrayV3Metadata.from_dict(cast(dict[str, JSON], document))
    except (ValueError, TypeError, KeyError):
        _fail(f"band {band_id!r} array metadata is invalid")
    return _ArrayMetadata(band_id, shape, cast(str, data_type), chunk_shape)


def _observed_band_ids(bands_root: Path, expected: set[str]) -> set[str]:
    observed: set[str] = set()
    try:
        with os.scandir(bands_root) as children:
            for child in children:
                if child.name == "zarr.json":
                    continue
                if child.is_symlink() or not child.is_dir(follow_symlinks=False):
                    _fail("bands group contains an unsupported member")
                if child.name not in expected or child.name in observed:
                    _fail("band paths are missing, extra, or duplicated")
                observed.add(child.name)
    except OSError:
        _fail("bands group cannot be listed")
    return observed


def _validate_band_arrays(
    root: Path, frozen_bands: list[dict[str, object]], expected_ids: list[str]
) -> list[_ArrayMetadata]:
    arrays: list[_ArrayMetadata] = []
    for band, band_id in zip(frozen_bands, expected_ids, strict=True):
        arrays.append(_array_metadata(root, band, band_id))
    first = arrays[0]
    if any(array.shape != first.shape for array in arrays[1:]):
        _fail("all bands must have the same 2D shape")
    if any(array.data_type != first.data_type for array in arrays[1:]):
        _fail("all bands must have one dtype")
    for band, array in zip(frozen_bands, arrays, strict=True):
        if not bands_v1_physical_range_fits_float32(
            cast(float, band["scale_factor"]), cast(float, band["add_offset"]), array.data_type
        ):
            _fail(f"band {array.band_id!r} physical value range exceeds float32")
    return arrays


def _validate_store(root: Path, descriptor: dict[str, object]) -> list[_ArrayMetadata]:
    if root.is_symlink() or not root.is_dir():
        _fail("store root must be a real directory")
    root_attributes = _group_attributes(root, "zarr.json")
    band_descriptors = cast(list[object], descriptor["bands"])
    frozen_bands = [cast(dict[str, object], band) for band in band_descriptors]
    _validate_root_interpretation(root_attributes, descriptor, frozen_bands)
    bands_root = root / "bands"
    if bands_root.is_symlink() or not bands_root.is_dir():
        _fail("bands group is missing or unsafe")
    _group_attributes(root, "bands/zarr.json")
    expected_ids = [cast(str, band["id"]) for band in frozen_bands]
    if _observed_band_ids(bands_root, set(expected_ids)) != set(expected_ids):
        _fail("band paths are missing, extra, or duplicated")
    arrays = _validate_band_arrays(root, frozen_bands, expected_ids)
    violation = _zarr_storage.store_decode_budget_violation(
        (array.shape, array.data_type, array.chunk_shape) for array in arrays
    )
    if violation is not None:
        _fail(f"store is outside the decode budget ({violation})")
    return arrays


def admit_download(
    root: Path, descriptor: dict[str, object], members: tuple[_zarr_storage.DownloadMember, ...]
) -> None:
    """Admit all metadata and listed chunk sizes before any remote chunk is fetched."""

    by_id = {array.band_id: array for array in _validate_store(root, descriptor)}
    for member in members:
        if member.relative.endswith("zarr.json"):
            continue
        _validate_chunk_member(tuple(member.relative.split("/")), member.expected_bytes, by_id)


def _validate_root_interpretation(
    attributes: Mapping[str, object], descriptor: dict[str, object], frozen_bands: list[dict[str, object]]
) -> None:
    if attributes.get("pws:radiometric_level") != descriptor["radiometricLevel"] or (
        ("calibration" in attributes) != ("calibration" in descriptor)
        or attributes.get("calibration") != descriptor.get("calibration")
    ):
        _fail("root radiometric level or calibration disagrees with mediaDescriptor")
    disk_bands = attributes.get("bands")
    if not isinstance(disk_bands, list) or len(disk_bands) != len(frozen_bands):
        _fail("root band order or descriptors disagree with mediaDescriptor")
    field_mapping = {
        "id": "name",
        "name": "description",
        "eo:common_name": "eo:common_name",
        "centerWavelengthUm": "eo:center_wavelength",
        "fwhmUm": "eo:full_width_half_max",
    }
    for disk_value, band in zip(disk_bands, frozen_bands, strict=True):
        disk_band = _strict_mapping(
            disk_value,
            {"name", "description", "eo:center_wavelength"},
            {"eo:common_name", "eo:full_width_half_max"},
            "root band",
        )
        for source, target in field_mapping.items():
            if (source in band) != (target in disk_band):
                _fail(f"root band {target!r} disagrees with mediaDescriptor")
            if source not in band:
                continue
            actual, expected = disk_band[target], band[source]
            if actual != expected or (source in {"centerWavelengthUm", "fwhmUm"} and not _finite_number(actual)):
                _fail(f"root band order or {target!r} disagrees with mediaDescriptor")


def _inspect_store_members(root: Path, arrays: list[_ArrayMetadata]) -> None:
    """Admit every physical member before selection or any Zarr decoder reads it."""

    by_id = {array.band_id: array for array in arrays}
    metadata_paths = {("zarr.json",), ("bands", "zarr.json")}
    metadata_paths.update(("bands", band_id, "zarr.json") for band_id in by_id)
    safe_root = root.resolve()
    directories = [root]
    members = metadata_documents = 0
    try:
        while directories:
            with os.scandir(directories.pop()) as entries:
                for entry in entries:
                    member = Path(entry.path)
                    if entry.is_symlink() or not member.resolve().is_relative_to(safe_root):
                        _fail("store member is unsafe or symlinked")
                    parts = member.relative_to(root).parts
                    if entry.is_dir(follow_symlinks=False):
                        _validate_member_directory(parts, by_id)
                        directories.append(member)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        _fail("store contains an unsupported member")
                    members += 1
                    metadata_documents += int(member.name == "zarr.json")
                    if (
                        members > _zarr_storage.USER_STORE_MAX_MEMBERS
                        or metadata_documents > _zarr_storage.USER_STORE_MAX_METADATA_DOCUMENTS
                    ):
                        _fail("store exceeds the member or metadata document limit")
                    if member.name == "zarr.json":
                        if parts not in metadata_paths:
                            _fail("store contains an unsupported metadata document")
                    else:
                        _validate_chunk_member(parts, entry.stat(follow_symlinks=False).st_size, by_id)
    except OSError:
        _fail("store members cannot be inspected safely")


def _validate_member_directory(parts: tuple[str, ...], by_id: dict[str, _ArrayMetadata]) -> None:
    if parts == ("bands",):
        return
    if len(parts) not in (2, 3, 4) or parts[0] != "bands" or parts[1] not in by_id:
        _fail("store contains an unsupported directory")
    if len(parts) >= 3 and parts[2] != "c":
        _fail("store contains an unsupported chunk directory")
    if len(parts) == 4:
        array = by_id[parts[1]]
        rows = -(-array.shape[0] // array.chunk_shape[0])
        if _zarr_storage.CHUNK_INDEX.fullmatch(parts[3]) is None or int(parts[3]) >= rows:
            _fail("store contains an out-of-grid chunk directory")


def _validate_chunk_member(parts: tuple[str, ...], size: int, by_id: dict[str, _ArrayMetadata]) -> None:
    if len(parts) != 5 or parts[0] != "bands" or parts[1] not in by_id or parts[2] != "c":
        _fail("store contains an unsupported chunk member")
    array = by_id[parts[1]]
    grid = [-(-extent // chunk) for extent, chunk in zip(array.shape, array.chunk_shape, strict=True)]
    if any(
        _zarr_storage.CHUNK_INDEX.fullmatch(index) is None or int(index) >= extent
        for index, extent in zip(parts[3:], grid, strict=True)
    ):
        _fail("store contains an out-of-grid chunk member")
    if size != math.prod(array.chunk_shape) * cast(int, _zarr_storage.dtype_bytes(array.data_type)):
        _fail("store contains a chunk with an invalid decoded size")


def read_multiband_store(
    root: Path,
    media_descriptor: object,
    *,
    band_id: str | None = None,
) -> MultibandData:
    """Validate and read all raw bands, or one explicitly selected band."""

    descriptor = validate_media_descriptor(media_descriptor, band_id=band_id)
    band_descriptors = cast(list[object], descriptor["bands"])
    band_ids = [cast(str, cast(dict[str, object], band)["id"]) for band in band_descriptors]

    _depth._require_depth_extra("bands.v1")
    import numpy as np

    arrays = _validate_store(root, descriptor)
    _inspect_store_members(root, arrays)
    selected_ids = band_ids if band_id is None else [band_id]
    selected = [array for array in arrays if array.band_id in selected_ids]

    raw_bands: dict[str, np.ndarray] = {}
    try:
        for array in selected:
            opened = _zarr_storage.open_bounded_array(root, f"bands/{array.band_id}")
            raw_bands[array.band_id] = np.asarray(opened[:])
    except ValidationError:
        raise
    except Exception:
        _fail("store is invalid")
    return MultibandData(raw_bands=raw_bands, descriptor=descriptor)
