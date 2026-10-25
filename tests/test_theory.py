"""theory: the mode table is right, and a relative move keeps the notes in the scale.

A wrong interval table ships wrong pitch content with a green suite: no gate
measures what a note *is*. So the table is checked against the whole/half-step
pattern of each mode - knowledge that does not come from the table being
checked - and the relative tables are checked against the one thing the
director promises: after the move the section's notes are still notes of the
section's scale.
"""

from __future__ import annotations

import pytest

from indiegen.theory.scales import (
    MODE_INTERVALS,
    RELATIVE_INTERVALS,
    RELATIVE_MODES,
    mode_scale,
    relative_of,
)

# The step pattern of each mode, W = whole tone, H = half tone, read off the
# modes themselves rather than off MODE_INTERVALS: D dorian is the white keys
# from D, A aeolian the white keys from A, and so on. The two non-diatonic
# modes are the symmetric ones - the whole-tone scale is six whole steps, the
# octatonic alternates W H from the root.
STEP_PATTERNS: dict[str, str] = {
    "dorian": "W H W W W H W",
    "phrygian": "H W W W H W W",
    "lydian": "W W W H W W H",
    "mixolydian": "W W H W W H W",
    "aeolian": "W H W W H W W",
    "whole_tone": "W W W W W W",
    "octatonic": "W H W H W H W H",
}


def _from_pattern(pattern: str) -> tuple[int, ...]:
    """The intervals of a step pattern, as semitones above the root.

    The pattern's last step closes the octave, so the sum it produces is
    dropped: the table lists the seven degrees, not the eighth.
    """
    steps = {"W": 2, "H": 1}
    intervals = [0]
    for step in pattern.split():
        intervals.append(intervals[-1] + steps[step])
    return tuple(intervals[:-1])


@pytest.mark.parametrize("mode", sorted(STEP_PATTERNS))
def test_every_mode_matches_its_step_pattern(mode: str) -> None:
    assert set(STEP_PATTERNS) == set(MODE_INTERVALS), "a mode was added or dropped on one side only"
    assert MODE_INTERVALS[mode] == _from_pattern(STEP_PATTERNS[mode])


@pytest.mark.parametrize("root", [48, 60, 65, 72])
@pytest.mark.parametrize("mode", sorted(RELATIVE_MODES))
def test_a_relative_move_keeps_the_notes_inside_the_new_scale(mode: str, root: int) -> None:
    """The invariant `_reharmonize` leans on: same notes, new centre.

    The relative of a mode is the mode it shares its notes with, so the root
    moves by that pair's own interval and the pitch content is unchanged. A
    melody written before the move is still in the scale after it, whatever
    the pair - which is the whole point, since nothing re-derives a note from
    a section once the Director has moved it.
    """
    relative, interval = relative_of(mode)
    before = {note % 12 for note in mode_scale(mode, root, 1)}
    after = {note % 12 for note in mode_scale(relative, root + interval, 1)}
    assert before == after, f"{mode} -> {relative} (root {root} + {interval}) left the scale"


def test_the_two_relative_tables_cover_exactly_the_same_modes() -> None:
    """A mode with a relative but no interval, or the reverse, is a key-drift bug."""
    assert set(RELATIVE_MODES) == set(RELATIVE_INTERVALS)
    assert set(RELATIVE_MODES) == set(MODE_INTERVALS)
    assert set(RELATIVE_MODES.values()) <= set(MODE_INTERVALS)


def test_a_relative_is_built_from_one_place() -> None:
    """Both call sites take the pair from `relative_of`, never from two lookups."""
    for mode in MODE_INTERVALS:
        assert relative_of(mode) == (RELATIVE_MODES[mode], RELATIVE_INTERVALS[mode])


def test_an_unknown_mode_has_no_relative_and_does_not_move() -> None:
    """A mode the tables do not know about keeps its name and its root."""
    assert relative_of("not_a_mode") == ("not_a_mode", 0)


def test_mode_scale_covers_the_requested_octaves_with_the_root_on_top() -> None:
    """The shape the planners count on: degrees * octaves notes plus the root."""
    for mode, intervals in MODE_INTERVALS.items():
        scale = mode_scale(mode, 60, 2)
        assert len(scale) == len(intervals) * 2 + 1
        assert scale[-1] == 60 + 24
        assert scale[0] == 60
