"""Value of a setpoint curve at a moment: the pure function a device program can call locally.

The curve shape is the one the Hub accepts in a rule action (`profile.mode == "curve"`) and the
agent runs. This module only evaluates it: no scheduler, no clock and no hardware loop. When to
start the curve and how often to evaluate it stay with the caller's own program. Axis range and
the temperature rate ceiling are checked by the device that advertises them, not here.
"""

from __future__ import annotations

import math
from typing import Literal

CurveShape = Literal["linear", "halfCosine"]


def setpoint_curve_value(
    shape: CurveShape,
    start_value: float,
    end_value: float,
    duration_secs: float,
    elapsed_secs: float,
) -> float:
    """Return the curve's value `elapsed_secs` after it started.

    `linear` moves at a constant slope; `halfCosine` follows `0.5 - 0.5 * cos(pi * x)` (x = the
    fraction of the duration), so it starts and ends flat. Before the start (negative elapsed time)
    the value is `start_value`; once `elapsed_secs` passes `duration_secs` it is `end_value`.

    Raises `ValueError` for an unknown shape, a value or elapsed time that is not finite, or a
    duration of zero or less.
    """
    if shape not in ("linear", "halfCosine"):
        raise ValueError(f"unknown curve shape: {shape!r}")
    for name, number in (
        ("start_value", start_value),
        ("end_value", end_value),
        ("duration_secs", duration_secs),
        ("elapsed_secs", elapsed_secs),
    ):
        if not math.isfinite(number):
            raise ValueError(f"{name} must be a finite number")
    if duration_secs <= 0:
        raise ValueError("duration_secs must be greater than zero")

    if elapsed_secs <= 0:
        return float(start_value)
    if elapsed_secs >= duration_secs:
        return float(end_value)
    fraction = elapsed_secs / duration_secs
    progress = fraction if shape == "linear" else 0.5 - 0.5 * math.cos(math.pi * fraction)
    return start_value + (end_value - start_value) * progress
