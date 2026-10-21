"""AC-40 to AC-47: the gates, measured on synthetic signals.

BRIEF §11: "Gate tests use synthetic signals (sine, impulse, DC), not full
tracks." Every measurement here is driven by a signal built for the purpose.
"""

from __future__ import annotations

import numpy as np

from indiegen.validate import (
    DC_OFFSET_LIMIT,
    GATES_IN_FORCE,
    SILENCE_FLOOR_LSB,
    TRAILING_SILENCE_LIMIT_S,
    GateFailure,
    GateResult,
    check_gate_2,
    check_gate_8,
    leading_silence_limit,
    run_gates,
)

RATE: int = 44100


def _pcm(samples: np.ndarray) -> np.ndarray:
    return samples.astype(np.int16)


def test_only_the_gates_in_force_are_implemented() -> None:
    assert GATES_IN_FORCE == (2, 8)


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


def test_run_gates_returns_none_when_everything_passes() -> None:
    mix = np.zeros((1024, 2))
    pcm = _pcm(np.zeros((1024, 2)))
    assert run_gates(mix, pcm, "ambient", RATE) is None


def test_run_gates_collects_the_failures() -> None:
    mix = np.zeros((1024, 2))
    pcm = _pcm(np.full((1024, 2), 4000))
    failure = run_gates(mix, pcm, "ambient", RATE)
    assert failure is not None
    assert failure.failures
