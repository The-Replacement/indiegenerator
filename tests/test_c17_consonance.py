"""AC-17: the harmonic centre is chosen against the lane's own spectrum.

Issue #17 asks for chord selection by measured consonance. These tests are
about the wiring: what the score changes, what it does not change, and that
the lane's declared sonority is the thing being measured.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose
from indiegen.compose.director import director
from indiegen.compose.planner import (
    _chord_roots,
    _consonant_roots,
    _lane_sonority,
    _lane_sonority_secondary,
    _lane_voices,
)
from indiegen.config import Preset, StationPreset, load_preset
from indiegen.plan import canonical_bytes
from indiegen.theory.scales import chord_pool, mode_scale, relative_of

SECONDS = 30
SEED = 1042
FRAMES = SECONDS * 44100


def _with_scoring(preset: Preset, enabled: bool) -> Preset:
    """The same preset with the station's consonance switch flipped."""
    station: StationPreset = preset.station.model_copy(update={"consonance_scoring_enabled": enabled})
    return preset.model_copy(update={"station": station})


@pytest.fixture(scope="module")
def motorik(presets_dir: object) -> Preset:
    return load_preset("motorik")


def test_the_lane_declares_the_sonority_the_scorer_measures(motorik: Preset) -> None:
    """The declaration is the lane's, and it is what the scorer reads."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    assert lane.chord_intervals == [0, 7, 2]
    assert _lane_sonority(lane, motorik.station) == [0, 7, 2]


def test_the_plan_names_the_sonority_it_built(motorik: Preset) -> None:
    """The plan says which chord its harmony was built on.

    With a second declared shape (mechanism B) the draw may pick either, so
    the plan's chord is one of the declared shapes, not a single pinned one.
    """
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    plan = compose(motorik, SEED, FRAMES)
    assert plan.chord_intervals in (lane.chord_intervals, lane.chord_intervals_secondary)


def test_the_switch_is_on_by_default(motorik: Preset) -> None:
    """On by default: the lane's sonority is measured, and the root follows it."""
    plan = compose(motorik, SEED, FRAMES)
    assert plan.consonance_scoring_enabled == 1


def test_the_switch_off_is_the_legacy_draw(motorik: Preset) -> None:
    """With the switch off the composer draws exactly as it did before."""
    off = compose(_with_scoring(motorik, False), SEED, FRAMES)
    again = compose(_with_scoring(motorik, False), SEED, FRAMES)
    assert canonical_bytes(off.model_dump()) == canonical_bytes(again.model_dump())
    assert off.consonance_scoring_enabled == 0


def test_the_scored_root_is_one_that_can_carry_the_sonority(motorik: Preset) -> None:
    """The harmonic centre is a root whose chord the lane's scale can voice.

    The legacy path draws the harmonic centre from the whole scale, so it
    can land on a root that cannot carry the lane's chord at all. With the
    scorer on, the draw comes from the roots that can, and the chord those
    roots voice is the declared sonority.
    """
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    station = motorik.station
    scored = compose(motorik, SEED, FRAMES)

    root = scored.sections[0].root_midi
    sonority = scored.chord_intervals
    assert root in _chord_roots(lane.scale_midi, sonority, 3)
    assert chord_pool(lane.scale_midi, root, sonority, station.chromatic_budget_permille) == list(sonority)


