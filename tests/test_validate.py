"""AC-40 to AC-47, AC-3, AC-6, AC-7, AC-8, AC-12, AC-18: the gates.

BRIEF §11: "Gate tests use synthetic signals (sine, impulse, DC), not full
tracks." Every measurement here is driven by a signal built for the purpose.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pytest

from indiegen.plan import MotifAppearance, MotifCell, MotifNote, Plan
from indiegen.validate import (
    DC_OFFSET_LIMIT,
    GATES_IN_FORCE,
    SILENCE_FLOOR_LSB,
    TENSION_CORRELATION_LIMIT,
    TRAILING_SILENCE_LIMIT_S,
    GateFailure,
    GateResult,
    _pcm_section_millibels,
    _pcm_section_onsets,
    check_gate_1,
    check_gate_2,
    check_gate_3,
    check_gate_4,
    check_gate_5,
    check_gate_6,
    check_gate_7,
    check_gate_8,
    check_gate_9,
    check_gate_10,
    check_gate_11,
    check_gate_12,
    check_gate_13,
    check_gate_14,
    leading_silence_limit,
    minimum_sections,
    run_gates,
    tension_correlation,
)

RATE: int = 44100


def _pcm(samples: np.ndarray) -> np.ndarray:
    return samples.astype(np.int16)


def test_only_the_gates_in_force_are_implemented() -> None:
    assert GATES_IN_FORCE == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)


def _tone(seconds: float = 6.0, amplitude: float = 5800.0) -> np.ndarray:
    """A tone at the target loudness, in the int16 scale."""
    times = np.arange(int(seconds * RATE)) / RATE
    wave = amplitude * np.sin(2.0 * np.pi * 220.0 * times)
    return _pcm(np.stack([wave, wave], axis=1))


def test_a_track_at_the_target_loudness_passes_gate_one() -> None:
    assert check_gate_1(_tone(), RATE) == []


def test_a_quiet_track_fails_gate_one() -> None:
    failures = check_gate_1(_tone(amplitude=1000.0), RATE)
    assert any("loudness" in failure.check for failure in failures)


def test_a_loud_track_fails_gate_one() -> None:
    failures = check_gate_1(_tone(amplitude=30000.0), RATE)
    assert any("loudness" in failure.check or "true peak" in failure.check for failure in failures)


def test_a_duration_inside_the_declared_range_passes_gate_three() -> None:
    plan = _plan(sections=2, frames=20 * RATE)
    assert check_gate_3(plan) == []


def test_a_duration_outside_the_declared_range_fails_gate_three() -> None:
    plan = _plan(sections=2, frames=20 * RATE)
    plan = plan.model_copy(update={"duration_range_frames": [30 * RATE, 40 * RATE]})
    failures = check_gate_3(plan)
    assert any("duration" in failure.check for failure in failures)


def test_a_mono_low_band_passes_gate_nine() -> None:
    assert check_gate_9(_tone(), RATE) == []


def test_a_low_band_that_cancels_in_mono_fails_gate_nine() -> None:
    """A low band that is out of phase between the channels loses its bass."""
    times = np.arange(int(6.0 * RATE)) / RATE
    bass = 20000.0 * np.sin(2.0 * np.pi * 60.0 * times)
    signal = np.stack([bass, -bass], axis=1)
    failures = check_gate_9(_pcm(signal), RATE)
    assert any("mono fold-down" in failure.check for failure in failures)


def test_the_same_hash_passes_gate_ten_and_a_different_one_does_not() -> None:
    assert check_gate_10("abc", "abc") == []
    failures = check_gate_10("abc", "def")
    assert failures and failures[0].gate == 10


def test_our_loudness_against_ffmpeg_passes_gate_eleven() -> None:
    assert check_gate_11(-16.0, -16.1) == []


def test_our_loudness_against_ffmpeg_fails_gate_eleven() -> None:
    failures = check_gate_11(-16.0, -16.5)
    assert failures and failures[0].gate == 11


def _comparison(**overrides: float) -> tuple[float, float, int, float]:
    values = {
        "lufs_before": -16.0,
        "lufs_after": -16.2,
        "clipped": 0,
        "correlation": 0.99,
    }
    values.update(overrides)
    return (
        values["lufs_before"],
        values["lufs_after"],
        int(values["clipped"]),
        values["correlation"],
    )


def test_a_clean_roundtrip_passes_gate_twelve() -> None:
    assert check_gate_12(*_comparison()) == []


def test_a_roundtrip_that_moves_the_loudness_fails_gate_twelve() -> None:
    failures = check_gate_12(*_comparison(lufs_after=-17.0))
    assert any("loudness" in failure.check for failure in failures)


def test_a_roundtrip_that_clips_fails_gate_twelve() -> None:
    failures = check_gate_12(*_comparison(clipped=12))
    assert any("clipping" in failure.check for failure in failures)


def test_a_roundtrip_that_collapses_fails_gate_twelve() -> None:
    failures = check_gate_12(*_comparison(correlation=0.05))
    assert any("correlation" in failure.check for failure in failures)


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


def _plan(
    sections: int = 4,
    frames: int = 60 * RATE,
    levels: list[int] | None = None,
    centroids: list[int] | None = None,
    pulse: Literal["bars", "seconds"] = "bars",
) -> Plan:
    """A plan with the given number of sections, tiling the track."""
    from indiegen.plan import SectionPlan

    width = frames // sections
    section_levels = levels if levels is not None else [0] * sections
    section_centroids = centroids if centroids is not None else [1000] * sections
    return Plan(
        version=3,
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
        form="full",
        tempo_bpm=120,
        frames_per_beat=22050,
        meter_numerator=4,
        meter_denominator=4,
        pulse=pulse,
        scale_midi=[60],
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
                level_millibels=section_levels[index],
                techniques=[],
                instrumentation=["pad"],
                mode="dorian",
                root_midi=38,
                texture="open",
                reprise_of=-1,
                centroid_hz=section_centroids[index],
            )
            for index in range(sections)
        ],
        motif=MotifCell(notes=[MotifNote(midi=38, duration_frames=22050)]),
        motif_appearances=[],
        deja_vu_replay_permille=[],
        title_words=[],
        lane_weights=[],
        dither_seed=1,
        dither_lsb=1,
        target_lufs_millibels=-16000,
        ceiling_millibels=0,
        bus_gains=[],
        fade_in_frames=0,
        fade_out_frames=0,
        section_crossfade_frames=0,
        track_number=1,
        delay_sends=[],
        reverb=None,
        frippertronics=None,
        dub_chain=None,
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


def test_a_piece_that_falls_to_silence_is_novel() -> None:
    """A section that gets quieter is novelty: the detector must not be one-sided.

    Four sections: a tone, silence, a quieter tone, silence. The three
    boundaries are two falls and one rise. A half-wave rectified flux counts
    only the rise, so it finds one peak against a limit of three; the
    two-sided detector counts the two boundary falls as well.
    """
    plan = _plan(sections=4, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = np.zeros((plan.duration_frames, 2))
    for index, amplitude in ((0, 8000.0), (2, 4000.0)):
        start = index * 5 * RATE
        stop = start + 5 * RATE
        pcm[start:stop, :] = (amplitude * tone[start:stop])[:, np.newaxis]
    assert check_gate_7(plan, _pcm(pcm), RATE) == []


def test_a_fall_that_is_not_a_section_boundary_is_not_novelty() -> None:
    """A drop inside a section is not a section change."""
    plan = _plan(sections=2, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = np.zeros((plan.duration_frames, 2))
    pcm[: 2 * RATE, :] = (8000.0 * tone[: 2 * RATE])[:, np.newaxis]
    assert check_gate_7(plan, _pcm(pcm), RATE) != []


def test_the_energy_trajectory_has_to_follow_the_plan() -> None:
    """Gate 5: the delivered energy follows the planned level curve."""
    plan = _plan(sections=4, frames=20 * RATE, levels=[0, -6000, 0, -6000])
    time = np.arange(plan.duration_frames) / RATE
    mix = np.zeros((plan.duration_frames, 2))
    for section in plan.sections:
        level = 10.0 ** (section.level_millibels / 2000.0)
        window = level * np.sin(2.0 * np.pi * 220.0 * time[section.start_frame : section.end_frame])
        mix[section.start_frame : section.end_frame, :] = window[:, np.newaxis]
    assert check_gate_5(plan, mix) == []


def test_an_energy_trajectory_against_the_plan_fails_gate_five() -> None:
    """The plan says the piece gets quieter, and it does not: the gate says so."""
    plan = _plan(sections=4, frames=20 * RATE, levels=[0, -6000, 0, -6000])
    time = np.arange(plan.duration_frames) / RATE
    mix = np.zeros((plan.duration_frames, 2))
    for section in plan.sections:
        window = 0.5 * np.sin(2.0 * np.pi * 220.0 * time[section.start_frame : section.end_frame])
        mix[section.start_frame : section.end_frame, :] = window[:, np.newaxis]
    failures = check_gate_5(plan, mix)
    assert any("energy trajectory" in failure.check for failure in failures)


def test_a_plan_that_predicted_no_movement_is_not_failed_for_it() -> None:
    """A flat plan is not a failed plan."""
    plan = _plan(sections=4, frames=20 * RATE, levels=[0, 0, 0, 0])
    time = np.arange(plan.duration_frames) / RATE
    mix = np.stack([np.sin(2.0 * np.pi * 220.0 * time)] * 2, axis=1)
    assert check_gate_5(plan, mix) == []


def test_the_timbre_trajectory_has_to_follow_the_plan() -> None:
    """Gate 6: a bright section sounds bright."""
    plan = _plan(sections=2, frames=20 * RATE, centroids=[500, 6000])
    time = np.arange(plan.duration_frames) / RATE
    mix = np.zeros((plan.duration_frames, 2))
    first, second = plan.sections
    low = 0.5 * np.sin(2.0 * np.pi * 500.0 * time[first.start_frame : first.end_frame])
    high = 0.5 * np.sin(2.0 * np.pi * 6000.0 * time[second.start_frame : second.end_frame])
    mix[first.start_frame : first.end_frame, :] = low[:, np.newaxis]
    mix[second.start_frame : second.end_frame, :] = high[:, np.newaxis]
    assert check_gate_6(plan, mix) == []


def test_a_timbre_trajectory_against_the_plan_fails_gate_six() -> None:
    plan = _plan(sections=2, frames=20 * RATE, centroids=[500, 6000])
    time = np.arange(plan.duration_frames) / RATE
    mix = np.stack([0.5 * np.sin(2.0 * np.pi * 500.0 * time)] * 2, axis=1)
    failures = check_gate_6(plan, mix)
    assert any("timbre trajectory" in failure.check for failure in failures)


def test_a_static_plan_wants_a_static_timbre() -> None:
    """A plan that declared a static timbre fails a moving one."""
    plan = _plan(sections=2, frames=20 * RATE, centroids=[1000, 1000])
    time = np.arange(plan.duration_frames) / RATE
    mix = np.zeros((plan.duration_frames, 2))
    first, second = plan.sections
    low = 0.5 * np.sin(2.0 * np.pi * 500.0 * time[first.start_frame : first.end_frame])
    high = 0.5 * np.sin(2.0 * np.pi * 6000.0 * time[second.start_frame : second.end_frame])
    mix[first.start_frame : first.end_frame, :] = low[:, np.newaxis]
    mix[second.start_frame : second.end_frame, :] = high[:, np.newaxis]
    failures = check_gate_6(plan, mix)
    assert any("static plan" in failure.check for failure in failures)


def test_the_motif_has_to_come_back_transformed() -> None:
    """Gate 13: fewer than three transformed appearances is a failure."""
    plan = _plan(sections=4, frames=20 * RATE)
    assert check_gate_13(plan) != []
    appearances = [
        MotifAppearance(
            section_index=index,
            transform="transpose" if index else "identity",
            parameter=5,
            start_frame=index * RATE,
            notes=[38, 41],
            durations=[22050, 22050],
        )
        for index in range(4)
    ]
    plan = plan.model_copy(update={"motif_appearances": appearances})
    assert not [failure for failure in check_gate_13(plan) if "motif" in failure.check]


def test_a_deja_vu_that_never_moved_is_a_failure() -> None:
    plan = _plan(sections=4, frames=20 * RATE)
    plan = plan.model_copy(update={"deja_vu_replay_permille": [150, 150, 150, 150]})
    failures = check_gate_13(plan)
    assert any("deja-vu" in failure.check for failure in failures)
    plan = plan.model_copy(update={"deja_vu_replay_permille": [150, 300, 500, 850]})
    assert not [failure for failure in check_gate_13(plan) if "deja-vu" in failure.check]


def test_a_director_that_never_fires_is_a_failure() -> None:
    """A pulsed lane has to have an arranger, at least once every 32 bars."""
    plan = _plan(sections=4, frames=20 * RATE, pulse="bars")
    failures = check_gate_13(plan)
    assert any("director fires" in failure.check for failure in failures)


def test_run_gates_returns_none_when_everything_passes() -> None:
    plan = _plan(sections=2, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    # A tone whose level ramps across the middle: there is a moment of
    # novelty in it, and its timbre does not move. Its level is the target
    # loudness, so the loudness gate has nothing to say about it.
    ramp = np.clip((time - 9.0) / 2.0, 0.0, 1.0) * 0.8 + 0.2
    tone = ramp * np.sin(2.0 * np.pi * 220.0 * time)
    pcm = _pcm(np.stack([tone, tone], axis=1) * 5800)
    mix = pcm.astype(np.float64) / 32768.0
    appearances = [
        MotifAppearance(
            section_index=index,
            transform="transpose",
            parameter=5,
            start_frame=index * RATE,
            notes=[38, 41],
            durations=[22050, 22050],
        )
        for index in range(3)
    ]
    plan = plan.model_copy(
        update={
            "motif_appearances": appearances,
            "deja_vu_replay_permille": [150, 850],
            "pulse": "seconds",
        }
    )
    assert run_gates(plan, mix, pcm) is None


def test_run_gates_collects_the_failures() -> None:
    plan = _plan(sections=2, frames=8 * RATE)
    mix = np.zeros((plan.duration_frames, 2))
    pcm = _pcm(np.full((plan.duration_frames, 2), 4000))
    failure = run_gates(plan, mix, pcm)
    assert failure is not None
    assert failure.failures


def test_the_promoted_limit_is_the_earned_threshold() -> None:
    """Gate 14 is promoted: the limit is the harness's pooled T, verbatim."""
    # docs/handoff/c10-tension-gate.json, pooled.T over 637 sections.
    assert TENSION_CORRELATION_LIMIT == 0.1499084456057718


