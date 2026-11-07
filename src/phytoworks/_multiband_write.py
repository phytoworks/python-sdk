"""Write a local Zarr v3 ``bands.v1`` store for ``upload_array("MULTISPECTRAL", ...)``.

The ordered :class:`BandInput` list is the only authority on band order and meaning. The descriptor it yields is
validated by the reader's own validator (``_multiband``) and the written store is reopened through the reader's
admission before anything is reserved, so the SDK never uploads a store its own reader would refuse.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from . import _depth, _multiband, _zarr_storage
from .errors import ValidationError

if TYPE_CHECKING:
    import numpy as np

_LEVELS = ("raw", "radiance", "reflectance")
_WAVELENGTH_UNITS = {"nm": 1000.0, "um": 1.0}
_CALIBRATION_KEYS = {"method", "version", "referenceSha256"}
_DTYPES = ("uint16", "float32")


@dataclass(frozen=True, slots=True)
class BandInput:
    """One band: a 2D ``uint16`` or ``float32`` array and what it measures.

    ``center_wavelength`` and ``fwhm`` are in ``wavelength_unit`` (``"nm"`` or ``"um"``; there is no default, so a
    wavelength is never read in the wrong unit); they are stored in micrometres. ``scale_factor``/``add_offset``
    decode a raw value to physical units; ``fill_value`` marks no-data and is compared before scaling.
    ``units`` is ``"1"`` (raw counts and reflectance) or ``"W m-2 sr-1 m-1"`` (radiance, already per metre: the SDK
    does not convert from per-nanometre radiance).
    """

    id: str
    name: str
    array: object
    center_wavelength: float
    wavelength_unit: str
    fill_value: float | int | str
    fwhm: float | None = None
    common_name: str | None = None
    scale_factor: float = 1.0
    add_offset: float = 0.0
    units: str = "1"
    standard_name: str | None = None


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"MULTISPECTRAL {label} must be a finite number")
    return float(value)


def _to_micrometres(value: object, unit: str, label: str) -> float:
    if unit not in _WAVELENGTH_UNITS:
        raise ValidationError("MULTISPECTRAL wavelength_unit must be 'nm' or 'um'")
    return _number(value, label) / _WAVELENGTH_UNITS[unit]


def _fill_value(value: object, dtype: str, band_id: str) -> float | int | str:
    if isinstance(value, bool):
        raise ValidationError(f"MULTISPECTRAL band {band_id!r} fill_value must be a number or NaN")
    if isinstance(value, float) and math.isnan(value):
        if dtype != "float32":
            raise ValidationError(f"MULTISPECTRAL band {band_id!r} NaN fill_value needs a float32 array")
        return "NaN"
    if isinstance(value, str):
        raise ValidationError(f"MULTISPECTRAL band {band_id!r} fill_value must be a number or NaN")
    number = _number(value, f"band {band_id!r} fill_value")
    if dtype == "uint16":
        if number != int(number) or not 0 <= number <= 65_535:
            raise ValidationError(f"MULTISPECTRAL band {band_id!r} fill_value does not fit uint16")
        return int(number)
    if struct.unpack("f", struct.pack("f", number))[0] != number:
        raise ValidationError(f"MULTISPECTRAL band {band_id!r} fill_value is not exactly a float32")
    return number


def _band_descriptor(band: BandInput, dtype: str) -> dict[str, object]:
    descriptor: dict[str, object] = {
        "id": band.id,
        "name": band.name,
        "centerWavelengthUm": _to_micrometres(band.center_wavelength, band.wavelength_unit, "center_wavelength"),
        "scale_factor": _number(band.scale_factor, "scale_factor"),
        "add_offset": _number(band.add_offset, "add_offset"),
        "_FillValue": _fill_value(band.fill_value, dtype, band.id),
        "units": band.units,
    }
    if band.fwhm is not None:
        descriptor["fwhmUm"] = _to_micrometres(band.fwhm, band.wavelength_unit, "fwhm")
    if band.common_name is not None:
        descriptor["eo:common_name"] = band.common_name
    if band.standard_name is not None:
        descriptor["standard_name"] = band.standard_name
    return descriptor


def _calibration(calibration: Mapping[str, object] | None) -> dict[str, object] | None:
    if calibration is None:
        return None
    if not isinstance(calibration, Mapping) or set(calibration) - _CALIBRATION_KEYS:
        raise ValidationError("MULTISPECTRAL calibration takes only method, version and referenceSha256")
    return {key: value for key, value in calibration.items() if value is not None}


def build_descriptor(
    bands: Sequence[BandInput], dtype: str, radiometric_level: str, calibration: Mapping[str, object] | None
) -> dict[str, object]:
    """The ``bands.v1`` media descriptor for ``bands`` in the given order, validated by the reader's validator."""

    if radiometric_level not in _LEVELS:
        raise ValidationError(f"MULTISPECTRAL radiometric_level must be one of {', '.join(_LEVELS)}")
    descriptor: dict[str, object] = {
        "version": 1,
        "layout": "bands.v1",
        "representation": "multiband",
        "radiometricLevel": radiometric_level,
        "bands": [_band_descriptor(band, dtype) for band in bands],
    }
    checked = _calibration(calibration)
    if checked is not None:
        descriptor["calibration"] = checked
    return _multiband.validate_media_descriptor(descriptor, data_type=dtype)


