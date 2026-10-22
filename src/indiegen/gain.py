"""The one conversion from a level in the Plan to a linear gain.

Every level in the Plan is an integer number of millibels, and every level in
the renderer is a linear multiplier. The exponent is 2000 because a millibel
is a hundredth of a decibel and a decibel is ``20 * log10`` of a gain, so
``10 ** (millibels / 2000)``. The conversion lives here, once, because a
renderer that spells it out per stage is a renderer where one stage can quietly
disagree with the others.
"""

from __future__ import annotations

import math

import numpy as np


def millibels_to_gain(millibels: float) -> float:
    """A level in millibels, as a linear gain."""
    return math.pow(10.0, millibels / 2000.0)


def millibels_to_gain_array(millibels: np.ndarray) -> np.ndarray:
    """The same conversion, over an array of levels."""
    return np.power(10.0, millibels / 2000.0)


def decibels_to_gain(decibels: float) -> float:
    """A level in decibels, as a linear gain."""
    return math.pow(10.0, decibels / 20.0)
