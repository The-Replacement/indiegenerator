"""The motif transforms.

BRIEF 6: "3-7 note cells, transformed (transpose/invert/retrograde/
augment/fragment)". A cell is a list of (midi, duration_frames) pairs, and
every transform is a pure function over it: the same cell in, the same cell
out, no randomness and no state.

The transforms are what make a motif a motif rather than a loop. A cell that
comes back in the same shape is a loop; a cell that comes back inverted, or
reversed, or stretched, is a reprise - which is the only kind of repetition
BRIEF 7 accepts.
"""

from __future__ import annotations

Cell = list[tuple[int, int]]

TRANSFORMS: tuple[str, ...] = ("transpose", "invert", "retrograde", "augment", "fragment")


def transpose(cell: Cell, semitones: int) -> Cell:
    """The cell moved up or down by a number of semitones."""
    return [(midi + semitones, duration) for midi, duration in cell]


def invert(cell: Cell, axis_midi: int) -> Cell:
    """The cell mirrored around a pitch.

    The axis is the harmonic centre, so the inverted cell stays in the key:
    a motif inverted around its own root is the same music seen upside down.
    """
    return [(2 * axis_midi - midi, duration) for midi, duration in cell]


def retrograde(cell: Cell) -> Cell:
    """The cell backwards, in time and in pitch."""
    return list(reversed(cell))


def augment(cell: Cell) -> Cell:
    """The cell stretched: every note lasts twice as long."""
    return [(midi, duration * 2) for midi, duration in cell]


def fragment(cell: Cell, length: int = 2) -> Cell:
    """The first few notes of the cell.

    A fragment is the smallest recognisable piece of a motif, so it keeps
    the beginning: the ear recognises the start of a cell it has heard.
    """
    if not cell:
        return []
    return cell[: max(1, min(length, len(cell)))]


def transform(name: str, cell: Cell, parameter: int, axis_midi: int) -> Cell:
    """Apply one transform by name.

    The parameter is the transform's own argument: the semitones of a
    transposition, the length of a fragment. The axis is the harmonic
    centre, which only the inversion needs.
    """
    if name == "identity":
        return list(cell)
    if name == "transpose":
        return transpose(cell, parameter)
    if name == "invert":
        return invert(cell, axis_midi)
    if name == "retrograde":
        return retrograde(cell)
    if name == "augment":
        return augment(cell)
    if name == "fragment":
        return fragment(cell, max(1, parameter))
    raise KeyError(f"unknown motif transform {name!r}")
