"""The modes, and the scales they build.

A mode is a set of intervals from the root. The tables are the standard ones
BRIEF 6 names - Dorian, Phrygian, Mixolydian, Aeolian, whole-tone and
octatonic - and they live here rather than in a preset because they are
theory, not parameters: a lane declares WHICH modes it draws from, never
which notes they contain.

The relative modes are here for the same reason: T16 moves the harmonic
center among related modes, and the relative of a mode is a fact about the
modes, not about a track.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

MODE_INTERVALS: Mapping[str, tuple[int, ...]] = MappingProxyType(
    {
        "dorian": (0, 2, 3, 5, 7, 9, 10),
        "phrygian": (0, 1, 3, 5, 7, 8, 10),
        "lydian": (0, 2, 4, 6, 7, 9, 11),
        "mixolydian": (0, 2, 4, 5, 7, 9, 10),
        "aeolian": (0, 2, 3, 5, 7, 8, 10),
        "whole_tone": (0, 2, 4, 6, 8, 10),
        "octatonic": (0, 2, 3, 5, 6, 8, 9, 11),
    }
)

# The relative of a mode: the mode a minor third below, which shares its
# notes. Dorian and phrygian are relatives, mixolydian and dorian are
# relatives, lydian and mixolydian are relatives.
RELATIVE_MODES: Mapping[str, str] = MappingProxyType(
    {
        "dorian": "phrygian",
        "phrygian": "dorian",
        "lydian": "mixolydian",
        "mixolydian": "dorian",
        "aeolian": "lydian",
        "whole_tone": "whole_tone",
        "octatonic": "octatonic",
    }
)

# The relative minor sits a minor third below the root.
RELATIVE_INTERVAL: int = -3


def mode_scale(mode: str, root_midi: int, octaves: int = 2) -> list[int]:
    """The scale of a mode, from the root, over the given octaves.

    The root itself is included at the top, so the scale covers the whole
    range the track needs and the octave is not a special case.
    """
    intervals = MODE_INTERVALS.get(mode)
    if intervals is None:
        raise KeyError(f"unknown mode {mode!r}")
    notes: list[int] = []
    for octave in range(octaves):
        for interval in intervals:
            notes.append(root_midi + 12 * octave + interval)
    notes.append(root_midi + 12 * octaves)
    return notes


def nearest_scale_note(scale: list[int], target: int) -> int:
    """The scale note nearest to the target, within the scale's own range."""
    if not scale:
        return target
    return min(scale, key=lambda note: (abs(note - target), note))
