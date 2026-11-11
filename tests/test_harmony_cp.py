"""Tests for the deterministic harmonic-progression CP solver (issue #12 slice 1)."""

from __future__ import annotations

from indiegen.theory.harmony_cp import (
    MAX_SOLUTIONS,
    select_solution,
    solve_progressions,
    voice_leading_distance,
)


def test_empty_sections_yields_one_empty_solution() -> None:
    assert solve_progressions([60, 62, 64], 0) == [[]]


def test_no_domain_yields_no_solution() -> None:
    assert solve_progressions([], 3) == []


def test_single_section_all_domain_candidates() -> None:
    sols = solve_progressions([60, 62], 1)
    assert sols == [[60], [62]]


def test_voice_leading_limit_prunes() -> None:
    # domain 60 and 72, limit 5 -> cannot move 12 semitones in one step.
    sols = solve_progressions([60, 72], 2, voice_leading_limit=5)
    # staying put is allowed; only the 60->72 leap is pruned
    assert sols == [[60, 60], [72, 72]]


def test_voice_leading_limit_allows_small_steps() -> None:
    sols = solve_progressions([60, 62, 64], 2, voice_leading_limit=5)
    assert [60, 62] in sols
    assert [60, 64] in sols
    assert [62, 60] in sols


def test_fixed_first_and_last() -> None:
    sols = solve_progressions([60, 62, 64], 3, fixed_first=60, fixed_last=60, voice_leading_limit=5)
    assert all(s[0] == 60 and s[-1] == 60 for s in sols)
    assert [60, 62, 60] in sols


def test_fixed_value_outside_domain() -> None:
    assert solve_progressions([60, 62], 2, fixed_first=70) == []


def test_deterministic_ordering() -> None:
    a = solve_progressions([60, 62, 64], 3, voice_leading_limit=10)
    b = solve_progressions([64, 60, 62], 3, voice_leading_limit=10)
    assert a == b  # domain sorted internally


def test_select_solution_none() -> None:
    assert select_solution([], 5) is None


def test_select_solution_index() -> None:
    sols = solve_progressions([60, 62], 2, voice_leading_limit=10)
    # 2*2 = 4 solutions: [60,60],[60,62],[62,60],[62,62]
    assert len(sols) == 4
    assert select_solution(sols, 0) == [60, 60]
    assert select_solution(sols, 5) == sols[5 % 4]


def test_max_solutions_cap() -> None:
    # 2^10 = 1024 solutions, cap at 3.
    sols = solve_progressions([60, 62], 10, voice_leading_limit=10, max_solutions=3)
    assert len(sols) == 3


def test_voice_leading_distance() -> None:
    assert voice_leading_distance(60, 64) == 4
    assert voice_leading_distance(64, 60) == 4


def test_max_solutions_constant() -> None:
    assert MAX_SOLUTIONS == 2048
