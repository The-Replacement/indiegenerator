"""Consonance scoring for chord candidates (issue #17).

A candidate is a chord the lane could voice: a root, plus the tones that
root admits under the scale and the chromatic budget. The score is the
roughness of the spectrum that would sound, measured with Sethares'
critical-bandwidth curve: every tone of the chord, each carrying the voice's
declared partials, with the roughness summed over the pairs that belong to
DIFFERENT tones. A note's own partials are consonant by construction; what a
chord is judged on is the beating BETWEEN its notes.

Three calibration decisions, all of them load-bearing.

*REGISTER-FAIR.* The comparison is made at one reference pitch, so what the
score says is which chord SHAPE is cleanest, not which octave it happens to
sit in. Sethares' bandwidth is in absolute Hz, so the same shape scored at
its own register reads rougher the lower it sits; without this the scorer
would just pick the top of the scale, which is the opposite of what a
consonance test is for. The register is the arranger's business - the CP
progression and the voice-leading walk both choose it.

*PER-PAIR.* The roughness is averaged over the pairs of tones rather than
summed, so a chord is not scored worse merely for having more notes. A
truncated chord (one tone missing from the scale) would otherwise win on
paper for being smaller, which is the opposite of the intent.

*PER-VOICE, WEIGHTED.* A lane's chord is sounded by more than one voice when
the lane has more than one additive voice, and each voice contributes its own
number of partial pairs: a voice with nine partials beats against itself and
against the other voices far more than a voice with one. The chord's score is
therefore the weighted mean of the voices' scores, weighted by the pairs each
voice contributes.

The curve is evaluated in float and rounded once, on the way out, to a
permille integer. The module is pure: no I/O, no RNG, no plan or preset
state, and no import of the render path.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from indiegen.theory.scales import chord_pool

# The pitch every candidate is scored at. The register is the arranger's choice.
REFERENCE_ROOT_MIDI: int = 36

A4_HZ: float = 440.0
A4_MIDI: int = 69

# A candidate chord: the root it sits on and the tones it sounds, as
# semitone offsets from that root.
Chord = tuple[int, tuple[int, ...]]

# A chord has at least three tones. Below that it is a fragment of the
# declared chord, and a fragment has fewer pairs of tones to beat against,
# which would make it look cleanest of all - the scorer would then prefer
# the root that voices least of the chord.
MIN_CHORD_TONES: int = 3


def _hz(midi: int) -> float:
    """The frequency of a MIDI note in equal temperament.

    Local rather than imported: ``theory/`` does not import the render path,
    and the renderer's own converter is free to change under it.
    """
    return A4_HZ * math.pow(2.0, (midi - A4_MIDI) / 12.0)


def dissonance_pair(f1: float, a1: float, f2: float, a2: float) -> float:
    """Sethares' roughness between two partials (Sethares 1999, ch. 3).

    ``s`` is the separation of the two partials in critical bandwidths, and
    the roughness is the difference of two decaying exponentials in it: zero
    when the partials are a whole number of bands apart, maximal when they
    sit inside one band and beat against each other.

    The two partials must be given in ascending frequency; the amplitudes go
    with them.
    """
    if f1 <= 0 or f2 <= 0:
        return 0.0
    lo, hi = (f1, f2) if f1 <= f2 else (f2, f1)
    a_lo, a_hi = (a1, a2) if f1 <= f2 else (a2, a1)
    s = (hi - lo) / (0.021 * lo + 19.0)
    return a_lo * a_hi * (math.exp(-3.5 * s) - math.exp(-5.75 * s))


def _voice_roughness(
    tones: Sequence[int],
    partial_ratios: Sequence[tuple[int, int]],
    reference_root_midi: int,
) -> tuple[float, int]:
    """The mean roughness of one voice's spectrum over a chord, and its pair count.

    The pair count is what the voice contributes to the chord's total: a voice
    with P partials on each of T tones makes C(T, 2) * P * P cross-tone pairs.
    """
    partials: list[tuple[float, float, int]] = []
    for index, tone in enumerate(tones):
        base = _hz(reference_root_midi + int(tone))
        for numerator, denominator in partial_ratios:
            partials.append((base * numerator / denominator, 1.0, index))
    total = 0.0
    pairs = 0
    for i in range(len(partials)):
        for j in range(i + 1, len(partials)):
            if partials[i][2] == partials[j][2]:
                continue
            total += dissonance_pair(partials[i][0], partials[i][1], partials[j][0], partials[j][1])
            pairs += 1
    if pairs == 0:
        return 0.0, 0
    return total / pairs, pairs


def spectrum_dissonance(
    tones: Sequence[int],
    partial_ratios: Sequence[tuple[int, int]],
    reference_root_midi: int = REFERENCE_ROOT_MIDI,
) -> int:
    """The roughness of one voice's spectrum over a chord, in permille.

    ``tones`` are the chord's semitone offsets from its root, and
    ``partial_ratios`` are the voice's declared partials as (numerator,
    denominator) pairs. Each tone carries the voice's partials; the roughness
    is summed over the pairs belonging to different tones and averaged over
    how many such pairs there are, so a chord is not scored worse merely
    for having more notes.

    The chord is scored at ``reference_root_midi``, so the result is a
    property of the chord's shape alone.
    """
    mean, _ = _voice_roughness(tones, partial_ratios, reference_root_midi)
    return int(round(1000.0 * mean))


def chord_dissonance(
    tones: Sequence[int],
    voices: Sequence[Sequence[tuple[int, int]]],
    reference_root_midi: int = REFERENCE_ROOT_MIDI,
) -> int:
    """The roughness of a chord sounded by every voice of a lane, in permille.

    ``voices`` is one partial-ratio list per additive voice of the lane. The
    chord's score is the weighted mean of the voices' scores, weighted by the
    number of partial pairs each voice contributes: the voice with the most
    partials is the one that beats most, so it counts most. A lane with no
    additive voice has nothing to measure and scores 0.
    """
    weighted = 0.0
    weight = 0
    for partial_ratios in voices:
        mean, pairs = _voice_roughness(tones, partial_ratios, reference_root_midi)
        if pairs == 0:
            continue
        weighted += mean * pairs
        weight += pairs
    if weight == 0:
        return 0
    return int(round(1000.0 * weighted / weight))


def chord_candidates(
    scale_midi: Sequence[int],
    declared_intervals: Sequence[int],
    roots: Sequence[int],
    budget_permille: int = 0,
) -> list[Chord]:
    """The chords the lane could voice at the given roots, in root order.

    Each root is paired with the chord it admits - the prefix of the
    declared intervals the scale and the chromatic budget allow - which is
    the same rule the poly-period voice applies when it plays its chord.

    A root whose chord falls below ``MIN_CHORD_TONES`` is not a candidate:
    it is a fragment of the declared chord, not the chord.
    """
    scale = [int(note) for note in scale_midi]
    intervals = [int(interval) for interval in declared_intervals]
    out: list[Chord] = []
    for root in sorted({int(value) for value in roots}):
        tones = tuple(chord_pool(scale, root, intervals, budget_permille))
        if len(tones) < MIN_CHORD_TONES:
            continue
        out.append((root, tones))
    return out


def chord_scores(
    candidates: Sequence[Chord],
    voices: Sequence[Sequence[tuple[int, int]]],
) -> list[tuple[int, Chord]]:
    """Every candidate with its score, cheapest first, ties by the lower root.

    The order is canonical: the same candidates and the same voices always
    score the same and sort the same, so the score is a pure function of the
    plan and never of the order the candidates arrived in.
    """
    scored = [(chord_dissonance(tones, voices), (root, tones)) for root, tones in candidates]
    scored.sort(key=lambda item: (item[0], item[1][0]))
    return scored


def best_chord(
    candidates: Sequence[Chord],
    voices: Sequence[Sequence[tuple[int, int]]],
) -> Chord | None:
    """The most consonant candidate, or None when there is none.

    Ties break by the lower root, so the choice is a pure function of the
    plan and never depends on the seed or on the order the candidates were
    produced in.
    """
    scored = chord_scores(candidates, voices)
    if not scored:
        return None
    return scored[0][1]


def consonant_chords(
    candidates: Sequence[Chord],
    voices: Sequence[Sequence[tuple[int, int]]],
    tolerance_permille: int = 0,
) -> list[Chord]:
    """The candidates the arranger may choose from, in root order.

    A candidate is eligible when its score is within ``tolerance_permille``
    of the cheapest candidate's score - 0 admits only the cheapest, and a
    larger tolerance admits the near-ties, which is where the draw still has
    a choice to make. The order is the canonical root order, so the draw is
    over a fixed list.
    """
    scored = chord_scores(candidates, voices)
    if not scored:
        return []
    limit = scored[0][0] + max(0, int(tolerance_permille))
    eligible = [chord for score, chord in scored if score <= limit]
    return sorted(eligible, key=lambda chord: chord[0])