def test_the_scored_pool_is_the_subset_that_can_carry_the_sonority(motorik: Preset) -> None:
    """The draw comes from the scored roots, not from the whole scale."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    station = motorik.station.model_copy(update={"consonance_scoring_enabled": True})
    legacy_pool = list(lane.scale_midi)
    scored_pairs = _consonant_roots(lane, station, legacy_pool)
    assert 0 < len(scored_pairs) < len(legacy_pool)
    for shape, root in scored_pairs:
        assert chord_pool(lane.scale_midi, root, list(shape), 0) == list(shape)


def test_the_scoring_is_deterministic(motorik: Preset) -> None:
    """The same seed and the same preset give the same plan, scored or not."""
    station = motorik.station.model_copy(update={"consonance_scoring_enabled": True})
    scored = motorik.model_copy(update={"station": station})
    first = compose(scored, SEED, FRAMES)
    second = compose(scored, SEED, FRAMES)
    assert canonical_bytes(first.model_dump()) == canonical_bytes(second.model_dump())


def test_a_lane_without_a_sonority_is_not_scored(presets_dir: object) -> None:
    """A lane that declares no chord keeps the legacy draw, whatever the switch.

    indie-noise's dissonance is deliberate (BRIEF 6), so there is no chord
    to steer towards and the scorer has nothing to say about the lane.
    """
    preset = load_preset("indie-noise")
    lane = next(entry.parameters for entry in preset.lanes if entry.lane == "indie-noise")
    assert lane.chord_intervals == []
    assert _lane_voices(lane) == [tuple((n, 1) for n in range(1, 6))]

    station = preset.station.model_copy(update={"consonance_scoring_enabled": True})
    scored = preset.model_copy(update={"station": station})
    off = compose(preset, SEED, FRAMES)
    on = compose(scored, SEED, FRAMES)
    assert [section.root_midi for section in off.sections] == [section.root_midi for section in on.sections]


def test_the_tolerance_gives_the_draw_more_choices(motorik: Preset) -> None:
    """A wider tolerance admits the near-ties, which is where variety lives."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    strict = motorik.station.model_copy(update={"consonance_scoring_enabled": True, "consonance_tolerance_permille": 0})
    loose = motorik.station.model_copy(
        update={"consonance_scoring_enabled": True, "consonance_tolerance_permille": 1000}
    )
    strict_pool = _consonant_roots(lane, strict, list(lane.scale_midi))
    loose_pool = _consonant_roots(lane, loose, list(lane.scale_midi))
    assert len(loose_pool) >= len(strict_pool)


def test_the_segments_walk_the_scored_pool(motorik: Preset) -> None:
    """Slice 4, AC-1: a chord segment sits on a root that can carry the sonority.

    With the switch on, the composer's segment walk reads the scored pool -
    the roots whose chord the lane's spectrum voices cleanly - so the pad's
    per-segment events land on roots the legacy draw could have avoided.
    """
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    station = motorik.station.model_copy(update={"consonance_scoring_enabled": True, "chord_segments_per_section": 3})
    preset = motorik.model_copy(update={"station": station})
    # The pool the composer scores over: the chord-capable roots when the
    # lane's poly-period card declares a chord, the whole scale otherwise -
    # the same two lines compose runs (planner.py, the roots/pool draw).
    from indiegen.config import PolyPeriodCard

    intervals = next((card.chord_intervals for card in lane.techniques if isinstance(card, PolyPeriodCard)), [])
    chord_roots = _chord_roots(lane.scale_midi, intervals, 3) if intervals else list(lane.scale_midi)
    scored_pairs = _consonant_roots(lane, station, chord_roots if chord_roots else list(lane.scale_midi))
    assert 0 < len(scored_pairs) < len(chord_roots)
    scored = [root for _, root in scored_pairs]

    plan = compose(preset, SEED, FRAMES)
    pads = [event for event in plan.events if event.instrument == "pad"]
    assert pads  # the lane declares a pad, so the segments are audible
    for event in pads:
        assert event.midi in scored


def test_the_segments_walk_the_legacy_roots_when_off(motorik: Preset) -> None:
    """Slice 4, AC-2: with the switch off the walk reads the unscored scale.

    The contrast with the previous test pins both paths: off, the pad's
    segment roots are only required to sit in the lane's scale; on, they sit
    in the scored pool.
    """
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    preset = _with_scoring(motorik, False)
    station_off = preset.station.model_copy(update={"chord_segments_per_section": 3})
    plan = compose(preset.model_copy(update={"station": station_off}), SEED, FRAMES)
    pads = [event for event in plan.events if event.instrument == "pad"]
    assert pads
    scale = set(lane.scale_midi)
    for event in pads:
        assert event.midi in scale


