"""Integer mixing shared by the compose PRNG and the master dither.

Both need a deterministic, stateless function of an integer and a counter. It
lives here, outside ``compose/`` and outside the render path, so that neither
boundary has to import the other.
"""

from __future__ import annotations

import numpy as np

MASK64: int = (1 << 64) - 1


def mix64(value: int) -> int:
    """SplitMix64's finaliser: a bijection on 64 bits."""
    z = value & MASK64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return (z ^ (z >> 31)) & MASK64


def mix64_array(values: np.ndarray) -> np.ndarray:
    """The same finaliser, over a whole array of counters."""
    with np.errstate(over="ignore"):
        z = values.astype(np.uint64)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))
