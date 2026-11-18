"""c14: pin the closed-subgroup contract in ``theory.motif``.

These tests document the source truth at ``theory/motif.py:75-112`` that the
pure ``orbit_element`` helper relies on. No source is edited here: if a
primitive's behavior drifts, these fail before the composer can rely on it.

Source truth note: ``orbit`` returns ``orbit_length(g)`` cells ``[g^0..g^(n-1)]``
with the closing identity ``g^n`` computed then discarded. For transpositions
the closing element returns the cell transposed by a multiple of 12 octaves,
so exact equality holds only for the order-2 involutions; pitch classes and
durations always return exactly.
"""

from __future__ import annotations

import math

import pytest

from indiegen.theory.motif import (
    Cell,
    closed_orbit,
    cycle,
    cycle_length,
    orbit,
    orbit_len,
    orbit_length,
    transform,
)

# A non-trivial, asymmetric, non-octave cell: no accidental fixed point under
# inversion, retrograde or retrograde-inversion.
BASE: Cell = [(60, 1), (63, 2), (67, 3), (71, 4)]


def _generators() -> list[tuple[str, int, int, str]]:
    gens: list[tuple[str, int, int, str]] = []
    for n in range(1, 12):
        gens.append(("transpose", n, 0, f"T_{n}"))
    gens.append(("I_n", 7, 0, "I_7"))
    gens.append(("retrograde", 0, 0, "R"))
    gens.append(("RI", 0, 9, "RI_9"))
    return gens


def _apply(cell: Cell, name: str, parameter: int, axis: int) -> Cell:
    return transform(name, cell, parameter, axis)


@pytest.mark.parametrize(("name", "parameter", "axis", "label"), _generators())
def test_orbit_returns_exactly_orbit_length_cells(name: str, parameter: int, axis: int, label: str) -> None:
    n = orbit_length(name, parameter, axis)
    if name == "transpose":
        assert n == (1 if parameter % 12 == 0 else 12 // math.gcd(12, parameter % 12)), label
    else:
        assert n == 2, label

    cells = orbit(BASE, name, parameter, axis)
    assert len(cells) == n, label
    assert cells[0] == BASE, label
    for index in range(n - 1):
        assert cells[index + 1] == _apply(cells[index], name, parameter, axis), label

    closing = _apply(cells[-1], name, parameter, axis)
    assert [duration for _, duration in closing] == [duration for _, duration in BASE], label
    assert [(midi - base) % 12 for (midi, _), (base, _) in zip(closing, BASE)] == [0] * len(BASE), label
    # The order-2 involutions close exactly; T_6 closes only up to an octave.
    if name in ("I_n", "retrograde", "RI"):
        assert closing == BASE, label


@pytest.mark.parametrize(("name", "parameter", "axis", "label"), _generators())
def test_orbit_excludes_closing_identity(name: str, parameter: int, axis: int, label: str) -> None:
    tail = orbit(BASE, name, parameter, axis)[1:]
    assert BASE not in tail, label


def test_aliases_match_primaries() -> None:
    assert closed_orbit is orbit
    assert cycle is orbit
    assert cycle_length is orbit_length
    assert orbit_len is orbit_length


@pytest.mark.parametrize("name", ["augment", "augment_n", "fragment", "fragment_n"])
def test_augment_fragment_not_group_elements(name: str) -> None:
    assert orbit_length(name, 0, 0) == 1
    assert orbit(BASE, name, 0, 0) == [BASE]
