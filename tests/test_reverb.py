"""AC-4, AC-35, AC-36, AC-37, AC-60: the short reverb."""

from __future__ import annotations

import math

import numpy as np

from indiegen.fx.reverb import render_reverb, reverb_state
from indiegen.plan import Rational, ReverbSpec

RATE: int = 44100

SPEC = ReverbSpec(
    comb_delays_frames=[1557, 1617, 1491, 1422, 1277, 1356, 1397, 1129],
    comb_feedback=Rational(numerator=84, denominator=100),
    damping=Rational(numerator=2, denominator=100),
    allpass_delays_frames=[556, 441, 341, 225],
    allpass_feedback=Rational(numerator=5, denominator=10),
    stereo_spread_frames=23,
    send_millibels=0,
)


def test_the_reverb_has_eight_combs_and_four_allpasses() -> None:
    assert len(SPEC.comb_delays_frames) == 8
    assert len(SPEC.allpass_delays_frames) == 4


def test_the_state_is_a_value_and_a_block_render_matches_a_single_shot() -> None:
    """The shipped configuration, damping included: the state is carried."""
    generator = np.random.default_rng(3)
    signal = generator.standard_normal((RATE, 2))
    whole, _ = render_reverb(signal, reverb_state(SPEC), SPEC, RATE)
    state = reverb_state(SPEC)
    pieces = []
    for start in range(0, signal.shape[0], 8192):
        piece, state = render_reverb(signal[start : start + 8192], state, SPEC, RATE)
        pieces.append(piece)
    assert np.allclose(np.concatenate(pieces), whole, atol=1e-9)


def test_the_same_block_twice_from_the_same_state_is_identical() -> None:
    generator = np.random.default_rng(4)
    block = generator.standard_normal((4096, 2))
    state = reverb_state(SPEC)
    first, _ = render_reverb(block, state, SPEC, RATE)
    second, _ = render_reverb(block, state, SPEC, RATE)
    assert np.array_equal(first, second)


def _fitted_rt60(wet: np.ndarray) -> float:
    """The decay of an impulse response, fitted the way a room is measured."""
    envelope = 20.0 * np.log10(np.maximum(np.abs(wet[:, 0]), 1e-12))
    peak = float(np.max(envelope))
    tail = np.nonzero(envelope > peak - 30.0)[0]
    assert tail.size >= 5
    slope = np.polyfit(tail, envelope[tail], 1)[0]
    assert slope < 0.0
    return -60.0 / (slope * RATE)


def test_the_decay_time_matches_the_analytic_value() -> None:
    """RT60 = (L/fs) * (-3 ln10 / ln g) for a comb.

    The formula is checked on a single comb, where it is exact, and the whole
    reverb is bounded from below by it: eight parallel combs and four
    allpass stages can only make the tail longer.
    """
    single = ReverbSpec(
        comb_delays_frames=[1557],
        comb_feedback=Rational(numerator=84, denominator=100),
        damping=Rational(numerator=1, denominator=1),
        allpass_delays_frames=[],
        allpass_feedback=Rational(numerator=5, denominator=10),
        stereo_spread_frames=23,
        send_millibels=0,
    )
    impulse = np.zeros((RATE * 8, 2))
    impulse[0, 0] = 1.0
    wet, _ = render_reverb(impulse, reverb_state(single), single, RATE)
    measured = _fitted_rt60(wet)
    longest = max(SPEC.comb_delays_frames)
    feedback = SPEC.comb_feedback.numerator / SPEC.comb_feedback.denominator
    analytic = (longest / RATE) * (-3.0 * math.log(10.0) / math.log(feedback))
    assert abs(measured - analytic) / analytic <= 0.10, f"measured {measured:.3f}s, analytic {analytic:.3f}s"

    full, _ = render_reverb(impulse, reverb_state(SPEC), SPEC, RATE)
    assert _fitted_rt60(full) >= analytic * 0.9


def test_the_right_channel_is_offset_by_the_spread() -> None:
    impulse = np.zeros((RATE, 2))
    impulse[0, 0] = 1.0
    wet, _ = render_reverb(impulse, reverb_state(SPEC), SPEC, RATE)
    assert not np.array_equal(wet[:, 0], wet[:, 1])


def test_the_reverb_does_not_pass_dc() -> None:
    constant = np.full((RATE, 2), 1e-3)
    wet, _ = render_reverb(constant, reverb_state(SPEC), SPEC, RATE)
    assert abs(float(np.mean(wet))) < 1e-6