def test_the_plan_carries_the_voices_it_measured(motorik: Preset) -> None:
    """Slice 4, AC-3: the plan names the spectra the sonority is judged against."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    expected = _lane_voices(lane)
    assert expected
    plan = compose(motorik, SEED, FRAMES)
    voices = [[(ratio.numerator, ratio.denominator) for ratio in voice] for voice in plan.chord_voices]
    assert voices == [list(voice) for voice in expected]


def test_the_director_measures_every_section(motorik: Preset) -> None:
    """Slice 4, AC-4: after the moves each section names what its own scale admits.

    The motorik sonority is three tones and the lane's scale admits it at
    every drawn root, so every section reports the full chord and a nonzero
    roughness against the plan's own voices.
    """
    plan = compose(motorik, SEED, FRAMES)
    directed = director(plan)
    sonority = plan.chord_intervals
    assert sonority
    for section in directed.sections:
        assert section.chord_tones_admitted == len(sonority)
        assert section.chord_consonance_permille > 0


def test_the_director_measures_a_moved_section_at_its_moved_root(motorik: Preset) -> None:
    """Slice 4, AC-5: a reharmonized section is measured where the move left it.

    The measurement is recomputed here from the section's own post-move mode
    and root, so the test holds the director to its own arithmetic rather
    than to a pinned number.
    """
    from indiegen.plan import DirectorMove
    from indiegen.theory.scales import chord_pool as pool

    plan = compose(motorik, SEED, FRAMES)
    move = DirectorMove(
        sample=0,
        strategy="reharmonize_relative",
        detail="reharmonize to the relative mode",
        parameter=0,
        crossfade_frames=0,
        applies_to=["bass"],
    )
    directed = director(plan.model_copy(update={"strategy_deck": [move]}))
    assert directed.director_log  # the move changed something
    for before, after in zip(plan.sections, directed.sections, strict=True):
        relative, interval = relative_of(before.mode)
        assert (after.mode, after.root_midi) == (relative, before.root_midi + interval)
        scale = mode_scale(after.mode, after.root_midi, 2)
        tones = pool(scale, after.root_midi, directed.chord_intervals, directed.chromatic_budget_permille)
        assert after.chord_tones_admitted == len(tones)


def test_the_measurement_is_a_strict_no_op_when_off(motorik: Preset) -> None:
    """Slice 4, AC-6: with the switch off the new fields stay zero."""
    off = _with_scoring(motorik, False)
    plan = compose(off, SEED, FRAMES)
    directed = director(plan)
    for section in directed.sections:
        assert section.chord_tones_admitted == 0
        assert section.chord_consonance_permille == 0


def test_mechanism_b_per_shape_eligibility_union(motorik: Preset) -> None:
    """Each declared shape contributes its own score-governed roots (mechanism B)."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    assert _lane_sonority_secondary(lane, motorik.station) == [0, 7, 9]
    legacy_pool = list(lane.scale_midi)
    pairs = _consonant_roots(lane, motorik.station, legacy_pool)
    shapes = {shape for shape, _ in pairs}
    assert (0, 7, 2) in shapes
    assert (0, 7, 9) in shapes
    # every pair is (shape, root) with a root that carries that shape
    for shape, root in pairs:
        assert chord_pool(lane.scale_midi, root, list(shape), 0) == list(shape)


def test_mechanism_b_variety_across_seeds(motorik: Preset) -> None:
    """The draw selects both declared shapes across the sweep seeds."""
    drawn = {tuple(compose(motorik, seed, FRAMES).chord_intervals) for seed in (1042, 2000, 3005)}
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    assert drawn == {tuple(lane.chord_intervals), tuple(lane.chord_intervals_secondary)}


def test_mechanism_b_empty_secondary_falls_back(motorik: Preset) -> None:
    """A lane with no secondary shape behaves like the single-shape path."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    no_secondary = lane.model_copy(update={"chord_intervals_secondary": []})
    new_lanes = [e.model_copy(update={"parameters": no_secondary}) for e in motorik.lanes if e.lane == "motorik"]
    preset = motorik.model_copy(update={"lanes": new_lanes})
    plan = compose(preset, SEED, FRAMES)
    assert plan.chord_intervals == [0, 7, 2]