def _pixels(bands: Sequence[BandInput]) -> list[np.ndarray]:
    import numpy as np

    if (
        isinstance(bands, (str, bytes))
        or not isinstance(bands, Sequence)
        or not all(isinstance(band, BandInput) for band in bands)
    ):
        raise ValidationError("MULTISPECTRAL data must be an ordered list of BandInput")
    if not 2 <= len(bands) <= 8:
        raise ValidationError("MULTISPECTRAL takes between two and eight bands")
    arrays = [np.asarray(band.array) for band in bands]
    if any(array.dtype.name not in _DTYPES for array in arrays):
        raise ValidationError("MULTISPECTRAL band arrays must be uint16 or float32; convert them explicitly first")
    if any(array.dtype != arrays[0].dtype for array in arrays):
        raise ValidationError("MULTISPECTRAL band arrays must share one dtype")
    if any(array.ndim != 2 or array.size == 0 for array in arrays):
        raise ValidationError("MULTISPECTRAL bands must be non-empty 2D arrays")
    if any(array.shape != arrays[0].shape for array in arrays):
        raise ValidationError("MULTISPECTRAL bands must share one shape")
    return arrays


def _root_attributes(descriptor: dict[str, object]) -> dict[str, object]:
    """The root group's STAC fields, which the reader compares with the frozen descriptor."""

    root_bands = []
    for band in cast("list[dict[str, object]]", descriptor["bands"]):
        entry: dict[str, object] = {
            "name": band["id"],
            "description": band["name"],
            "eo:center_wavelength": band["centerWavelengthUm"],
        }
        if "eo:common_name" in band:
            entry["eo:common_name"] = band["eo:common_name"]
        if "fwhmUm" in band:
            entry["eo:full_width_half_max"] = band["fwhmUm"]
        root_bands.append(entry)
    attributes: dict[str, object] = {"bands": root_bands, "pws:radiometric_level": descriptor["radiometricLevel"]}
    if "calibration" in descriptor:
        attributes["calibration"] = descriptor["calibration"]
    return attributes


def _write_store(root: Path, descriptor: dict[str, object], arrays: list[np.ndarray]) -> None:
    import numpy as np
    import zarr
    from zarr.core.common import JSON

    group = zarr.open_group(
        str(root), mode="w", zarr_format=3, attributes=cast("dict[str, JSON]", _root_attributes(descriptor))
    )
    bands_group = group.create_group("bands")
    for band, pixels in zip(cast("list[dict[str, object]]", descriptor["bands"]), arrays, strict=True):
        cf = {
            key: band[key]
            for key in ("scale_factor", "add_offset", "_FillValue", "units", "standard_name")
            if key in band
        }
        # Uncompressed single chunk: Hub admits no compressor for user stores.
        bands_group.create_array(
            cast(str, band["id"]),
            data=pixels,
            chunks=pixels.shape,
            compressors=None,
            fill_value=np.nan if band["_FillValue"] == "NaN" else band["_FillValue"],
            dimension_names=("y", "x"),
            attributes=cast("dict[str, JSON]", cf),
        )


def _verify_store(root: Path, descriptor: dict[str, object], arrays: list[np.ndarray]) -> None:
    """Reopen the written store through the reader's admission and compare every band byte for byte."""

    import numpy as np

    try:
        stored = _multiband._validate_store(root, descriptor)
        _multiband._inspect_store_members(root, stored)
        for band, pixels in zip(cast("list[dict[str, object]]", descriptor["bands"]), arrays, strict=True):
            reopened = np.asarray(_zarr_storage.open_bounded_array(root, f"bands/{band['id']}")[:])
            if reopened.dtype != pixels.dtype or not np.array_equal(
                reopened, pixels, equal_nan=pixels.dtype.kind == "f"
            ):
                raise ValidationError("MULTISPECTRAL local Zarr verification failed")
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("MULTISPECTRAL local Zarr verification failed") from None


def _write_preview(first: dict[str, object], pixels: np.ndarray, thumbnail: Path) -> Path:
    """A grayscale preview of the first band's valid pixels (the full cube is the asset; this is a thumbnail)."""

    import numpy as np

    valid = np.isfinite(pixels) if pixels.dtype.kind == "f" else np.ones(pixels.shape, dtype=bool)
    if first["_FillValue"] != "NaN":
        valid &= pixels != first["_FillValue"]
    return _depth._write_preview(
        pixels, valid, cast(float, first["scale_factor"]), cast(float, first["add_offset"]), thumbnail
    )


def prepare_multispectral(
    bands: Sequence[BandInput],
    root: Path,
    *,
    radiometric_level: str | None,
    calibration: Mapping[str, object] | None,
) -> tuple[Path, int, int, str, int, dict[str, object]]:
    """Validate, write and reopen the store; return ``(preview, width, height, dtype, size, descriptor)``."""

    _depth._require_depth_extra("MULTISPECTRAL")
    arrays = _pixels(bands)
    if radiometric_level is None:
        raise ValidationError("MULTISPECTRAL requires radiometric_level")
    shape = arrays[0].shape
    dtype = arrays[0].dtype.name
    if _zarr_storage.store_decode_budget_violation((list(shape), dtype, list(shape)) for _ in bands) is not None:
        raise ValidationError("MULTISPECTRAL bands exceed the reader decode budget")
    descriptor = build_descriptor(bands, dtype, radiometric_level, calibration)
    _write_store(root, descriptor, arrays)
    _verify_store(root, descriptor, arrays)
    first = cast("list[dict[str, object]]", descriptor["bands"])[0]
    thumbnail = _write_preview(first, arrays[0], root.parent / "multispectral-preview.jpg")
    height, width = shape
    size = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    return thumbnail, width, height, dtype, size, descriptor
