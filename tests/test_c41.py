"""c41: the declared centroid, the drone in the tension model, and the no-op pins.

Two deliverables under one change id:

* ``indiegen.spectrum.declared_centroid_millihz`` records, per section, the
  amplitude- and duration-weighted centroid of the partials the section
  actually declares. It is unread at runtime; ``0`` is the sentinel for "no
  additive spectrum".
* ``tension.pitched_notes`` learns about ``DroneEvent``, so the richest
  declared spectrum in the tree stops being invisible to the tension model.

The corpus test is marked ``slow`` because it composes 90 tracks.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from indiegen.compose import compose, director, tension
from indiegen.config import load_preset
from indiegen.errors import PlanError
from indiegen.gain import millibels_to_gain
from indiegen.plan import (
    SAMPLE_RATE,
    AmplitudeLfo,
    BassEvent,
    DetuneLfo,
    DriftingPartial,
    DroneEvent,
    Event,
    LeadEvent,
    PadEvent,
    Partial,
    Plan,
    PluckEvent,
    PolyPeriodEvent,
    PolyPeriodVoice,
    Rational,
    RhythmEvent,
)
from indiegen.spectrum import declared_centroid_millihz

DURATION = 44100
SEED = 1042


def _ratio(numerator: int, denominator: int = 1) -> Rational:
    return Rational(numerator=numerator, denominator=denominator)


def _partial(numerator: int, denominator: int = 1, *, millibels: int = 0, detune_cents: int = 0) -> Partial:
    return Partial(
        ratio=_ratio(numerator, denominator),
        amplitude_millibels=millibels,
        detune_cents=detune_cents,
    )


def _pad(
    midi: int = 57,
    *,
    start: int = 0,
    duration: int = DURATION,
    millibels: int = -3000,
    partials: list[Partial] | None = None,
) -> PadEvent:
    return PadEvent(
        instrument="pad",
        kind="pad",
        start_frame=start,
        duration_frames=duration,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=millibels,
        attack_frames=0,
        release_frames=0,
        partials=partials if partials is not None else [_partial(1), _partial(2), _partial(3)],
        lfo_rate=_ratio(1, 10),
        lfo_depth_cents=0,
    )


def _lead(
    midi: int = 69,
    *,
    start: int = 0,
    duration: int = DURATION,
    millibels: int = -14000,
    partials: list[Partial] | None = None,
) -> LeadEvent:
    return LeadEvent(
        instrument="lead",
        kind="lead",
        start_frame=start,
        duration_frames=duration,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=millibels,
        attack_frames=0,
        release_frames=0,
        partials=partials if partials is not None else [_partial(1), _partial(3, 2)],
        lfo_rate=_ratio(1, 10),
        lfo_depth_cents=0,
    )


def _drifting(numerator: int, *, millibels: int, detune_cents: int = 0) -> DriftingPartial:
    return DriftingPartial(
        ratio=_ratio(numerator),
        amplitude_millibels=millibels,
        detune_cents=detune_cents,
        detune_lfo=DetuneLfo(rate=_ratio(1, 10), depth_cents=12),
        amplitude_lfo=AmplitudeLfo(rate=_ratio(1, 10), depth_millibels=4000),
    )


def _drone(
    midi: int = 45,
    *,
    start: int = 0,
    duration: int = DURATION,
    partials: list[DriftingPartial] | None = None,
) -> DroneEvent:
    return DroneEvent(
        instrument="drone",
        kind="drone",
        start_frame=start,
        duration_frames=duration,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        partials=partials if partials is not None else [_drifting(1, millibels=-3000), _drifting(2, millibels=-4200)],
        noise_seed=7,
    )


def _poly_period(midi: int = 57, *, start: int = 0, duration: int = DURATION) -> PolyPeriodEvent:
    return PolyPeriodEvent(
        instrument="poly_period",
        kind="poly_period",
        start_frame=start,
        duration_frames=duration,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        voices=[PolyPeriodVoice(period_frames=4410, on_frames=2205, phase_frames=0, midi=midi)],
        partials=[_partial(1, millibels=-3000), _partial(2, millibels=-3000)],
    )


def _pluck(midi: int = 60, *, start: int = 0, duration: int = DURATION) -> PluckEvent:
    return PluckEvent(
        instrument="pluck",
        kind="pluck",
        start_frame=start,
        duration_frames=duration,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=-6000,
        attack_frames=0,
        release_frames=0,
        feedback=_ratio(9, 10),
        brightness=_ratio(1, 2),
        pluck_position_permille=300,
        detune_cents=0,
        excitation_seed=11,
    )


# --- the arithmetic anchors -------------------------------------------------


def test_a_harmonic_pad_declares_its_own_octave_series() -> None:
    """midi 57 with 1/1, 2/1, 3/1 is (220 + 440 + 660) / 3 = 440 Hz, exactly."""
    assert declared_centroid_millihz([_pad(57)], 0, 240 * DURATION) == 440_000


def test_the_anchor_scales_with_the_root() -> None:
    """The anchor is 12-TET plus exact ratios, not a table.

    The stack 1/1, 2/1, 3/1 means 2x the fundamental: 220 Hz reads 440000 and
    E4 reads 659255. The octave above that is exactly double again.
    """
    stack = [_partial(1), _partial(2), _partial(3)]
    assert declared_centroid_millihz([_pad(64, partials=stack)], 0, DURATION) == 659_255
    assert declared_centroid_millihz([_pad(76, partials=stack)], 0, DURATION) == 1_318_510


def test_an_exact_ratio_moves_the_centroid_off_12_tet() -> None:
    """A just 3/2 is 701.955 cents, so it sits below the octave it replaces."""
    third = declared_centroid_millihz([_pad(57, partials=[_partial(1), _partial(3, 2)])], 0, DURATION)
    octave = declared_centroid_millihz([_pad(57, partials=[_partial(1), _partial(2)])], 0, DURATION)
    assert third < octave
    assert third == 275_000


def test_a_detuned_partial_moves_the_centroid_by_exactly_its_cents() -> None:
    """+100 cents on the upper partial is 2 ** (100/1200) on its term, no more."""
    plain = declared_centroid_millihz([_pad(57, partials=[_partial(1), _partial(2)])], 0, DURATION)
    sharp = declared_centroid_millihz([_pad(57, partials=[_partial(1), _partial(2, detune_cents=100)])], 0, DURATION)
    assert plain == 330_000
    assert sharp == pytest.approx(1000 * 220 * (1 + 2 * 2 ** (100 / 1200)) / 2, abs=1)


# --- the sentinel -----------------------------------------------------------


def test_no_event_declares_no_spectrum() -> None:
    """An empty window is the sentinel, not an error."""
    assert declared_centroid_millihz([], 0, DURATION) == 0


def test_events_outside_the_window_do_not_count() -> None:
    pad = _pad(57, start=2 * DURATION, duration=DURATION)
    assert declared_centroid_millihz([pad], 0, DURATION) == 0


def test_a_parametric_voice_declares_no_spectrum() -> None:
    """A pluck has feedback, brightness and position - no partials, so no field."""
    assert declared_centroid_millihz([_pluck(60), _pluck(67)], 0, DURATION) == 0


# --- the window -------------------------------------------------------------


def test_a_straddling_event_counts_in_both_sections() -> None:
    """The predicate is overlap, weighted by the overlap itself.

    The same pad straddles a boundary; each section declares it with its own
    share of the frames, so the field is the same either way and non-zero in
    both - this is ``_instrumentation``'s predicate, not containment.
    """
    pad = _pad(57, start=DURATION - 1, duration=2)
    assert declared_centroid_millihz([pad], 0, DURATION) > 0
    assert declared_centroid_millihz([pad], 0, 2 * DURATION) == 440_000


def test_a_non_positive_window_raises() -> None:
    with pytest.raises(PlanError):
        declared_centroid_millihz([_pad()], DURATION, DURATION)
    with pytest.raises(PlanError):
        declared_centroid_millihz([_pad()], DURATION, 0)


# --- duration and level are both weights ------------------------------------


def test_the_longer_event_dominates_the_mean() -> None:
    """Duration weighting: a 3 s pad and a 1 s pad average 3:1, not 1:1."""
    low = _pad(45, start=0, duration=3 * DURATION, partials=[_partial(1)])
    high = _pad(69, start=0, duration=DURATION, partials=[_partial(1)])
    alone_low = declared_centroid_millihz([low], 0, 4 * DURATION)
    alone_high = declared_centroid_millihz([high], 0, 4 * DURATION)
    mixed = declared_centroid_millihz([low, high], 0, 4 * DURATION)
    assert alone_low == 110_000
    assert alone_high == 440_000
    assert abs(mixed - (3 * alone_low + alone_high) // 4) <= 1


def test_the_event_level_is_part_of_the_weight() -> None:
    """The convention C6 states, which a single event cannot show.

    A uniform level offset is invisible inside one voice - it scales every
    partial of that voice alike - so the only place the event level is
    material is between voices. A lead 14 dB under the pad may not dominate it.
    """
    pad = _pad(45, partials=[_partial(1)])
    lead = _lead(81, partials=[_partial(1)])
    pad_only = declared_centroid_millihz([pad], 0, DURATION)
    assert pad_only == 110_000
    quiet = declared_centroid_millihz([pad, lead], 0, DURATION)
    loud = declared_centroid_millihz([pad, _lead(81, millibels=0, partials=[_partial(1)])], 0, DURATION)
    assert pad_only < quiet < loud
    # -14 dB is a gain of 10 ** (-14/20) = 0.1995, so the lead owns 22% of the
    # mean, not the 50% a partial-only weight would give it.
    share = millibels_to_gain(-14000) / (millibels_to_gain(-3000) + millibels_to_gain(-14000))
    assert share == pytest.approx(0.2199, abs=1e-4)
    assert quiet == pytest.approx(110_000 + share * (880_000 - 110_000), abs=1)


def test_the_drone_root_transposed_up_raises_the_field() -> None:
    """A drone is a declared spectrum; +7 semitones is a different one."""
    low = declared_centroid_millihz([_drone(45)], 0, DURATION)
    high = declared_centroid_millihz([_drone(52)], 0, DURATION)
    assert 0 < low < high
    assert high / low == pytest.approx(2 ** (7 / 12), rel=1e-4)


def test_a_poly_period_counts_every_voice() -> None:
    """One voice is the anchor; two voices an octave apart is the same mean."""
    one = _poly_period(57)
    two = one.model_copy(
        update={
            "voices": [
                PolyPeriodVoice(period_frames=4410, on_frames=2205, phase_frames=0, midi=57),
                PolyPeriodVoice(period_frames=5512, on_frames=1102, phase_frames=384, midi=69),
            ]
        }
    )
    alone = declared_centroid_millihz([one], 0, DURATION)
    both = declared_centroid_millihz([two], 0, DURATION)
    assert alone == 330_000
    assert both == pytest.approx(495_000, abs=1)


# --- plan level: the field on real material ---------------------------------


@pytest.fixture(scope="module")
def kosmische_240() -> Plan:
    return director(compose(load_preset("kosmische"), SEED, 240 * SAMPLE_RATE))


@pytest.fixture(scope="module")
def ambient_240() -> Plan:
    return director(compose(load_preset("ambient"), SEED, 240 * SAMPLE_RATE))


def test_a_lane_without_an_additive_card_declares_nothing() -> None:
    """AC-3: the sentinel is exact, not approximate - indie-noise has no pad,
    lead, poly-period or drone card at all. (dub-electronic now carries a
    sustained drone bed, so it declares a spectrum.)"""
    for lane in ("indie-noise",):
        plan = director(compose(load_preset(lane), SEED, 60 * SAMPLE_RATE))
        assert [section.declared_centroid_millihz for section in plan.sections] == [0] * len(plan.sections)


def test_a_drone_lane_declares_a_spectrum_in_every_section() -> None:
    plan = director(compose(load_preset("kosmische"), SEED, 60 * SAMPLE_RATE))
    assert all(section.declared_centroid_millihz > 0 for section in plan.sections)


def test_the_director_re_derives_the_field(kosmische_240: Plan, composed_plan: Plan) -> None:
    """A directed plan may not describe its pre-Director material.

    Motorik's deck contains transpose_up_fourth, which rewrites pad, drone and
    lead midi. The field is re-derived from the final events, so the two plans
    disagree wherever a move landed on an additive voice.
    """
    motorik = director(compose(load_preset("motorik"), SEED, 60 * SAMPLE_RATE))
    before = compose(load_preset("motorik"), SEED, 60 * SAMPLE_RATE)
    assert [s.declared_centroid_millihz for s in before.sections] == [
        349_699,
        329_723,
        247_251,
        349_699,
        293_524,
    ]
    assert [s.declared_centroid_millihz for s in motorik.sections] == [
        349_699,
        329_723,
        247_251,
        349_699,
        355_892,
    ]
    assert composed_plan.sections[3].declared_centroid_millihz == 349_699


def test_ac4_transposing_the_drone_raises_every_section(kosmische_240: Plan) -> None:
    """AC-4: the field answers to the drone root, and the timbre table does not."""
    shifted = _with_drone_shift(kosmische_240, 7)
    before = [section.declared_centroid_millihz for section in kosmische_240.sections]
    after = [declared_centroid_millihz(shifted.events, s.start_frame, s.end_frame) for s in kosmische_240.sections]
    assert before == [229_239, 155_182, 130_517, 258_988, 136_122, 172_486]
    assert after == [343_471, 232_510, 195_555, 355_873, 183_594, 258_438]
    assert all(high > low for low, high in zip(before, after, strict=True))
    assert [section.centroid_hz for section in kosmische_240.sections] == [994, 1824, 995, 1878, 1674, 862]
    assert [section.centroid_hz for section in shifted.sections] == [994, 1824, 995, 1878, 1674, 862]


def test_ac5_transposing_the_poly_period_raises_every_section(ambient_240: Plan) -> None:
    """AC-5: the same response through the other additive voice."""
    shifted = _with_poly_period_shift(ambient_240, 7)
    before = [section.declared_centroid_millihz for section in ambient_240.sections]
    after = [declared_centroid_millihz(shifted.events, s.start_frame, s.end_frame) for s in ambient_240.sections]
    assert before == [132_206, 132_332, 146_565, 151_974]
    assert after == [177_987, 177_098, 193_496, 200_298]
    assert all(high > low for low, high in zip(before, after, strict=True))
    assert [section.centroid_hz for section in ambient_240.sections] == [560, 560, 560, 560]


def test_ac6_the_drone_reaches_the_tension_model(kosmische_240: Plan) -> None:
    """AC-6: the falsifier. Before this change the two FeatureSets were identical.

    Pitch falls in every section: the drone is the lowest voice and it enters a
    duration-weighted mean. Roughness is a MEAN over sounding pairs, so the
    drone does not simply add roughness - it RISES where it is the section's
    second note and FALLS where a consonant low voice dilutes a busy section,
    and it stays 0 in the outro where the drone sounds alone at every sample
    (fewer than two notes is not a pair). The measured directions are recorded
    here as evidence, and the handoff carries the reasoning.
    """
    events = kosmische_240.events
    without = _pitched_without_drone(events)
    roughness: list[tuple[int, int]] = []
    for section in kosmische_240.sections:
        before = tension.section_features(
            events, section.start_frame, section.end_frame, section.bars, section.level_millibels, without
        )
        after = tension.section_features(
            events, section.start_frame, section.end_frame, section.bars, section.level_millibels
        )
        assert before != after
        assert after.pitch < before.pitch
        roughness.append((before.roughness, after.roughness))
    assert roughness == [(0, 2000), (0, 2750), (0, 1000), (3667, 1571), (6500, 1238), (0, 0)]


def _with_drone_shift(plan: Plan, semitones: int) -> Plan:
    return plan.model_copy(
        update={
            "events": [
                event.model_copy(update={"midi": event.midi + semitones}) if isinstance(event, DroneEvent) else event
                for event in plan.events
            ]
        }
    )


def _with_poly_period_shift(plan: Plan, semitones: int) -> Plan:
    return plan.model_copy(
        update={
            "events": [
                event.model_copy(
                    update={
                        "voices": [voice.model_copy(update={"midi": voice.midi + semitones}) for voice in event.voices]
                    }
                )
                if isinstance(event, PolyPeriodEvent)
                else event
                for event in plan.events
            ]
        }
    )


def _pitched_without_drone(events: Sequence[Event]) -> list[tuple[int, int, int]]:
    """tension.pitched_notes as it stood before the drone branch, for the falsifier.

    Written out rather than monkeypatched so the test states the old predicate
    instead of reaching into the module it is testing.
    """
    out: list[tuple[int, int, int]] = []
    for event in events:
        if isinstance(event, PluckEvent | PadEvent | LeadEvent):
            out.append((event.start_frame, event.start_frame + event.duration_frames, event.midi))
        elif isinstance(event, PolyPeriodEvent):
            out.extend(
                (event.start_frame, event.start_frame + event.duration_frames, voice.midi) for voice in event.voices
            )
        elif isinstance(event, RhythmEvent):
            out.extend(
                (hit.frame, hit.frame + tension.BASS_HIT_FRAMES, hit.midi)
                for hit in event.hits
                if isinstance(hit, BassEvent)
            )
    return out
