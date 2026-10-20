"""The bus: summing, and the pan law."""

from __future__ import annotations

import math


def pan_gains(pan_permille: int) -> tuple[float, float]:
    """Constant-power pan gains. A centred source lands at 0.707 on both sides."""
    theta = (pan_permille / 1000.0 + 1.0) * (math.pi / 4.0)
    return math.cos(theta), math.sin(theta)
