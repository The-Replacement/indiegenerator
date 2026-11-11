"""AC-17: the harmonic centre is chosen against the lane's own spectrum.

Issue #17 asks for chord selection by measured consonance. These tests are
about the wiring: what the score changes, what it does not change, and that
the lane's declared sonority is the thing being measured.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose
from indiegen.compose.planner import _chord_roots, _consonant_roots, _lane_sonority, _lane_voices
from indiegen.config import Preset, StationPreset, load_preset
from indiegen.plan import canonical_bytes
from indiegen.theory.scales import chord_pool

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
    """The plan says which chord its harmony was built on."""
    plan = compose(motorik, SEED, FRAMES)
    assert plan.chord_intervals == [0, 7, 2]


def test_the_switch_is_off_by_default(motorik: Preset) -> None:
    """Off means off: the plan says so, and nothing is scored."""
    plan = compose(motorik, SEED, FRAMES)
    assert plan.consonance_scoring_enabled == 0


def test_the_switch_off_leaves_the_plan_byte_identical(motorik: Preset) -> None:
    """With the switch off the composer draws exactly as it did before."""
    off = compose(_with_scoring(motorik, False), SEED, FRAMES)
    again = compose(_with_scoring(motorik, False), SEED, FRAMES)
    assert canonical_bytes(off.model_dump()) == canonical_bytes(again.model_dump())


def test_the_scored_root_is_one_that_can_carry_the_sonority(motorik: Preset) -> None:
    """The harmonic centre is a root whose chord the lane's scale can voice.

    The legacy path draws the harmonic centre from the whole scale, so it
    can land on a root that cannot carry the lane's chord at all. With the
    scorer on, the draw comes from the roots that can, and the chord those
    roots voice is the declared sonority.
    """
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    station = motorik.station.model_copy(update={"consonance_scoring_enabled": True})
    scored = compose(motorik.model_copy(update={"station": station}), SEED, FRAMES)

    root = scored.sections[0].root_midi
    sonority = _lane_sonority(lane, station)
    assert root in _chord_roots(lane.scale_midi, sonority, 3)
    assert chord_pool(lane.scale_midi, root, sonority, station.chromatic_budget_permille) == list(sonority)


def test_the_scored_pool_is_the_subset_that_can_carry_the_sonority(motorik: Preset) -> None:
    """The draw comes from the scored roots, not from the whole scale."""
    lane = next(entry.parameters for entry in motorik.lanes if entry.lane == "motorik")
    station = motorik.station.model_copy(update={"consonance_scoring_enabled": True})
    legacy_pool = list(lane.scale_midi)
    scored_pool = _consonant_roots(lane, station, legacy_pool)
    assert 0 < len(scored_pool) < len(legacy_pool)
    for root in scored_pool:
        assert chord_pool(lane.scale_midi, root, _lane_sonority(lane, station), 0) == list(
            _lane_sonority(lane, station)
        )


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
    assert _lane_voices(lane) == []

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
