"""Wrapped mod-12 quotient geodesic voice leading (Tymoczko).

A chord voicing is an ordered k-tuple of absolute MIDI pitches: pitch-class
(mod 12) plus register. The geodesic distance between two voicings is the
minimum total circular-semitone movement over all voice bijections — the
"shortest path" in the wrapped quotient space, computed in pure integer
arithmetic (no floats, no RNG, no I/O). This is the integer cousin of
Tymoczko's orbifold, not the continuous geometry: same shape, but every value
is a small integer and every tie-break is deterministic.

Nothing here imports the compose or render paths. It is tables and pure
functions, like the rest of ``theory/``.
"""

from __future__ import annotations

from itertools import permutations

Voicing = tuple[int, ...]


def circular_semitone_dist(a: int, b: int) -> int:
    """Minimal movement between two pitch classes on the mod-12 circle, 0..6."""
    d = abs((int(a) - int(b)) % 12)
    return min(d, 12 - d)


def geodesic_distance(a: Voicing, b: Voicing) -> int:
    """Minimum total circular-semitone movement over all voice bijections.

    Enumerates every k! pairing (k is at most the chord-tone budget + root,
    so bounded by a small constant). Raises ``ValueError`` when the voicings
    have different sizes. Pure: no I/O, no RNG, no global or plan state.
    """
    if len(a) != len(b):
        raise ValueError("voicing length mismatch")
    if not a:
        return 0
    return min(
        sum(circular_semitone_dist(a[i], b[j]) for i, j in enumerate(perm)) for perm in permutations(range(len(b)))
    )


def geodesic_matching(a: Voicing, b: Voicing) -> tuple[int, ...]:
    """The lexicographically-first optimal pairing, as a tuple of b-indices.

    ``result[i]`` is the index into ``b`` paired with voice ``i`` of ``a``.
    ``itertools.permutations`` yields pairings in lexicographic order, and
    ``min`` keeps the first minimum, so the tie-break is deterministic.
    """
    if len(a) != len(b):
        raise ValueError("voicing length mismatch")
    if not a:
        return ()
    return min(
        permutations(range(len(b))),
        key=lambda perm: sum(circular_semitone_dist(a[i], b[j]) for i, j in enumerate(perm)),
    )


def is_crossing(v: Voicing) -> bool:
    """True iff voices are in strictly increasing register order (no crossing, no equal)."""
    return all(v[i] < v[i + 1] for i in range(len(v) - 1))


def is_doubled(v: Voicing) -> bool:
    """True iff any two voices share the same absolute pitch."""
    return len(set(v)) != len(v)


def _valid(v: Voicing, low: int, high: int) -> bool:
    """Whether a voicing already satisfies every walk constraint."""
    return is_crossing(v) and not is_doubled(v) and all(low <= p <= high for p in v)


def _ceil_pitch(pc: int, floor: int) -> int:
    """The smallest pitch >= floor whose pitch-class is ``pc`` (mod 12)."""
    pc %= 12
    delta = (pc - (floor % 12)) % 12
    return floor + delta


def _spell(pcs: list[int], low: int, high: int) -> Voicing | None:
    """Spell distinct ascending pitch classes into [low, high] strictly increasing.

    Returns the lexicographically smallest (lowest-register) spelling, or None
    when the window cannot hold all of them as distinct strictly-ordered pitches.
    """
    result: list[int] = []
    floor = low
    for pc in pcs:
        pitch = _ceil_pitch(pc, floor)
        if pitch > high:
            return None
        result.append(pitch)
        floor = pitch + 1
    return tuple(result)


def lead_voicing(prev: Voicing, target: Voicing, *, low: int, high: int) -> Voicing:
    """The register-resolved walk step toward ``target``.

    The geodesic distance depends only on pitch classes, not octave, so the
    walk is free to spell ``target``'s pitch classes into the register window
    ``[low, high]`` as the most compact (lexicographically smallest) strictly
    ordered, non-doubled voicing. When ``target`` already satisfies every
    constraint it is returned untouched; when the window cannot hold the
    voicing it falls back to ``target``. Never raises.
    """
    if _valid(target, low, high):
        return target
    pcs = sorted({int(p) % 12 for p in target})
    spelling = _spell(pcs, low, high)
    return spelling if spelling is not None else target
