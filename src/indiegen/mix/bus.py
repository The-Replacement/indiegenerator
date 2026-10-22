"""The mix bus: the pan law and the per-instrument trims.

The bus is where the balance of a track is decided. Every level in it is an
integer number of millibels in the Plan, and the render turns them into
linear gains: the mix bus is data, and the renderer only multiplies.
"""

from __future__ import annotations

import math

from indiegen.plan import BusGain


def pan_gains(pan_permille: int) -> tuple[float, float]:
    """Constant-power pan gains. A centred source lands at 0.707 on both sides."""
    theta = (pan_permille / 1000.0 + 1.0) * (math.pi / 4.0)
    return math.cos(theta), math.sin(theta)


def bus_gains(gains: list[BusGain]) -> dict[str, float]:
    """The trim of every instrument kind, as a linear gain.

    A kind that is not in the list is not trimmed.
    """
    return {gain.kind: math.pow(10.0, gain.gain_millibels / 2000.0) for gain in gains}


def trim(lookup: dict[str, float], kind: str) -> float:
    """The trim of one instrument kind."""
    return lookup.get(kind, 1.0)
