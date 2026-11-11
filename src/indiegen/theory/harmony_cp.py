"""A tiny, deterministic constraint-programming solver for harmonic progressions.

No third-party dependency. The solver is pure Python and operates on integer
roots (MIDI notes or scale-degree indices) and, in the voicing-aware variant,
on chord voicings (ordered tuples of absolute MIDI pitches). Variables are
solved in section order, domains are sorted, and solutions are enumerated in
lexicographic order, so a seed-derived index selects the same solution on
every machine.

Constraints in this slice:
- every root/voicing must come from the supplied domain;
- adjacent roots must be within ``voice_leading_limit`` semitones (parsimony);
- adjacent voicings must be within ``voice_leading_limit`` (geodesic distance);
- admissibility: crossing-free, non-doubled voicings (and spellable into range);
- the first and last roots/voicings may be pinned (resolution at boundaries).

Modal mixture and tension targets are intentionally left to the caller's
domain construction (the chromatic budget already gates chord tones via
``theory.scales.chord_pool``); they are not re-derived here.
"""

from __future__ import annotations

from typing import Any

from indiegen.theory.orbifold import (
    Voicing,
    geodesic_distance,
    is_crossing,
    is_doubled,
)

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


def select_solution(solutions: list[Any], seed: int) -> list[Any] | None:
    """Pick one solution by seed-derived index. None if no solutions."""
    if not solutions:
        return None
    index = int(seed) % len(solutions)
    return list(solutions[index])


def voice_leading_distance(a: int, b: int) -> int:
    """Absolute semitone distance between two roots."""
    return abs(int(a) - int(b))


def is_voicing_admissible(voicing: Voicing) -> bool:
    """Whether a voicing is crossing-free and non-doubled."""
    if not voicing:
        return True
    if not is_crossing(voicing):
        return False
    return not is_doubled(voicing)


def voicing_distance(a: Voicing, b: Voicing) -> int:
    """Geodesic distance between two voicings."""
    return int(geodesic_distance(a, b))


def solve_voicing_progressions(  # noqa: C901
    domain: list[Voicing],
    sections: int,
    *,
    voice_leading_limit: int = 7,
    root_leading_limit: int | None = None,
    fixed_first: Voicing | None = None,
    fixed_last: Voicing | None = None,
    max_solutions: int = MAX_SOLUTIONS,
    require_admissible: bool = True,
) -> list[list[Voicing]]:
    """Enumerate feasible voicing progressions, up to ``max_solutions``.

    Adjacent voicings must be within ``voice_leading_limit`` (geodesic distance).
    Inadmissible voicings (crossing/doubled) are skipped when require_admissible.

    The geodesic distance lives in the wrapped mod-12 quotient, so it does not
    see the register at all: a voicing an octave away costs 0, and for a
    single-note voicing an octave leap costs 4 - less than a five-semitone
    step. That is right for the pitch-class question Tymoczko asks, and wrong
    for the question this composer asks, which is where the chord SITS.
    ``root_leading_limit`` adds the second constraint: the ROOT (voicing[0])
    may not move more than that many absolute semitones between adjacent
    sections. Without it the solver scatters the roots over the whole
    keyboard and the arrangement stops tracking its own timbre trajectory.
    """
    if sections <= 0:
        return [[]]
    if not domain:
        return []
    domain_filtered = [v for v in domain if (not require_admissible or is_voicing_admissible(v))]
    if not domain_filtered:
        return []
    domain_sorted = sorted(set(domain_filtered))
    if fixed_first is not None and fixed_first not in domain_sorted:
        return []
    if fixed_last is not None and fixed_last not in domain_sorted:
        return []
    solutions: list[list[Voicing]] = []
    current: list[Voicing] = []

    def may_follow(candidate: Voicing, previous: Voicing) -> bool:
        """Whether a voicing may follow another one.

        Two limits, and they answer two different questions: the geodesic
        distance asks whether the CHORD moves smoothly (and lives in the
        wrapped mod-12 quotient, so it cannot see the register), and the root
        limit asks whether the chord's ROOT stays where the listener can
        follow it.
        """
        try:
            distance = geodesic_distance(candidate, previous)
        except ValueError:
            return False
        if distance > voice_leading_limit:
            return False
        if root_leading_limit is None:
            return True
        return abs(candidate[0] - previous[0]) <= root_leading_limit

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
            if current and not may_follow(candidate, current[-1]):
                continue
            current.append(candidate)
            backtrack(index + 1)
            current.pop()
            if len(solutions) >= max_solutions:
                return

    backtrack(0)
    return solutions
