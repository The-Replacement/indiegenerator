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

    def snapshot(self) -> int:
        """The current state, to be restored with :meth:`restore`."""
        return self._state

    def restore(self, state: int) -> None:
        """Restore a state taken by :meth:`snapshot`."""
        self._state = state & MASK64


def seed_from_bytes(payload: bytes) -> int:
    """Derive a 64-bit seed from bytes, so the seed material is never guessed."""
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def groove_offsets(seed: int, count: int, depth: int) -> list[int]:
    """A deterministic, low-frequency offset sequence in ``[-depth, depth]``.

    The values come from a dedicated SplitMix64 stream - never the compose
    RNG, whose draw order the rest of the plan depends on - and are run
    through an integer one-pole so consecutive onsets drift instead of
    jittering like white noise. A hand pushes and pulls; white noise
    twitches. ``depth <= 0`` or ``count <= 0`` returns zeros, so the groove
    pass is a strict no-op and the default render cannot move because of
    this helper.
    """
    if depth <= 0 or count <= 0:
        return [0] * max(0, count)
    rng = SplitMix64(seed_from_bytes(f"groove:{seed}".encode("ascii")))
    out: list[int] = []
    value = 0
    for _ in range(count):
        target = rng.between(-1000, 1000)
        value = (3 * value + target) // 4
        out.append(max(-depth, min(depth, (value * depth) // 1000)))
    return out
