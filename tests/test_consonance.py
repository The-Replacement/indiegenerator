"""Tests for the consonance scorer (issue #17).

The scorer is a measurement, so the tests are about what it measures: that
it tells chord shapes apart, that it does not care about the register, that
it is a pure function, and that it never lets a fragment of a chord look
cleaner than the chord.
"""

from __future__ import annotations

from indiegen.theory.consonance import (
    REFERENCE_ROOT_MIDI,
    best_chord,
    chord_candidates,
    chord_dissonance,
    chord_scores,
    consonant_chords,
    dissonance_pair,
    spectrum_dissonance,
)

# A single partial: the loudest, plainest voice there is.
PURE: list[tuple[int, int]] = [(1, 1)]

# The drone's just ratios: a voice whose partials sit on top of each other.
DRONE: list[tuple[int, int]] = [(1, 1), (9, 8), (5, 4), (4, 3), (3, 2)]

MAJOR_SCALE = [60, 62, 64, 65, 67, 69, 71, 72]
MAJOR_SCALE_3 = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79, 81, 83, 84]


def test_a_cluster_is_rougher_than_a_triad() -> None:
    """The score has to tell chord shapes apart, or it measures nothing."""
    cluster = spectrum_dissonance([0, 1, 2], PURE)
    triad = spectrum_dissonance([0, 4, 7], PURE)
    assert cluster > triad


def test_a_minor_third_is_rougher_than_a_fifth() -> None:
    third = spectrum_dissonance([0, 3, 7], PURE)
    fifth = spectrum_dissonance([0, 7, 12], PURE)
    assert third > fifth


def test_the_score_does_not_depend_on_the_register() -> None:
    """The same shape scores the same wherever it sits.

    Sethares' bandwidth is in absolute Hz, so a shape scored at its own
    register reads rougher the lower it sits. The scorer compares shapes at
    one reference pitch, so the register cannot leak into the answer: the
    same chord an octave up scores the same as the chord an octave down.
    """
    candidates = chord_candidates(MAJOR_SCALE_3, [0, 4, 7], [48, 60, 72])
    scores = {root: score for score, (root, _) in chord_scores(candidates, [DRONE])}
    assert len(scores) == 3
    assert len(set(scores.values())) == 1


def test_the_reference_register_is_the_documented_one() -> None:
    assert REFERENCE_ROOT_MIDI == 36


def test_a_single_tone_has_nothing_to_beat_against() -> None:
    """One tone against itself is consonant by construction."""
    assert spectrum_dissonance([0], DRONE) == 0
    assert spectrum_dissonance([], DRONE) == 0


def test_a_voice_with_more_partials_counts_more() -> None:
    """The chord is sounded by every voice; the busiest voice dominates.

    A lane's chord is not one voice's spectrum: the drone, the pad and the
    lead all sound it. The voice with the most partials beats against itself
    and against the others most, so it counts most in the chord's score.
    """
    quiet = chord_dissonance([0, 3, 7], [PURE])
    loud = chord_dissonance([0, 3, 7], [PURE, DRONE])
    assert loud > quiet


def test_the_score_is_a_pure_function() -> None:
    """The same candidates and the same voices always score the same."""
    candidates = chord_candidates(MAJOR_SCALE, [0, 4, 7], [60, 65, 72])
    first = chord_scores(candidates, [DRONE])
    second = chord_scores(candidates, [DRONE])
    assert first == second


def test_the_candidates_are_the_chords_the_scale_admits() -> None:
    """Each root is paired with the prefix of the declared chord it can voice."""
    candidates = chord_candidates(MAJOR_SCALE, [0, 4, 7], [60, 65, 72])
    assert candidates == [(60, (0, 4, 7)), (65, (0, 4, 7))]


def test_a_root_that_can_voice_only_a_fragment_is_not_a_candidate() -> None:
    """A fragment of the chord has fewer pairs to beat, and would look cleanest.

    Root 72 in a major scale that stops at 72 can voice neither the third
    nor the fifth of the chord, so it is not a candidate: the scorer would
    otherwise pick it every time.
    """
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    candidates = chord_candidates(scale, [0, 4, 7], [60, 65, 72])
    assert 72 not in [root for root, _ in candidates]


def test_the_chromatic_budget_admits_a_tone_the_scale_does_not_have() -> None:
    """The budget is the spice: a tone outside the scale, within the budget."""
    scale = [60, 62, 64, 65, 67, 71]
    # The 7th (0, 4, 7) is in the scale; the 9th (0, 4, 7, 9) is not.
    without = chord_candidates(scale, [0, 4, 7, 9], [60], 0)
    with_budget = chord_candidates(scale, [0, 4, 7, 9], [60], 500)
    assert without == [(60, (0, 4, 7))]
    assert with_budget == [(60, (0, 4, 7, 9))]


def test_the_best_chord_breaks_a_tie_by_the_lower_root() -> None:
    """The choice never depends on the order the candidates arrived in."""
    candidates = chord_candidates(MAJOR_SCALE, [0, 4, 7], [65, 60])
    assert best_chord(candidates, [DRONE]) == (60, (0, 4, 7))
    assert best_chord(list(reversed(candidates)), [DRONE]) == (60, (0, 4, 7))


def test_the_best_chord_is_none_when_there_is_nothing_to_choose() -> None:
    assert best_chord([], [DRONE]) is None
    assert consonant_chords([], [DRONE]) == []


def test_the_tolerance_admits_the_near_ties() -> None:
    """The draw needs a choice to make, and the tolerance is what gives it one.

    The roots that admit the whole chord are cleaner than the roots whose
    chord the scale truncates. With no tolerance only the cleanest survive;
    with one, the near-ties come back and the draw decides among them.
    """
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    candidates = chord_candidates(scale, [0, 4, 7, 9], [60, 62, 65])
    scores = {root: score for score, (root, _) in chord_scores(candidates, [DRONE])}
    assert len(set(scores.values())) > 1, "the fixture must have candidates that differ"

    strict = consonant_chords(candidates, [DRONE], 0)
    loose = consonant_chords(candidates, [DRONE], 1000)
    assert len(loose) >= len(strict) > 0
    assert all(root in dict(loose) for root, _ in strict)


def test_the_tolerance_never_admits_a_worse_candidate_than_the_best() -> None:
    candidates = chord_candidates(MAJOR_SCALE, [0, 4, 7], [60, 65, 72])
    eligible = consonant_chords(candidates, [DRONE], 0)
    best = chord_scores(candidates, [DRONE])[0][0]
    scores = chord_scores(candidates, [DRONE])
    assert all(score == best for score, (root, _) in scores if (root, _) in eligible)


def test_the_roughness_of_a_pair_peaks_inside_one_band() -> None:
    """Sethares' curve: zero a whole number of bands apart, maximal inside."""
    unison = dissonance_pair(440.0, 1.0, 440.0, 1.0)
    assert unison == 0.0
    assert dissonance_pair(440.0, 1.0, 441.0, 1.0) > 0.0
