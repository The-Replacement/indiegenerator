"""AC-40 to AC-47: the gates, measured on synthetic signals.

BRIEF §11: "Gate tests use synthetic signals (sine, impulse, DC), not full
tracks." Every measurement here is driven by a signal built for the purpose.
"""

from __future__ import annotations

import numpy as np

from indiegen.plan import Plan
from indiegen.validate import (
    DC_OFFSET_LIMIT,
    GATES_IN_FORCE,
    SILENCE_FLOOR_LSB,
    TRAILING_SILENCE_LIMIT_S,
    GateFailure,
    GateResult,
    check_gate_2,
    check_gate_4,
    check_gate_7,
    check_gate_8,
    leading_silence_limit,
    minimum_sections,
    run_gates,
)

RATE: int = 44100


def _pcm(samples: np.ndarray) -> np.ndarray:
    return samples.astype(np.int16)


def test_only_the_gates_in_force_are_implemented() -> None:
    assert GATES_IN_FORCE == (2, 4, 7, 8)


def test_a_clean_signal_passes_gate_two() -> None:
    mix = np.zeros((1024, 2))
    pcm = _pcm(np.zeros((1024, 2)))
    assert check_gate_2(mix, pcm) == []


def test_a_non_finite_sample_fails_gate_two() -> None:
    mix = np.zeros((1024, 2))
    mix[10, 0] = np.nan
    pcm = _pcm(np.zeros((1024, 2)))
    failures = check_gate_2(mix, pcm)
    assert failures
    assert any("non-finite" in failure.check for failure in failures)


def test_a_dc_offset_fails_gate_two() -> None:
    mix = np.zeros((1024, 2))
    mix[:, 0] = 0.5
    pcm = _pcm(np.full((1024, 2), 8000))
    failures = check_gate_2(mix, pcm)
    assert any("DC offset" in failure.check for failure in failures)


def test_a_clipped_signal_fails_gate_two() -> None:
    mix = np.zeros((1024, 2))
    pcm = _pcm(np.full((1024, 2), 32767))
    failures = check_gate_2(mix, pcm)
    assert any("full scale" in failure.check for failure in failures)


def test_the_silence_floor_is_the_briefs_own() -> None:
    assert SILENCE_FLOOR_LSB == 33
    assert DC_OFFSET_LIMIT == 0.001


def test_the_ambient_lane_gets_four_seconds_and_the_others_one() -> None:
    assert leading_silence_limit("ambient") == 4.0
    assert leading_silence_limit("motorik") == 1.0
    assert TRAILING_SILENCE_LIMIT_S == 3.0


def test_a_silent_lead_fails_the_ambient_lane() -> None:
    pcm = _pcm(np.zeros((5 * RATE, 2)))
    failures = check_gate_8(pcm, "ambient", RATE)
    assert any("leading silence" in failure.check for failure in failures)


def test_a_silent_lead_fails_the_other_lanes_harder() -> None:
    pcm = _pcm(np.zeros((2 * RATE, 2)))
    assert check_gate_8(pcm, "ambient", RATE) == []
    failures = check_gate_8(pcm, "motorik", RATE)
    assert any("leading silence" in failure.check for failure in failures)


def test_a_silent_tail_fails_every_lane() -> None:
    pcm = np.zeros((10 * RATE, 2), dtype=np.int16)
    pcm[: 6 * RATE, 0] = 1000
    failures = check_gate_8(pcm, "ambient", RATE)
    assert any("trailing silence" in failure.check for failure in failures)


def test_the_failure_is_data_and_not_an_exception() -> None:
    assert not issubclass(GateFailure, BaseException)
    assert not issubclass(GateResult, BaseException)
    result = GateResult(gate=2, measured=1.0, limit=0.0, check="clipping")
    failure = GateFailure(failures=[result])
    assert failure.failures[0].gate == 2


