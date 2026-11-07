"""Local DEPTH and THERMAL Zarr preparation and scoped object upload.

Heavy optional dependencies stay inside these functions so the base SDK remains
usable without the ``zarr`` extra.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import math
import re
import threading
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
from typing import TYPE_CHECKING, cast

from . import _zarr_storage
from ._scalar_policy import ScalarFieldPolicy, depth_policy
from .errors import ValidationError

if TYPE_CHECKING:
    import numpy as np


_ZARR_MIN_VERSION = (3, 1, 4)
_ZARR_MAX_MAJOR = 4
_ZARR_REQUIRED_RANGE = f"zarr>={'.'.join(map(str, _ZARR_MIN_VERSION))},<{_ZARR_MAX_MAJOR}"


def _require_depth_extra(modality: str = "DEPTH") -> None:
    if any(importlib.util.find_spec(module) is None for module in ("boto3", "numpy", "zarr", "PIL")):
        raise ValidationError(f"{modality} requires the optional SDK extra: pip install phytoworks[zarr]") from None
    try:
        installed = tuple(int(part) for part in re.findall(r"\d+", importlib.metadata.version("zarr"))[:3])
    except importlib.metadata.PackageNotFoundError:
        installed = ()
    if not (_ZARR_MIN_VERSION <= installed and installed[0] < _ZARR_MAX_MAJOR):
        raise ValidationError(f"{modality} requires {_ZARR_REQUIRED_RANGE}; pip install phytoworks[zarr]") from None


def _array_path(policy: ScalarFieldPolicy) -> str:
    array_path = _zarr_storage.array_path_for_field("DEPTH", policy.field_name)
    if array_path is None:
        raise ValidationError("DEPTH policy has no Zarr array mapping")
    return array_path


def admit_download(root: Path, members: tuple[_zarr_storage.DownloadMember, ...]) -> None:
    """Admit DEPTH metadata and every listed chunk before fetching any chunk."""

    try:
        policy = depth_policy()
        array_name = _array_path(policy)
        document = _zarr_storage.bounded_array_metadata(root, array_name)
        if len(cast(list[int], document["shape"])) != 2 or document["data_type"] not in policy.allowed_dtypes:
            raise ValueError("unsupported DEPTH shape or dtype")
        for member in members:
            if member.relative.endswith("zarr.json"):
                continue
            _zarr_storage.validate_array_chunk(
                tuple(member.relative.removeprefix(array_name + "/").split("/")), member.expected_bytes, document
            )
    except ValidationError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        raise ValidationError("Downloaded DEPTH Zarr is invalid") from None


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def prepare_depth(  # noqa: C901 - validation, local Zarr proof, and preview share the same pixels
    array: object,
    root: Path,
    *,
    unit: str | None,
    scale: float | None,
    offset: float | None,
    no_data: float | None,
    display_range: tuple[float, float] | None,
    colormap: str | None,
    intrinsics: Mapping[str, float] | None,
    source_sensor: str | None,
) -> tuple[Path, dict[str, object], int, int, str, int]:
    """Validate, write, and reopen a single 2D Zarr v3 depth array."""

    _require_depth_extra()
    import numpy as np
    import zarr

    policy = depth_policy()
    pixels = np.asarray(array)
    if pixels.ndim != 2 or pixels.size == 0 or pixels.dtype.name not in policy.allowed_dtypes:
        raise ValidationError("DEPTH requires a non-empty 2D array with a policy-supported dtype")
    resolved_unit = policy.default_unit if unit is None else unit
    resolved_scale = policy.default_scale if scale is None else scale
    resolved_offset = policy.default_offset if offset is None else offset
    resolved_no_data = policy.default_no_data if no_data is None else no_data
    if resolved_unit not in policy.allowed_units or not _finite_number(resolved_scale) or resolved_scale <= 0:
        raise ValidationError("DEPTH unit or scale is outside the versioned policy")
    if not _finite_number(resolved_offset):
        raise ValidationError("DEPTH offset must be finite")
    if resolved_no_data is not None and not _finite_number(resolved_no_data):
        raise ValidationError("DEPTH no_data must be finite or None")
    if (
        resolved_no_data is not None
        and pixels.dtype.name == "uint16"
        and (resolved_no_data != int(resolved_no_data) or resolved_no_data < 0 or resolved_no_data > 65535)
    ):
        raise ValidationError("DEPTH uint16 no_data must be an integer in [0, 65535]")
    if display_range is not None and (
        not isinstance(display_range, (tuple, list))
        or len(display_range) != 2
        or any(not _finite_number(value) for value in display_range)
        or display_range[0] >= display_range[1]
    ):
        raise ValidationError("DEPTH display_range must be increasing finite physical values")
    if colormap is not None and colormap not in policy.allowed_colormaps:
        raise ValidationError("DEPTH colormap is outside the versioned policy")
    if not isinstance(source_sensor, (str, type(None))) or (source_sensor is not None and not source_sensor.strip()):
        raise ValidationError("DEPTH source_sensor must be a non-empty string")
    metadata: dict[str, object] = {"version": policy.version}
    if unit is not None:
        metadata["unit"] = resolved_unit
    if scale is not None:
        metadata["scale"] = float(resolved_scale)
    if offset is not None:
        metadata["offset"] = float(resolved_offset)
    if no_data is not None:
        metadata["noData"] = int(no_data) if pixels.dtype.name == "uint16" else float(no_data)
    if display_range is not None:
        metadata["displayRange"] = [float(value) for value in display_range]
    if colormap is not None:
        metadata["colormap"] = colormap
    if intrinsics is not None:
        if (
            not isinstance(intrinsics, Mapping)
            or set(intrinsics) != {"fx", "fy", "cx", "cy"}
            or any(not _finite_number(value) for value in intrinsics.values())
            or intrinsics["fx"] <= 0
            or intrinsics["fy"] <= 0
        ):
            raise ValidationError("DEPTH intrinsics require finite fx/fy > 0 and finite cx/cy")
        metadata["intrinsics"] = {key: float(value) for key, value in intrinsics.items()}
    if source_sensor is not None:
        metadata["sourceSensor"] = source_sensor.strip()

    if (
        _zarr_storage.decode_budget_violation(
            list(pixels.shape),
            pixels.dtype.name,
            list(pixels.shape),
        )
        is not None
    ):
        raise ValidationError("DEPTH array exceeds the reader decode budget")

    group = zarr.open_group(str(root), mode="w", zarr_format=3)
    array_name = _array_path(policy)
    # Uncompressed: Hub admits no compressor for user stores.
    group.create_array(array_name, data=pixels, compressors=None)
    try:
        reopened = np.asarray(_zarr_storage.open_bounded_array(root, array_name)[:])
    except ValueError:
        raise ValidationError("DEPTH local Zarr verification failed") from None
    if (
        reopened.dtype != pixels.dtype
        or reopened.shape != pixels.shape
        or not np.array_equal(reopened, pixels, equal_nan=True)
    ):
        raise ValidationError("DEPTH local Zarr verification failed")

    valid = np.isfinite(pixels)
    if resolved_no_data is not None:
        valid &= pixels != resolved_no_data
    thumbnail = _write_preview(
        pixels, valid, float(resolved_scale), float(resolved_offset), root.parent / "depth-preview.jpg"
    )
    height, width = pixels.shape
    size = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    return thumbnail, metadata, width, height, pixels.dtype.name, size


def _write_preview(pixels: np.ndarray, valid: np.ndarray, scale: float, offset: float, thumbnail: Path) -> Path:
    """A 2-98 percentile grayscale JPEG of the valid physical values; invalid pixels stay black."""

    import numpy as np
    from PIL import Image

    preview = np.zeros(pixels.shape, dtype=np.uint8)
    if valid.any():
        physical = pixels[valid].astype(np.float64) * scale + offset
        low, high = np.percentile(physical, (2, 98))
        if high > low:
            preview[valid] = np.rint(np.clip((physical - low) * 255 / (high - low), 0, 255)).astype(np.uint8)
        else:
            preview[valid] = 127
    image = Image.fromarray(preview)
    image.thumbnail((512, 512))
    image.save(thumbnail, format="JPEG", quality=90, optimize=False, progressive=False)
    return thumbnail


# Native THERMAL encoding: the scalar policy's only dtype, scale and offset
# (``scalar-field-policy-v1.json``; ``tests/test_array_upload.py`` pins the copy).
# Stored raw is centi-kelvin, so uint16 spans -273.15..382.2 degC at 0.01 K.
THERMAL_SCALE = 0.01
THERMAL_OFFSET = -273.15
THERMAL_MIN_C = -273.15
THERMAL_MAX_C = 382.2


def prepare_thermal(array: object, root: Path) -> tuple[Path, int, int, str, int]:
    """Encode float degC as native uint16 centi-kelvin, write it, and reopen it.

    Integer input is refused rather than guessed at: an integer ``25`` could be
    degC or already centi-kelvin, and reading one as the other is off by ~300 K.
    """

    _require_depth_extra("THERMAL")
    import numpy as np
    import zarr

    pixels = np.asarray(array)
    if pixels.dtype.kind != "f":
        raise ValidationError("THERMAL requires a float array of degC; convert the input to float degC first")
    if pixels.ndim != 2 or pixels.size == 0:
        raise ValidationError("THERMAL requires a non-empty 2D array")
    if _zarr_storage.decode_budget_violation(list(pixels.shape), "uint16", list(pixels.shape)) is not None:
        raise ValidationError("THERMAL array exceeds the reader decode budget")
    celsius = pixels.astype(np.float64)
    if not np.isfinite(celsius).all():
        raise ValidationError("THERMAL values must be finite")
    # Bound the quantized raw, not the degC floats: float32(382.2) and
    # 65535 * 0.01 - 273.15 both sit a representation error above 382.2.
    quantized = np.rint((celsius - THERMAL_OFFSET) / THERMAL_SCALE)
    if quantized.min() < 0 or quantized.max() > np.iinfo(np.uint16).max:
        raise ValidationError(f"THERMAL values must lie within {THERMAL_MIN_C}..{THERMAL_MAX_C} degC")
    raw = quantized.astype(np.uint16)

    array_name = _zarr_storage.array_path_for_field("THERMAL", "temperature")
    if array_name is None:
        raise ValidationError("THERMAL has no Zarr array mapping")
    # Explicit intermediate group: Hub's native layout check wants every non-array node a group.
    parent, _, leaf = array_name.rpartition("/")
    group = zarr.open_group(str(root), mode="w", zarr_format=3).create_group(parent)
    # Uncompressed: Hub admits no compressor for user stores.
    group.create_array(leaf, data=raw, compressors=None)
    try:
        reopened = np.asarray(_zarr_storage.open_bounded_array(root, array_name)[:])
    except ValueError:
        raise ValidationError("THERMAL local Zarr verification failed") from None
    if reopened.dtype != raw.dtype or not np.array_equal(reopened, raw):
        raise ValidationError("THERMAL local Zarr verification failed")

    thumbnail = _write_preview(
        raw, np.ones(raw.shape, dtype=bool), THERMAL_SCALE, THERMAL_OFFSET, root.parent / "thermal-preview.jpg"
    )
    height, width = raw.shape
    size = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    return thumbnail, width, height, raw.dtype.name, size


def read_depth(root: Path) -> np.ndarray:
    """Read an SDK-downloaded Zarr v3 store without retaining temp files."""

    _require_depth_extra()
    import numpy as np

    try:
        policy = depth_policy()
        array = _zarr_storage.open_bounded_array(root, _array_path(policy))
        if array.ndim != 2 or array.dtype.name not in policy.allowed_dtypes:
            raise ValidationError("Downloaded DEPTH Zarr has unsupported shape or dtype")
        return np.asarray(array[:]).copy()
    except ValidationError as exc:
        raise ValidationError(f"Downloaded DEPTH Zarr is invalid ({exc})") from None
    except Exception:
        raise ValidationError("Downloaded DEPTH Zarr is invalid") from None


# Kept importable here: callers and tests address the DEPTH upload through this module.
_public_endpoint = _zarr_storage.public_endpoint


def upload_members(root: Path, reservation: Mapping[str, object], cancel: threading.Event | None = None) -> None:
    """PUT every local member under the issued prefix; retries keep that grant. See ``upload_store`` for ``cancel``."""

    _require_depth_extra()
    _zarr_storage.upload_store(root, reservation, cancel=cancel)