def test_the_pcm_loudness_tracks_section_rms() -> None:
    """Gate 14 Slice 1: a louder section reads louder, in millibels."""
    plan = _plan(sections=4, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = np.zeros((plan.duration_frames, 2))
    amplitudes = [2000.0, 8000.0, 4000.0, 12000.0]
    for index, amplitude in enumerate(amplitudes):
        start = index * 5 * RATE
        stop = start + 5 * RATE
        pcm[start:stop, :] = (amplitude * tone[start:stop])[:, np.newaxis]
    read = [_pcm_section_millibels(_pcm(pcm), section.start_frame, section.end_frame) for section in plan.sections]
    assert read[0] < read[2] < read[1] < read[3]
    # Silence reads the 1e-9 floor, as a constant RMS gain offset would.
    silent = _pcm_section_millibels(_pcm(np.zeros((RATE, 2))), 0, RATE)
    assert silent == 20000.0 * np.log10(1e-9)


def test_the_pcm_onset_counts_the_novelty_peaks() -> None:
    """Gate 14 Slice 1: the gate-7 rises, counted per bar."""
    plan = _plan(sections=4, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = _pcm(np.stack([tone, tone], axis=1) * 8000)
    for index in range(4):
        start = index * 5 * RATE
        half = RATE // 2
        pcm[start : start + half, :] = 12000
        pcm[start + half : start + RATE, :] = -12000
    onsets = _pcm_section_onsets(pcm, RATE, list(plan.sections))
    assert all(value >= 0 for value in onsets)
    assert sum(onsets) > 0


def test_exempt_plan_passes_gate_14() -> None:
    """Gate 14: an exempt flat plan passes whatever the PCM."""
    plan = _plan(sections=4, frames=20 * RATE)
    time = np.arange(plan.duration_frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = _pcm(np.stack([tone, tone], axis=1) * 8000)
    correlation = tension_correlation(plan, pcm)
    assert -1.0 <= correlation <= 1.0
    assert check_gate_14(plan, pcm) == []


def _tension_plan(
    tensions: list[int],
    deltas: list[int] | None = None,
    corridors: list[tuple[int, int]] | None = None,
) -> Plan:
    """A flat-section plan whose sections carry the given tension walk."""
    plan = _plan(sections=len(tensions), frames=20 * RATE)
    sections = []
    for index, section in enumerate(plan.sections):
        update: dict[str, int] = {"tension_permille": tensions[index]}
        if deltas is not None:
            update["tension_delta_permille"] = deltas[index]
        if corridors is not None:
            update["tension_delta_min_permille"], update["tension_delta_max_permille"] = corridors[index]
        sections.append(section.model_copy(update=update))
    return plan.model_copy(update={"sections": sections})


def _ramp_pcm(amplitudes: list[float]) -> np.ndarray:
    """One tone per section at the given amplitudes, as int16 stereo PCM."""
    frames = 5 * RATE * len(amplitudes)
    time = np.arange(frames) / RATE
    tone = np.sin(2.0 * np.pi * 220.0 * time)
    pcm = np.zeros((frames, 2))
    for index, amplitude in enumerate(amplitudes):
        start = index * 5 * RATE
        pcm[start : start + 5 * RATE, :] = (amplitude * tone[start : start + 5 * RATE])[:, np.newaxis]
    return _pcm(pcm)


def test_fewer_than_three_sections_is_exempt() -> None:
    """AC-2.1: N < 3 reads 1.0 and does not fail."""
    for sections in (1, 2):
        plan = _plan(sections=sections, frames=20 * RATE)
        pcm = _pcm(np.zeros((plan.duration_frames, 2)))
        assert tension_correlation(plan, pcm) == 1.0
        assert check_gate_14(plan, pcm) == []


def test_a_flat_planned_tension_is_exempt() -> None:
    """AC-2.2: flat is judged on the planned permille, not the measured one."""
    # Mean 500, spread 25: exactly 0.05 * mean, so flat by the gate-6 rule.
    plan = _tension_plan([488, 513, 500, 499])
    pcm = _ramp_pcm([8000.0, 8000.0, 8000.0, 8000.0])
    assert tension_correlation(plan, pcm) == 1.0
    assert check_gate_14(plan, pcm) == []
    # One permille wider is no longer flat: a flat measured curve reads 0.0.
    wider = _tension_plan([487, 513, 500, 499])
    assert tension_correlation(wider, pcm) == 0.0


def test_a_flat_measured_curve_is_not_exempt() -> None:
    """The parent correction: flat measured does not buy the exemption."""
    plan = _tension_plan([500, 600, 700, 800])
    pcm = _ramp_pcm([8000.0, 8000.0, 8000.0, 8000.0])
    assert tension_correlation(plan, pcm) == 0.0


def test_a_corridor_miss_alone_never_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2.3: a miss with a passing Pearson does not fail, even armed."""
    plan = _tension_plan(
        [500, 550, 600, 650], deltas=[0, 500, 500, 500], corridors=[(-1000, 1000), (0, 10), (0, 10), (0, 10)]
    )
    pcm = _ramp_pcm([2000.0, 4000.0, 8000.0, 12000.0])
    assert tension_correlation(plan, pcm) > 0.9
    import indiegen.validate as validate

    monkeypatch.setattr(validate, "TENSION_CORRELATION_LIMIT", 0.5)
    assert check_gate_14(plan, pcm) == []


def test_a_low_correlation_fails_exactly_once_when_armed(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2.3: contained but uncorrelated fails with exactly one gate-14 result."""
    plan = _tension_plan([500, 600, 700, 800], deltas=[0, 100, 100, 100], corridors=[(-1000, 1000)] * 4)
    pcm = _ramp_pcm([8000.0, 8000.0, 8000.0, 8000.0])
    assert tension_correlation(plan, pcm) == 0.0
    import indiegen.validate as validate

    monkeypatch.setattr(validate, "TENSION_CORRELATION_LIMIT", 0.5)
    failures = check_gate_14(plan, pcm)
    assert len(failures) == 1
    assert failures[0].gate == 14
    assert failures[0].measured == 0.0
    assert failures[0].limit == 0.5
    assert failures[0].check == "tension trajectory correlation"


def test_mutating_the_planned_events_moves_the_measured_curve() -> None:
    """AC-5.2: pitch and roughness are carried from the plan, not the PCM."""
    from indiegen.plan import PluckEvent, Rational

    def _pluck(midi: int, start: int) -> PluckEvent:
        return PluckEvent(
            instrument="pluck",
            kind="pluck",
            start_frame=start,
            duration_frames=5 * RATE,
            midi=midi,
            pan_permille=0,
            amplitude_millibels=-6000,
            attack_frames=0,
            release_frames=0,
            feedback=Rational(numerator=9, denominator=10),
            brightness=Rational(numerator=1, denominator=2),
            pluck_position_permille=300,
            detune_cents=0,
            excitation_seed=11,
        )

    plan = _tension_plan([500, 550, 600, 650])
    pcm = _ramp_pcm([2000.0, 4000.0, 8000.0, 12000.0])
    base = tension_correlation(plan, pcm)
    upward = plan.model_copy(
        update={"events": [_pluck(40, 0), _pluck(50, 5 * RATE), _pluck(60, 10 * RATE), _pluck(70, 15 * RATE)]}
    )
    downward = plan.model_copy(
        update={"events": [_pluck(70, 0), _pluck(60, 5 * RATE), _pluck(50, 10 * RATE), _pluck(40, 15 * RATE)]}
    )
    assert tension_correlation(upward, pcm) != base
    assert tension_correlation(downward, pcm) != base
    assert tension_correlation(upward, pcm) != tension_correlation(downward, pcm)


def test_gate_14_is_in_the_active_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-5.5: gate 14 is promoted, live in run_gates, and fails when low."""
    assert GATES_IN_FORCE == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
    assert 14 in GATES_IN_FORCE
    import indiegen.validate as validate

    flat_plan = _tension_plan([500, 500, 500, 500])
    flat_pcm = _ramp_pcm([8000.0, 8000.0, 8000.0, 8000.0])
    flat_mix = flat_pcm.astype(np.float64) / 32768.0
    flat_failure = run_gates(flat_plan, flat_mix, flat_pcm)
    assert flat_failure is None or not [result for result in flat_failure.failures if result.gate == 14]
    plan = _tension_plan([500, 600, 700, 800])
    pcm = _ramp_pcm([8000.0, 8000.0, 8000.0, 8000.0])
    mix = pcm.astype(np.float64) / 32768.0
    monkeypatch.setattr(validate, "TENSION_CORRELATION_LIMIT", 0.99)
    failure = run_gates(plan, mix, pcm)
    assert failure is not None
    assert [result for result in failure.failures if result.gate == 14]
