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

# The relative of a mode: the mode that shares its notes, so the section and
# the transposed notes still agree after the move. Dorian and phrygian are
# relatives, mixolydian and dorian are relatives, lydian and mixolydian are
# relatives, aeolian and lydian are relatives.
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

# How far the root moves with it, in semitones, keyed by the mode being left.
# The offset is a property of the pair, not one constant for every mode:
# aeolian's relative is a major third below (A aeolian -> F lydian), dorian's
# is a whole tone above and mixolydian's is a fifth below. The one rule every
# entry follows is that the scale is left unchanged - the same notes, heard
# from a different centre - which is what lets a note written before the move
# stay inside the mode that holds it after.
RELATIVE_INTERVALS: Mapping[str, int] = MappingProxyType(
    {
        "dorian": 2,
        "phrygian": -2,
        "lydian": 2,
        "mixolydian": -5,
        "aeolian": -4,
        "whole_tone": 0,
        "octatonic": -3,
    }
)


def relative_of(mode: str) -> tuple[str, int]:
    """The relative of a mode: the mode it shares its notes with, and how far
    its root moves to get there.

    Both call sites need the pair together, so the pair is built once. A mode
    that is not in the tables has no relative and does not move.
    """
    return RELATIVE_MODES.get(mode, mode), RELATIVE_INTERVALS.get(mode, 0)


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


def tonic_triad(root_midi: int, mode: str) -> tuple[int, int, int]:
    """The tonic triad (root, third, fifth) as MIDI pitches.

    The third is +3 semitones for minor quality and +4 for major. Quality is
    selected from ``mode``: ``"major"`` -> +4, ``"minor"`` -> +3, a modal
    name -> its scale's third interval. Unknown modes raise ``KeyError``.
    """
    if mode == "major":
        third_offset = 4
    elif mode == "minor":
        third_offset = 3
    elif mode in MODE_INTERVALS:
        intervals = MODE_INTERVALS[mode]
        if len(intervals) < 3:
            raise KeyError(f"mode {mode!r} has no third")
        third_offset = intervals[2]
        if third_offset not in (3, 4):
            third_offset = 3 if third_offset <= 3 else 4
    else:
        raise KeyError(f"unknown mode {mode!r}")
    return (root_midi, root_midi + third_offset, root_midi + 7)


def _tintinnabuli_members(root_midi: int, mode: str) -> list[int]:
    """Every tonic-triad tone over the octaves a T-voice can reach, ascending."""
    root, third, fifth = tonic_triad(root_midi, mode)
    members: set[int] = set()
    for octave in range(-6, 7):
        shift = 12 * octave
        members.add(root + shift)
        members.add(third + shift)
        members.add(fifth + shift)
    return sorted(members)


def _tintinnabuli_position(position: int, index: int, process: str) -> int:
    """The 1-based position the process asks for on this note."""
    pos = max(1, int(position))
    if process == "constant":
        return pos
    if process == "alternating":
        return pos if index % 2 == 0 else pos + 1
    if process == "step":
        return pos + index
    raise ValueError(f"unknown tintinnabuli process {process!r}")


def _tintinnabuli_direction(range_direction: int | str) -> int:
    """The signed range direction: +1 above the M-voice, -1 below it."""
    if isinstance(range_direction, str):
        lowered = range_direction.lower()
        if lowered in {"superior", "up", "above", "ascending", "+1", "1"}:
            return 1
        if lowered in {"inferior", "down", "below", "descending", "-1"}:
            return -1
        return int(range_direction)
    return int(range_direction)


def tintinnabuli_t_voice(
    m_midi: int,
    root_midi: int,
    mode: str,
    position: int,
    range_direction: int | str,
    index: int = 0,
    process: str = "constant",
) -> int:
    """The T-voice pitch for one M-voice note, by Pärt's position rule.

    The tonic triad is the armature; the position selects which triad tone
    the T-voice takes. Position 1 is the NEAREST triad tone in the chosen
    range direction: the nearest tone below the M-voice when the direction
    is inferior, the nearest above when it is superior. Position 2 is the
    next one out, and so on. The process moves that position across the
    phrase (``constant``, ``alternating``, ``step``).

    The result is always a member of the tonic triad - the rule only ever
    picks from the triad's own pitches - and it is a pure function of the
    M-voice note and the declared armature. A note that lands past the
    generated octaves continues the same triad class by whole octaves, so
    it stays a triad member.
    """
    members = _tintinnabuli_members(root_midi, mode)
    target = _tintinnabuli_position(position, index, process)
    direction = _tintinnabuli_direction(range_direction)

    if direction >= 0:
        candidates = sorted(tone for tone in members if tone > m_midi)
    else:
        candidates = sorted((tone for tone in members if tone < m_midi), reverse=True)

    if candidates:
        offset = target - 1
        if offset < len(candidates):
            return candidates[offset]
        return candidates[-1] + direction * 12 * (offset - len(candidates) + 1)

    # No triad tone lies on that side of the M-voice: take the nearest one and
    # move it by whole octaves until it is on the asked-for side, then step
    # out the rest of the position.
    base = min(members, key=lambda tone: (abs(tone - m_midi), tone))
    while (direction >= 0 and base <= m_midi) or (direction < 0 and base >= m_midi):
        base += direction * 12
    return base + direction * 12 * (target - 1)


derive_t_voice_midi = tintinnabuli_t_voice
t_voice_midi = tintinnabuli_t_voice
derive_tintinnabuli_tone = tintinnabuli_t_voice
tintinnabuli = tintinnabuli_t_voice
tintinnabuli_voice = tintinnabuli_t_voice
second_voice = tintinnabuli_t_voice
derive_second_voice = tintinnabuli_t_voice
t_voice = tintinnabuli_t_voice
position_rule = tintinnabuli_t_voice


def chord_pool(scale_midi: list[int], root_midi: int, intervals: list[int], budget_permille: int) -> list[int]:
    """The declared chord tones the scale and the chromatic budget admit.

    A tone in the scale is always admitted. A tone outside the scale is
    admitted only while the off-scale count stays within the budget: the
    fraction of chromatic tones in the returned prefix can never exceed
    ``budget_permille / 1000``. The first tone the budget refuses ends the
    list, because the voices take a prefix and a silently dropped middle
    tone would change the chord without being declared.

    At ``budget_permille = 0`` this is exactly the old scale filter: the
    prefix breaks at the first non-scale tone.
    """
    usable: list[int] = []
    off_scale = 0
    for interval in intervals:
        if root_midi + interval in scale_midi:
            usable.append(interval)
            continue
        total = len(usable) + 1
        if (off_scale + 1) * 1000 > budget_permille * total:
            break
        usable.append(interval)
        off_scale += 1
    return usable or [0]
