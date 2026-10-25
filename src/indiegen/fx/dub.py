"""T10: the dub chain - the bit reduction and the drifting bandpass.

The chain, in the order the brief gives it: the stabs are pitched down, then
bit-reduced, then bandpassed, and the bandpass is where the movement lives.
The dotted-eighth delay, the filter delay, the reverb and the sidechain to the
kick belong to the other stages. This module returns the wet of the bandpass
and nothing else: the dry is the render path's business, and so is the send
level.

Three decisions shape the sound.

The bit reduction is a quantiser, not a dither. A sample is snapped to the
grid of ``2**(bit_depth-1)`` steps, so at eight bits the staircase is 1/128
wide and the resolution itself is the character. The quantiser runs first,
on the dry stabs, because that is where the character has to be earned.

The band's cutoff drifts on the 1/f stream, at the control rate, and not on
a sine LFO. A 1/f signal sits near zero most of the time and moves rarely
and by a little; that is what a hand on a knob does. A sine moves at a fixed
rate forever, and it is heard as a wobble rather than as a drift. The stream
is about a twentieth of unity, so it is scaled by its own deviation before it
is used: the plan's depth is the width of the drift, not a nominal bound.

The band is twelve decibels an octave: two second-order sections in series,
from ``scipy.signal.butter`` at order two. Its width comes from the plan's
own Q - the half width is the centre over twice the Q - and the edges follow
the drifting centre, so the whole band travels with it.

The coefficients are rebuilt every ``CONTROL_RATE`` samples - ten times a
second at forty-four-one-one hundred hertz - and the biquad's state is
carried across the rebuilds, so the cutoff moves without the filter clicking.
Rebuilding them per sample would be ten times the work for a cutoff that does
not move that fast.

The state is a value, and the numbers are exact: the 1/f stream is
counter-based, the interpolation is done in integer arithmetic, and the
filter is a plain recursion. A block-wise render is therefore bit-identical
to a single-shot one, which is the invariant the whole project rests on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt

from indiegen.control import (
    CONTROL_RATE,
    HIGHEST_CUTOFF_HZ,
    LOWEST_CUTOFF_HZ,
    SOURCE_COUNT,
    WEIGHT_EXPONENT,
    PinkState,
    control_slice,
    pink_state,
    stream_key,
)
from indiegen.plan import CHANNELS, DubChainSpec
from indiegen.synth.filter import initial_state
from indiegen.synth.noise import interpolate_block

MIN_CENTRE_HZ: float = 20.0
"""The lowest centre the band may take, so the lower edge stays above zero."""

MAX_CENTRE_FRACTION: float = 0.28
"""The highest centre, as a fraction of the sample rate: the edge stays below Nyquist."""

DRIFT_STREAM: int = 0
"""The purpose the drift stream is drawn for."""

DRIFT_DEVIATION: float = 0.25
"""The drift's standard deviation, on the half scale.

