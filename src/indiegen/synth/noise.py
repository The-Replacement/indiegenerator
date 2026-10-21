"""The 1/f primitive.

A deterministic, counter-based signal: no RNG object is constructed and no
random source is imported. It is the sum of a handful of one-pole lowpassed
counter-based white sources with geometrically spaced cutoffs and f^-3/2
weights, which is the standard spectral-mixture way to get a 1/f law.

The Voss-McCartney row sum was measured and rejected: it is flat to -7
dB/decade, but its inter-sample step reaches 4.7 sigma, which at a ten-cent
detune depth is an audible forty-seven-cent pitch jump.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from indiegen.mixing import MASK64, mix64, mix64_array

CONTROL_RATE: int = 4410
SOURCE_COUNT: int = 12
LOWEST_CUTOFF_HZ: float = 20.0
HIGHEST_CUTOFF_HZ: float = 10000.0
WEIGHT_EXPONENT: float = 1.5
DETUNE_STREAM: int = 0
AMPLITUDE_STREAM: int = 1
HISTORY: int = 2


@dataclass(frozen=True)
class PinkState:
    """The state of the 1/f stream: the filters, the position and the history.

    The history holds the last couple of samples the stream produced, because
    a block that starts inside the control grid needs a value the previous
    block already produced.
    """

    filters: tuple[np.ndarray, ...]
    position: int
    history: np.ndarray


def pink_state() -> PinkState:
    """The zero state of the 1/f stream."""
    return PinkState(
        filters=tuple(np.zeros(1, dtype=np.float64) for _ in range(SOURCE_COUNT)),
        position=0,
        history=np.zeros(HISTORY, dtype=np.float64),
    )


def stream_key(seed: int, index: int, kind: int) -> int:
    """The integer that selects a noise stream for a partial and a purpose."""
    return mix64((seed ^ mix64(index * 0x9E3779B97F4A7C15 + kind)) & MASK64)


def uniform_stream(seed: int, index: int, kind: int, count: int, start: int = 0) -> np.ndarray:
    """A uniform white stream in [-0.5, 0.5), from a counter hash.

    The counters run from ``start``, so a block of the stream is the same
    block of the whole one.
    """
    key = np.uint64(stream_key(seed, index, kind) & MASK64)
    counter = np.arange(start, start + count, dtype=np.uint64) + key
    words = mix64_array(counter)
    return (words >> np.uint64(11)).astype(np.float64) / 9007199254740992.0 - 0.5


def pink_stream_block(
    seed: int,
    count: int,
    rate: int,
    state: PinkState,
) -> tuple[np.ndarray, PinkState]:
    """The next ``count`` samples of the 1/f stream, continuing the state.

    The one-pole filters carry their own state, so a block of the stream is
    bit-identical to the same block of the whole one.
    """
    total = np.zeros(count, dtype=np.float64)
    weight_sum = 0.0
    filters: list[np.ndarray] = []
    for index in range(SOURCE_COUNT):
        fraction = index / max(1, SOURCE_COUNT - 1)
        cutoff = LOWEST_CUTOFF_HZ * math.pow(HIGHEST_CUTOFF_HZ / LOWEST_CUTOFF_HZ, fraction)
        alpha = math.exp(-2.0 * math.pi * cutoff / rate)
        weight = math.pow(cutoff, -WEIGHT_EXPONENT)
        white = uniform_stream(seed, index, 0, count, state.position) * 2.0
        filtered, carry = lfilter([1.0 - alpha], [1.0, -alpha], white, zi=state.filters[index])
        total += weight * filtered
        weight_sum += weight
        filters.append(carry)
    if weight_sum <= 0.0:
        values = total
    else:
        values = total / weight_sum
    history = state.history
    if count > 0:
        history = np.concatenate((state.history, values))[-HISTORY:]
    return values, PinkState(filters=tuple(filters), position=state.position + count, history=history)


def pink_stream(seed: int, count: int, rate: int) -> np.ndarray:
    """A 1/f signal of ``count`` samples at ``rate`` hertz."""
    values, _ = pink_stream_block(seed, count, rate, pink_state())
    return values


def control_slice(
    state: PinkState,
    seed: int,
    low: int,
    high: int,
    rate: int,
) -> tuple[np.ndarray, PinkState]:
    """The control-rate values at the indices ``[low, high]``.

    A block of the audio needs the control values around it, and the block
    that came before may already have produced the first one or two of them.
    The stream is continued from where it stands, so the values are the same
    ones the whole stream would have produced.
    """
    have = state.position - low
    if have > HISTORY:
        raise ValueError("the control stream is too far ahead of the block")
    if have > 0:
        prefix = state.history[HISTORY - have :]
    else:
        prefix = np.zeros(0, dtype=np.float64)
    count = high - state.position + 1
    if count <= 0:
        return prefix, state
    produced, new_state = pink_stream_block(seed, count, rate, state)
    if have > 0:
        return np.concatenate((prefix, produced)), new_state
    return produced[low - state.position :], new_state


def control_count(duration_frames: int, sample_rate: int) -> int:
    """How many control-rate samples a track of this length needs."""
    return int(math.ceil(duration_frames * CONTROL_RATE / sample_rate)) + 2


def interpolate_block(
    control: np.ndarray,
    count: int,
    sample_rate: int,
    start: int,
    offset: int,
    total: int,
) -> np.ndarray:
    """Interpolate a slice of a control-rate signal up to the audio rate.

    ``control`` holds the control samples from the index ``offset`` onwards;
    the audio frames are the local frames ``[start, start + count)``. The
    result passes exactly through the control points. The position of a
    sample in the control signal is computed with integer arithmetic,
    because a float ratio drifts and a control point would land a hair to
    the side of its own value.
    """
    samples = np.arange(start, start + count, dtype=np.int64)
    scaled = samples * CONTROL_RATE
    lower = scaled // sample_rate
    remainder = scaled - lower * sample_rate
    lower_index = (lower - offset).astype(np.int64)
    upper = (np.minimum(lower + 1, total - 1) - offset).astype(np.int64)
    fraction = remainder.astype(np.float64) / sample_rate
    values = control[lower_index] * (1.0 - fraction) + control[upper] * fraction
    return values


def interpolate_to(control: np.ndarray, count: int, sample_rate: int) -> np.ndarray:
    """Interpolate a control-rate signal up to the audio rate.

    The result passes exactly through the control points. The position of a
    sample in the control signal is computed with integer arithmetic, because
    a float ratio drifts and a control point would land a hair to the side of
    its own value.

    The interpolation is written out rather than delegated to ``np.interp``,
    which binary-searches per sample and cost more than the rest of the
    drone put together.
    """
    return interpolate_block(control, count, sample_rate, 0, 0, control.size)
