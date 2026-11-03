"""Local scalar policy validation data projected from shared-types.

The JSON is generated and version-pinned; importing this module does not load
array or storage extras. Hub remains authoritative at upload completion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import cast


@dataclass(frozen=True, slots=True)
class ScalarFieldPolicy:
    version: int
    field_name: str
    zarr_array_name: str
    allowed_units: tuple[str, ...]
    allowed_dtypes: tuple[str, ...]
    allowed_colormaps: tuple[str, ...]
    default_unit: str
    default_scale: float
    default_offset: float
    default_no_data: float | None
    default_colormap: str


@cache
def _artifact() -> dict[str, object]:
    artifact = cast(
        dict[str, object],
        json.loads(files("phytoworks").joinpath("scalar-field-policy-v1.json").read_text(encoding="utf-8")),
    )
    if artifact["version"] != 1:
        raise ValueError("unsupported scalar policy artifact version")
    return artifact


def media_modalities() -> frozenset[str]:
    """Every media modality the Hub knows: the artifact's ``modalities`` keys (generated from ``MEDIA_MODALITY_PROFILES``)."""
    return frozenset(cast(dict[str, object], _artifact()["modalities"]))


@cache
def depth_policy() -> ScalarFieldPolicy:
    """Return the installed SDK's pinned DEPTH policy without network access."""
    artifact = _artifact()
    modalities = cast(dict[str, dict[str, object]], artifact["modalities"])
    values = modalities["DEPTH"]
    return ScalarFieldPolicy(
        version=1,
        field_name=cast(str, values["fieldName"]),
        zarr_array_name=cast(str, values["zarrArrayName"]),
        allowed_units=tuple(cast(list[str], values["allowedUnits"])),
        allowed_dtypes=tuple(cast(list[str], values["allowedDtypes"])),
        allowed_colormaps=tuple(cast(list[str], artifact["allowedColormaps"])),
        default_unit=cast(str, values["defaultUnit"]),
        default_scale=cast(float, values["defaultScale"]),
        default_offset=cast(float, values["defaultOffset"]),
        default_no_data=cast(float | None, values["defaultNoData"]),
        default_colormap=cast(str, values["defaultColormap"]),
    )
