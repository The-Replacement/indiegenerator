"""Envelopes. Every one of them is a pure function of the Plan."""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter

from indiegen.plan import EventBase, Plan

DC_BLOCKER_HZ: float = 20.0


def dc_block(signal: np.ndarray, sample_rate: int) -> np.ndarray:
    """Remove the DC offset with a one-pole high pass.

    A voice with an envelope correlates with its carrier, and a plucked string
    whose tail is cut leaves a small offset behind. Both are tiny in level
    and enormous in a reverb, whose combs have a DC gain of 1/(1-g) each.
    The block lives with the instruments rather than in the master chain, so
    the sustained pad - and with it the committed S0 artifact - is untouched.

    The transfer function is (1 - z^-1) / (1 - r z^-1): zero at DC, and a
    high pass above the corner.
    """
    coefficient = math.exp(-2.0 * math.pi * DC_BLOCKER_HZ / sample_rate)
    blocked: np.ndarray = lfilter([1.0, -1.0], [1.0, -coefficient], signal)
    return blocked


def dc_block_state(
    signal: np.ndarray,
    sample_rate: int,
    state: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """The same block, with its state carried across the blocks.

    A block-wise filter that starts from zero every time leaves a residual
    behind on every block, and the reverb's comb bank multiplies that
    residual by fifty.
    """
    coefficient = math.exp(-2.0 * math.pi * DC_BLOCKER_HZ / sample_rate)
    filtered, carry = lfilter([1.0, -1.0], [1.0, -coefficient], signal, zi=state)
    result: np.ndarray = filtered
    return result, carry


def note_envelope(event: EventBase) -> np.ndarray:
    """The note's attack and release, linear, exactly zero at the very edges.

    The edges are zero even when the attack and the release are empty: a
    note that starts or stops at full level is a click, and a plucked string
    has neither an attack nor a release of its own.
    """
    count = event.duration_frames
    gain = np.ones(count, dtype=np.float64)
    if event.attack_frames > 0:
        ramp = np.arange(count, dtype=np.float64) / event.attack_frames
        gain *= np.minimum(1.0, ramp)
    if event.release_frames > 0:
        ramp = np.arange(count - 1, -1, -1, dtype=np.float64) / event.release_frames
        gain *= np.minimum(1.0, ramp)
    if count > 0:
        gain[0] = 0.0
        gain[-1] = 0.0
    return gain


def section_gain(plan: Plan, start: int, count: int) -> np.ndarray:
    """The arrangement's level over an absolute window, with crossfades."""
    levels = np.empty(count, dtype=np.float64)
    levels.fill(float(plan.sections[0].level_millibels) if plan.sections else 0.0)
    for section in plan.sections:
        low = max(start, section.start_frame)
        high = min(start + count, section.end_frame)
        if high > low:
            levels[low - start : high - start] = float(section.level_millibels)
    half = plan.section_crossfade_frames // 2
    for section in plan.sections[1:]:
        low = max(start, section.start_frame - half)
        high = min(start + count, section.start_frame + plan.section_crossfade_frames - half)
        if high > low:
            ramp = np.linspace(levels[low - start], levels[min(high - start, count - 1)], high - low)
            levels[low - start : high - start] = ramp
    return np.power(10.0, levels / 2000.0)


def fade_gain(plan: Plan, start: int, count: int) -> np.ndarray:
    """The global fade in and out. Exactly zero at the first and last frame."""
    index = np.arange(start, start + count, dtype=np.float64)
    gain = np.ones(count, dtype=np.float64)
    if plan.fade_in_frames > 0:
        mask = index < plan.fade_in_frames
        gain[mask] = index[mask] / plan.fade_in_frames
    if plan.fade_out_frames > 0:
        mask = index >= plan.duration_frames - plan.fade_out_frames
        gain[mask] = (plan.duration_frames - 1 - index[mask]) / plan.fade_out_frames
    return np.clip(gain, 0.0, 1.0)


def fade_weight(plan: Plan) -> np.ndarray:
    """One where the track is not inside a fade, zero where it is."""
    gain = fade_gain(plan, 0, plan.duration_frames)
    return (gain >= 1.0).astype(np.float64)
