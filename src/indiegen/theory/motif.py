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


def T(cell: Cell, semitones: int) -> Cell:  # noqa: N802
    """Transpose by ``semitones`` (alias for ``transpose``)."""
    return transpose(cell, semitones)


def I(cell: Cell, axis_midi: int) -> Cell:  # noqa: E743,N802
    """Invert around ``axis_midi`` (alias for ``invert``)."""
    return invert(cell, axis_midi)


def R(cell: Cell) -> Cell:  # noqa: N802
    """Retrograde (alias for ``retrograde``)."""
    return retrograde(cell)


def RI(cell: Cell, axis_midi: int) -> Cell:  # noqa: N802
    """Retrograde inversion: invert, then reverse in time."""
    return retrograde(invert(cell, axis_midi))


def retrograde_inversion(cell: Cell, axis_midi: int) -> Cell:
    """Retrograde inversion (long form)."""
    return retrograde(invert(cell, axis_midi))


def retrograde_invert(cell: Cell, axis_midi: int) -> Cell:
    """Retrograde inversion (alternate spelling)."""
    return retrograde(invert(cell, axis_midi))


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
    if name in ("retrograde", "R"):
        return retrograde(cell)
    if name in ("augment",):
        return augment(cell)
    if name in ("fragment",):
        return fragment(cell, max(1, parameter))
    if name in ("retrograde_inversion", "RI", "retrograde_invert"):
        return retrograde(invert(cell, axis_midi))
    if name in ("T", "transpose", "transpose_n"):
        return transpose(cell, parameter)
    if name in ("I", "invert", "invert_n", "I_n"):
        return invert(cell, axis_midi)
    raise KeyError(f"unknown motif transform {name!r}")