Two standard deviations of the 1/f stream fill the half scale, so the plan's
depth is the width of the drift and not a nominal bound: a centre of four
hundred and fifty hertz with a depth of five hundred travels from two
hundred to seven hundred hertz.
"""

DRIFT_LIMIT: float = 0.5
"""The drift is bounded to the half scale, the way the drone bounds its detune."""


@dataclass(frozen=True)
class DubChainState:
    """The state of the dub chain, as a value.

    The drift stream carries its own position, so the drift is continuous
    across the block boundary. ``position`` is the global frame the next
    block starts at, and ``step_start`` is the frame at which the current
    coefficients were built: the filter is never rebuilt inside a step.
    """

    drift: PinkState
    position: int
    step_start: int
    sos: np.ndarray
    zi: tuple[np.ndarray, ...]


def bit_reduce(block: np.ndarray, bit_depth: int) -> np.ndarray:
    """Snap every sample to the grid of the declared bit depth.

    The quantiser is a round to the nearest multiple of ``1/2**(bit_depth-1)``.
    There is no dither and no noise shaping: the staircase is the point.
    """
    scale = float(2 ** (bit_depth - 1))
    return np.round(np.asarray(block, dtype=np.float64) * scale) / scale


def drift_signal(spec: DubChainSpec, sample_rate: int, count: int) -> np.ndarray:
    """The 1/f drift of the band's centre, over ``count`` frames from the start.

    The drift is the project's own 1/f stream, cut at the control rate and
    interpolated up to the audio rate, bounded to the half scale. It is
    exposed because the drift is a measurement: its spectrum is the proof
    that the cutoff wanders on 1/f and not on a sine.
    """
    values, _ = _drift_block(spec, sample_rate, count, 0, pink_state())
    return values


def dub_chain_state(spec: DubChainSpec, sample_rate: int) -> DubChainState:
    """The zero state of the dub chain."""
    centre = _centre_hz(spec, float(drift_signal(spec, sample_rate, 1)[0]))
    sos = _band_sos(centre, sample_rate, _quality(spec))
    zi = initial_state(sos, 1)
    return DubChainState(
        drift=pink_state(),
        position=0,
        step_start=0,
        sos=sos,
        zi=tuple(zi.copy() for _ in range(CHANNELS)),
    )


def render_dub_chain(
    block: np.ndarray,
    state: DubChainState,
    spec: DubChainSpec,
    sample_rate: int,
) -> tuple[np.ndarray, DubChainState]:
    """Filter one block of the stabs through the dub chain.

    The block is the dry stabs; what comes back is the wet of the bandpass.
    The block is processed in steps of ``CONTROL_RATE`` samples, and the
    coefficients are rebuilt at the step boundaries, so the cutoff moves
    without the filter clicking and without the state depending on where the
    block happens to end.

    The block must be the frames that start at the state's position: the
    chain keeps its own place in the track, and the drift is cut from there.
    """
    count = int(block.shape[0])
    if count == 0:
        return np.asarray(block, dtype=np.float64).copy(), state

    reduced = bit_reduce(block, spec.bit_depth)
    drift, drift_state = _drift_block(spec, sample_rate, count, state.position, state.drift)

    wet = np.zeros((count, block.shape[1]), dtype=np.float64)
    zi = [state.zi[channel].copy() for channel in range(block.shape[1])]
    sos = state.sos
    step_start = state.step_start
    cursor = 0
    while cursor < count:
        frame = state.position + cursor
        if frame >= step_start + CONTROL_RATE:
            step_start += CONTROL_RATE
            offset = step_start - state.position
            if offset < 0 or offset >= count:
                raise ValueError("the dub chain was rendered out of order: the block skips frames")
            centre = _centre_hz(spec, float(drift[offset]))
            sos = _band_sos(centre, sample_rate, _quality(spec))
        chunk = min(count - cursor, step_start + CONTROL_RATE - frame)
        for channel in range(block.shape[1]):
            filtered, zi[channel] = sosfilt(sos, reduced[cursor : cursor + chunk, channel], zi=zi[channel])
            wet[cursor : cursor + chunk, channel] = filtered
        cursor += chunk

    return wet, DubChainState(
        drift=drift_state,
        position=state.position + count,
        step_start=step_start,
        sos=sos,
        zi=tuple(zi),
    )


def _drift_block(
    spec: DubChainSpec,
    sample_rate: int,
    count: int,
    position: int,
    drift_state: PinkState,
) -> tuple[np.ndarray, PinkState]:
    """The drift over ``count`` frames, from the global frame ``position``.

    The control values are cut from the 1/f stream the way the drone cuts
    its detune: the stream is continued from where it stands, so the values
    are the ones the whole stream would have produced, and the block that
    came before may already have produced the first of them.
    """
    low = position * CONTROL_RATE // sample_rate
    high = (position + count - 1) * CONTROL_RATE // sample_rate + 1
    control, new_state = control_slice(
        drift_state,
        stream_key(spec.drift_seed, 0, DRIFT_STREAM),
        low,
        high,
        CONTROL_RATE,
    )
    values = interpolate_block(control, count, sample_rate, position, low, high + 1)
    scale = DRIFT_DEVIATION / _pink_deviation()
    return np.clip(values * scale, -DRIFT_LIMIT, DRIFT_LIMIT), new_state


def _pink_deviation() -> float:
    """The 1/f stream's standard deviation, from its design.

    The stream is a weighted mean of one-pole lowpassed white sources, so
    its variance is the sum of the sources' variances, weighted. The number
    is a property of the design and not of the seed: every seed draws the
    same distribution, to within the sampling error of a track.

    The stream is about a twentieth of unity - a raw sample of it would
    move a cutoff by a couple of hertz and be heard as nothing - so the
    drift is scaled by this number before it is used.
    """
    weighted = 0.0
    total_weight = 0.0
    for index in range(SOURCE_COUNT):
        fraction = index / max(1, SOURCE_COUNT - 1)
        cutoff = LOWEST_CUTOFF_HZ * math.pow(HIGHEST_CUTOFF_HZ / LOWEST_CUTOFF_HZ, fraction)
        alpha = math.exp(-2.0 * math.pi * cutoff / CONTROL_RATE)
        weight = math.pow(cutoff, -WEIGHT_EXPONENT)
        weighted += weight * weight * (1.0 - alpha) / (1.0 + alpha)
        total_weight += weight
    return math.sqrt(weighted / (total_weight * total_weight) / 3.0)


def _centre_hz(spec: DubChainSpec, drift_value: float) -> float:
    """The centre of the band, on the drifting cutoff."""
    return float(spec.bandpass_hz) + float(spec.drift_depth_hz) * drift_value


def _quality(spec: DubChainSpec) -> float:
    """The Q of the band, from the plan."""
    return spec.bandpass_q_num / max(1, spec.bandpass_q_den)


def _band_sos(centre_hz: float, sample_rate: int, quality: float) -> np.ndarray:
    """The two bandpass sections of the twelve-decibel band.

    Order two of a Butterworth bandpass is two second-order sections in
    series, twelve decibels an octave. The width comes from the plan's
    own Q: the half width is the centre over twice the Q, so a Q of two is
    a band a quarter of the centre wide. The centre is clamped so the
    lower edge stays above zero and the upper edge stays below Nyquist.
    """
    highest = MAX_CENTRE_FRACTION * sample_rate
    centre = min(max(centre_hz, MIN_CENTRE_HZ), highest)
    half = centre / (2.0 * max(0.25, quality))
    low = max(MIN_CENTRE_HZ * 0.5, centre - half)
    high = min(highest, centre + half)
    sections = butter(2, [low, high], btype="band", fs=sample_rate, output="sos")
    return np.asarray(sections, dtype=np.float64)
