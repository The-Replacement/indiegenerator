"""Seeded TPDF dither.

A pure function of the seed and the sample index: no RNG object is ever
constructed, and no random source is imported. The master chain consumes the
Plan's integer dither seed and nothing else.
"""

from __future__ import annotations

import numpy as np

GOLDEN_GAMMA: int = 0x9E3779B97F4A7C15
TWO_POW_32: float = 4294967296.0


def tpdf(seed: int, count: int, start_index: int = 0) -> np.ndarray:
    """Triangular dither in LSB for a run of samples.

    Two independent uniform words are summed, which gives the triangular
    probability density that removes quantisation distortion at the cost of
    a little noise.
    """
    index = np.arange(start_index, start_index + count, dtype=np.uint64)
    state = np.uint64(seed & 0xFFFFFFFFFFFFFFFF) + index * np.uint64(GOLDEN_GAMMA)
    state = (state ^ (state >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    state = (state ^ (state >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    state = state ^ (state >> np.uint64(31))
    high = (state >> np.uint64(32)).astype(np.float64) / TWO_POW_32 - 0.5
    low = (state & np.uint64(0xFFFFFFFF)).astype(np.float64) / TWO_POW_32 - 0.5
    return high + low
