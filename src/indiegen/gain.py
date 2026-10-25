"""The one conversion from a level in the Plan to a linear gain.

Every level in the Plan is an integer number of millibels - the SI millibel,
one thousandth of a decibel - and every level in the renderer is a linear
multiplier. The two numbers that define the unit live here, once, and both
conversions are derived from them: a decibel is ``20 * log10`` of a gain, and
a millibel is a thousandth of a decibel, so a level in millibels is
``10 ** (millibels / 20000)``. The conversion lives here, once, because a
renderer that spells it out per stage is a renderer where one stage can quietly
disagree with the others.
"""

from __future__ import annotations

import math

import numpy as np

# The unit, defined once. A millibel is 1/1000 dB and a dB is 20 * log10 of a
# gain; the two conversions below are derived from these two numbers and never
# spell the arithmetic out again.
MILLIBELS_PER_DECIBEL: int = 1000
DECIBEL_EXPONENT: float = 20.0


def millibels_to_gain(millibels: float) -> float:
    """A level in millibels, as a linear gain."""
    return math.pow(10.0, millibels / (DECIBEL_EXPONENT * MILLIBELS_PER_DECIBEL))


def millibels_to_gain_array(millibels: np.ndarray) -> np.ndarray:
    """The same conversion, over an array of levels."""
    return np.power(10.0, millibels / (DECIBEL_EXPONENT * MILLIBELS_PER_DECIBEL))


def decibels_to_gain(decibels: float) -> float:
    """A level in decibels, as a linear gain."""
    return math.pow(10.0, decibels / DECIBEL_EXPONENT)


def unity_block(count: int) -> np.ndarray:
    """A gain block of ``count`` frames, everywhere at unity.

    Every duck and envelope starts from "no gain change" and carves from
    there; the starting value and its float64 dtype live here, once.
    """
    return np.ones(count, dtype=np.float64)