def _plan(sections: int = 4, frames: int = 60 * RATE) -> Plan:
    """A plan with the given number of sections, tiling the track."""
    from indiegen.plan import SectionPlan

    width = frames // sections
    return Plan(
        version=2,
        format_version=1,
        preset="ambient",
        seed=1042,
        lane="ambient",
        alias="x",
        album="x",
        file_token="x",
        title="x",
        sample_rate=RATE,
        channels=2,
        duration_frames=frames,
        duration_range_frames=[frames, frames],
        tempo_bpm=120,
        frames_per_beat=22050,
        meter_numerator=4,
        meter_denominator=4,
        scale_midi=[60],
        palette=[],
        fx_sends=[],
        techniques=[],
        strategy_deck=[],
        section_count_range=[sections, sections],
        section_count=sections,
        sections=[
            SectionPlan(
                index=index,
                function="build",
                start_frame=index * width,
                end_frame=(index + 1) * width,
                bars=1,
                density=50,
                level_millibels=0,
                motif=[],
                techniques=[],
            )
            for index in range(sections)
        ],
        motif=[],
        title_words=[],
        lane_weights=[],
        dither_seed=1,
        dither_lsb=1,
        master_gain_millibels=0,
        ceiling_millibels=0,
        fade_in_frames=0,
        fade_out_frames=0,
        section_crossfade_frames=0,
        track_number=1,
        delay_sends=[],
        reverb=None,
        events=[],
        director_log=[],
    )


def test_the_ambient_lane_needs_two_sections_and_the_others_four() -> None:
    assert minimum_sections("ambient") == 2
    assert minimum_sections("motorik") == 4


def test_too_few_sections_fails_gate_four() -> None:
    plan = _plan(sections=2)
    plan = plan.model_copy(update={"lane": "motorik"})
    failures = check_gate_4(plan, _pcm(np.zeros((plan.duration_frames, 2))))
    assert any("planned sections" in failure.check for failure in failures)


def test_a_silent_section_was_not_realized() -> None:
    plan = _plan(sections=4, frames=8 * RATE)
    pcm = _pcm(np.zeros((plan.duration_frames, 2)))
    pcm[: 4 * RATE, 0] = 1000
    failures = check_gate_4(plan, pcm)
    assert any("was not realized" in failure.check for failure in failures)


def test_a_flat_piece_has_no_novelty() -> None:
    """A constant tone is not novel, and the gate says so."""
    plan = _plan(sections=4, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = _pcm(np.stack([tone, tone], axis=1) * 8000)
    failures = check_gate_7(plan, pcm, RATE)
    assert any("novelty" in failure.check for failure in failures)


def test_a_piece_that_changes_four_times_has_novelty() -> None:
    """Four arrivals in four sections are four moments of novelty."""
    plan = _plan(sections=4, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = _pcm(np.stack([tone, tone], axis=1) * 8000)
    for index in range(4):
        start = index * 5 * RATE
        half = RATE // 2
        pcm[start : start + half, :] = 12000
        pcm[start + half : start + RATE, :] = -12000
    assert check_gate_7(plan, pcm, RATE) == []


def test_run_gates_returns_none_when_everything_passes() -> None:
    plan = _plan(sections=2, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = _pcm(np.stack([tone, tone], axis=1) * 8000)
    for index in range(2):
        start = index * 10 * RATE
        half = RATE // 2
        pcm[start : start + half, :] = 12000
        pcm[start + half : start + RATE, :] = -12000
    mix = pcm.astype(np.float64) / 32768.0
    assert run_gates(plan, mix, pcm) is None


def test_run_gates_collects_the_failures() -> None:
    plan = _plan(sections=2, frames=8 * RATE)
    mix = np.zeros((plan.duration_frames, 2))
    pcm = _pcm(np.full((plan.duration_frames, 2), 4000))
    failure = run_gates(plan, mix, pcm)
    assert failure is not None
    assert failure.failures
