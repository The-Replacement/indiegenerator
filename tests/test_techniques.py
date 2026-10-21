"""AC-13 to AC-34: the techniques' invariants, asserted from the Plan.

No criterion here is judged by ear: the voice count, the distinct periods,
the exact sounding-frame density, the one-chord rule, the minor second rule,
the drift, the ratios, the feedback and the delay are all read off the
frozen plan.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.compose.techniques.t1_polyperiod import plan_poly_period, sounding_frames
from indiegen.config import PolyPeriodCard, load_preset
from indiegen.errors import PlanError
from indiegen.plan import DroneEvent, Plan, PluckEvent


@pytest.fixture(scope="module")
def ambient_plan(presets_dir: object) -> Plan:
    """The directed ambient plan for the canonical seed."""
    return director(compose(load_preset("ambient", presets_dir=presets_dir), 1042, 90 * 44100))


def test_the_poly_period_voice_count_is_between_three_and_nine(ambient_plan: Plan) -> None:
    events = [event for event in ambient_plan.events if event.kind == "poly_period"]
    assert events
    for event in events:
        assert 3 <= len(event.voices) <= 9


def test_the_periods_are_distinct_and_in_range(ambient_plan: Plan) -> None:
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        periods = [voice.period_frames for voice in event.voices]
        assert len(set(periods)) == len(periods)
        for period in periods:
            assert 15 * ambient_plan.sample_rate <= period <= 90 * ambient_plan.sample_rate


def test_the_on_window_covers_the_attack_and_the_release(ambient_plan: Plan) -> None:
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        for voice in event.voices:
            assert voice.on_frames >= event.attack_frames + event.release_frames
            assert 0 <= voice.phase_frames < voice.period_frames


def test_the_sounding_frame_density_is_between_half_and_two(ambient_plan: Plan) -> None:
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        frames = sum(
            sounding_frames(voice.period_frames, voice.on_frames, voice.phase_frames, ambient_plan.duration_frames)
            for voice in event.voices
        )
        density = frames / ambient_plan.duration_frames
        assert 0.5 <= density <= 2.0


def test_the_voices_come_from_one_chord_in_the_scale(ambient_plan: Plan) -> None:
    scale = ambient_plan.scale_midi
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        for voice in event.voices:
            assert voice.midi in scale


def test_at_most_one_pair_forms_a_minor_second(ambient_plan: Plan) -> None:
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        pitches = [voice.midi for voice in event.voices]
        pairs = 0
        for index, first in enumerate(pitches):
            for second in pitches[index + 1 :]:
                if abs(first - second) % 12 in {1, 11}:
                    pairs += 1
        assert pairs <= 1


def test_the_gate_eight_safety_rule(ambient_plan: Plan) -> None:
    """The drone starts at frame zero, and the first voice is present at once."""
    drones = [event for event in ambient_plan.events if event.kind == "drone"]
    assert drones
    for drone in drones:
        assert drone.start_frame == 0
        assert drone.start_frame + drone.duration_frames == ambient_plan.duration_frames
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        assert event.voices[0].phase_frames == 0


def test_a_density_outside_the_band_raises_a_plan_error(presets_dir: object) -> None:
    """A configuration that cannot reach the band must fail, not pass quietly."""
    lane = load_preset("ambient", presets_dir=presets_dir).lanes[0].parameters
    card = next(item for item in lane.techniques if item.kind == "poly_period")
    assert isinstance(card, PolyPeriodCard)
    impossible = PolyPeriodCard.model_validate(
        {**card.model_dump(), "on_fraction_permille": {"min": 1000, "max": 1000}}
    )
    context = TechniqueContext(
        preset="ambient",
        seed=1042,
        lane="ambient",
        scale_midi=list(lane.scale_midi),
        root_midi=lane.scale_midi[0],
        sample_rate=44100,
        duration_frames=90 * 44100,
        frames_per_beat=22000,
        attack_frames=13230,
        release_frames=13230,
    )
    with pytest.raises(PlanError):
        plan_poly_period(impossible, SplitMix64(7), context)


def test_the_drone_partials_carry_their_own_drift(ambient_plan: Plan) -> None:
    drones = [event for event in ambient_plan.events if event.kind == "drone"]
    assert drones
    for drone in drones:
        assert 1 <= len(drone.partials) <= 16
        for partial in drone.partials:
            assert partial.detune_lfo.rate.numerator > 0
            assert partial.detune_lfo.depth_cents >= 0
            assert partial.amplitude_lfo.rate.numerator > 0
            assert partial.amplitude_lfo.depth_millibels >= 0
            assert partial.ratio.denominator > 0


def test_the_drone_ratios_are_the_declared_ones(ambient_plan: Plan) -> None:
    for event in ambient_plan.events:
        if event.kind != "drone":
            continue
        for partial in event.partials:
            ratio = (partial.ratio.numerator, partial.ratio.denominator)
            assert ratio in {(1, 1), (9, 8), (5, 4), (4, 3), (3, 2)}


def test_the_pluck_feedback_is_in_the_declared_band(ambient_plan: Plan) -> None:
    plucks = [event for event in ambient_plan.events if event.kind == "pluck"]
    assert plucks
    for pluck in plucks:
        value = pluck.feedback.numerator / pluck.feedback.denominator
        assert 0.996 <= value <= 0.999


def test_the_chorus_is_a_detuned_pair(ambient_plan: Plan) -> None:
    plucks = [event for event in ambient_plan.events if event.kind == "pluck"]
    pairs: dict[tuple[int, int], list[PluckEvent]] = {}
    for pluck in plucks:
        pairs.setdefault((pluck.start_frame, pluck.midi), []).append(pluck)
    assert pairs
    for group in pairs.values():
        assert len(group) == 2
        detunes = sorted(event.detune_cents for event in group)
        assert detunes[1] - detunes[0] == 7


def test_the_dotted_eighth_delay_is_resolved_at_compose_time(ambient_plan: Plan) -> None:
    assert ambient_plan.delay_sends
    send = ambient_plan.delay_sends[0]
    assert send.delay_frames == 3 * ambient_plan.frames_per_beat // 4


def test_the_voices_take_a_prefix_of_the_chord_intervals(ambient_plan: Plan, presets_dir: object) -> None:
    """The offsets are a prefix of the declared list, not a cycle of it."""
    lane = load_preset("ambient", presets_dir=presets_dir).lanes[0].parameters
    card = next(item for item in lane.techniques if item.kind == "poly_period")
    assert isinstance(card, PolyPeriodCard)
    for event in ambient_plan.events:
        if event.kind != "poly_period":
            continue
        offsets = [voice.midi - event.midi for voice in event.voices]
        assert offsets == card.chord_intervals[: len(offsets)]


def test_the_ambient_director_log_is_empty(ambient_plan: Plan) -> None:
    """The station's move declares the pad, and the ambient lane has none."""
    assert ambient_plan.director_log == []


def test_the_drone_spans_the_track(ambient_plan: Plan) -> None:
    for event in ambient_plan.events:
        if isinstance(event, DroneEvent):
            assert event.duration_frames == ambient_plan.duration_frames
