"""The only randomness in the program.

SplitMix64 over Python integers. It is deliberately *not* ``numpy.random``:
numpy's ``Generator`` stream is not contractually stable across numpy
releases (only the legacy ``RandomState`` carries a stability guarantee, and
that one is float-based), and the Plan contract is that ``plan_sha256`` is
bit-identical on every machine. Forty lines of integer arithmetic is the
cheapest way to keep that promise true across numpy upgrades.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TypeVar

from indiegen.mixing import MASK64, mix64

T = TypeVar("T")

GOLDEN_GAMMA: int = 0x9E3779B97F4A7C15


class SplitMix64:
    """A deterministic integer generator. Every value it yields is an ``int``."""

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & MASK64

    def next_u64(self) -> int:
        """The next 64-bit unsigned integer."""
        self._state = (self._state + GOLDEN_GAMMA) & MASK64
        return mix64(self._state)

    def next_int(self) -> int:
        """The next signed 64-bit integer."""
        value = self.next_u64()
        return value - (1 << 64) if value >= (1 << 63) else value

    def below(self, bound: int) -> int:
        """A uniform integer in ``[0, bound)``, free of modulo bias."""
        if bound <= 0:
            raise ValueError("bound must be positive")
        limit = (1 << 64) - ((1 << 64) % bound)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % bound

    def between(self, low: int, high: int) -> int:
        """A uniform integer in ``[low, high]``, both ends inclusive."""
        if high < low:
            raise ValueError("high must not be below low")
        return low + self.below(high - low + 1)

    def choice(self, items: Sequence[T]) -> T:
        """One element of a non-empty sequence, chosen uniformly."""
        if not items:
            raise ValueError("cannot choose from an empty sequence")
        return items[self.below(len(items))]


def seed_from_bytes(payload: bytes) -> int:
    """Derive a 64-bit seed from bytes, so the seed material is never guessed."""
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
