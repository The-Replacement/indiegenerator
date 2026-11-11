"""A tiny, deterministic constraint-programming solver for harmonic progressions.

No third-party dependency. The solver is pure Python and operates on integer
roots (MIDI notes or scale-degree indices). Variables are solved in section
order, domains are sorted ascending, and solutions are enumerated in
lexicographic order, so a seed-derived index selects the same solution on
every machine.

Constraints in this slice:
- every root must come from the supplied domain;
- adjacent roots must be within ``voice_leading_limit`` semitones (parsimony);
- the first and last roots may be pinned (resolution at boundaries).

Modal mixture and tension targets are intentionally left to the caller's
domain construction (the chromatic budget already gates chord tones via
``theory.scales.chord_pool``); they are not re-derived here.
"""

from __future__ import annotations

MAX_SOLUTIONS: int = 2048


def solve_progressions(  # noqa: C901
    domain: list[int],
    sections: int,
    *,
    voice_leading_limit: int = 7,
    fixed_first: int | None = None,
    fixed_last: int | None = None,
    max_solutions: int = MAX_SOLUTIONS,
) -> list[list[int]]:
    """Enumerate feasible root progressions, up to ``max_solutions``.

    Returns a list of solutions, each a list of ``sections`` roots. An empty
    list means no feasible solution. ``sections == 0`` yields one empty
    solution.
    """
    if sections <= 0:
        return [[]]
    if not domain:
        return []
    domain_sorted = sorted(set(int(x) for x in domain))
    if fixed_first is not None and fixed_first not in domain_sorted:
        return []
    if fixed_last is not None and fixed_last not in domain_sorted:
        return []
    # Validate fixed values against voice-leading with themselves (trivial).
    solutions: list[list[int]] = []
    current: list[int] = []

    def backtrack(index: int) -> None:
        if len(solutions) >= max_solutions:
            return
        if index == sections:
            solutions.append(list(current))
            return
        for candidate in domain_sorted:
            if index == 0 and fixed_first is not None and candidate != fixed_first:
                continue
            if index == sections - 1 and fixed_last is not None and candidate != fixed_last:
                continue
            if current and abs(candidate - current[-1]) > voice_leading_limit:
                continue
            current.append(candidate)
            backtrack(index + 1)
            current.pop()
            if len(solutions) >= max_solutions:
                return

    backtrack(0)
    return solutions


def select_solution(solutions: list[list[int]], seed: int) -> list[int] | None:
    """Pick one solution by seed-derived index. None if no solutions."""
    if not solutions:
        return None
    index = int(seed) % len(solutions)
    return list(solutions[index])


def voice_leading_distance(a: int, b: int) -> int:
    """Absolute semitone distance between two roots."""
    return abs(int(a) - int(b))
