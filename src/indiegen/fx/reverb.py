"""A short Schroeder reverb.

Eight parallel comb filters into four series allpass filters per channel, with
the right channel's delay lengths offset by a declared spread. The decay is
the comb feedback: with no damping the RT60 is analytic, ``(L/fs) * (-3 ln10 /
ln g)``, and the unit test checks the rendered impulse response against it.

The comb and allpass lines are processed a block at a time
(:mod:`indiegen.fx.line`), because ``lfilter`` with a fifteen-hundred-tap
filter over four million samples is sixty billion operations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from indiegen.fx.line import allpass_line, comb_line, zero_wet
from indiegen.plan import ReverbSpec
from indiegen.synth.env import dc_block_state, dc_blocker_state


@dataclass(frozen=True)
class ReverbState:
    """The delay lines of the reverb, as a value."""

    comb_states: tuple[tuple[np.ndarray, ...], ...]
    allpass_states: tuple[tuple[np.ndarray, ...], ...]
    dc_states: tuple[np.ndarray, ...]
    dc_sum_states: tuple[np.ndarray, ...]
    damping_states: tuple[np.ndarray, ...]


def reverb_state(spec: ReverbSpec) -> ReverbState:
    """The zero state of the reverb."""
    comb_states: list[tuple[np.ndarray, ...]] = []
    allpass_states: list[tuple[np.ndarray, ...]] = []
    for channel in range(2):
        offset = spec.stereo_spread_frames if channel == 1 else 0
        combs = tuple(np.zeros(delay + offset, dtype=np.float64) for delay in spec.comb_delays_frames)
        allpasses = tuple(np.zeros(delay + offset, dtype=np.float64) for delay in spec.allpass_delays_frames)
        comb_states.append(combs)
        allpass_states.append(allpasses)
    return ReverbState(
        comb_states=tuple(comb_states),
        allpass_states=tuple(allpass_states),
        dc_states=tuple(dc_blocker_state() for _ in range(2)),
        dc_sum_states=tuple(dc_blocker_state() for _ in range(2)),
        damping_states=tuple(np.zeros(1, dtype=np.float64) for _ in range(2)),
    )


def render_reverb(
    block: np.ndarray,
    state: ReverbState,
    spec: ReverbSpec,
    sample_rate: int,
) -> tuple[np.ndarray, ReverbState]:
    """Filter one block of the main bus through the reverb."""
    feedback = spec.comb_feedback.numerator / spec.comb_feedback.denominator
    allpass_feedback = spec.allpass_feedback.numerator / spec.allpass_feedback.denominator
    damping = spec.damping.numerator / spec.damping.denominator

    wet = zero_wet(block)
    new_comb_states: list[tuple[np.ndarray, ...]] = []
    new_allpass_states: list[tuple[np.ndarray, ...]] = []
    new_dc_states: list[np.ndarray] = []
    new_dc_sum_states: list[np.ndarray] = []
    new_damping_states: list[np.ndarray] = []

    for channel in range(block.shape[1]):
        offset = spec.stereo_spread_frames if channel == 1 else 0
        signal = np.ascontiguousarray(block[:, channel], dtype=np.float64)
        signal, dc_carry = dc_block_state(signal, sample_rate, state.dc_states[channel])
        new_dc_states.append(dc_carry)
        comb_states = list(state.comb_states[channel])
        summed = np.zeros(signal.size, dtype=np.float64)
        for index, delay in enumerate(spec.comb_delays_frames):
            filtered, comb_states[index] = comb_line(signal, delay + offset, feedback, comb_states[index])
            summed += filtered
        # The comb bank has a DC gain of 1/(1-g) each, so the offset the input
        # block removed comes back multiplied by the whole bank. Block it again
        # here, before the allpasses.
        summed, dc_sum_carry = dc_block_state(summed, sample_rate, state.dc_sum_states[channel])
        new_dc_sum_states.append(dc_sum_carry)
        if damping < 1.0:
            summed, damp_carry = lfilter([1.0 - damping], [1.0, -damping], summed, zi=state.damping_states[channel])
            new_damping_states.append(damp_carry)
        else:
            new_damping_states.append(state.damping_states[channel])

        allpass_states = list(state.allpass_states[channel])
        for index, delay in enumerate(spec.allpass_delays_frames):
            summed, allpass_states[index] = allpass_line(
                summed, delay + offset, allpass_feedback, allpass_states[index]
            )

        wet[:, channel] = summed
        new_comb_states.append(tuple(comb_states))
        new_allpass_states.append(tuple(allpass_states))

    return wet, ReverbState(
        comb_states=tuple(new_comb_states),
        allpass_states=tuple(new_allpass_states),
        dc_states=tuple(new_dc_states),
        dc_sum_states=tuple(new_dc_sum_states),
        damping_states=tuple(new_damping_states),
    )
