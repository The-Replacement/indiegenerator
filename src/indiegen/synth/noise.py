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


def stream_key(seed: int, index: int, kind: int) -> int:
    """The integer that selects a noise stream for a partial and a purpose."""
    return mix64((seed ^ mix64(index * 0x9E3779B97F4A7C15 + kind)) & MASK64)


def uniform_stream(seed: int, index: int, kind: int, count: int) -> np.ndarray:
    """A uniform white stream in [-0.5, 0.5), from a counter hash."""
    key = np.uint64(stream_key(seed, index, kind) & MASK64)
    counter = np.arange(count, dtype=np.uint64) + key
    words = mix64_array(counter)
    return (words >> np.uint64(11)).astype(np.float64) / 9007199254740992.0 - 0.5


def pink_stream(seed: int, count: int, rate: int) -> np.ndarray:
    """A 1/f signal of ``count`` samples at ``rate`` hertz."""
    total = np.zeros(count, dtype=np.float64)
    weight_sum = 0.0
    for index in range(SOURCE_COUNT):
        fraction = index / max(1, SOURCE_COUNT - 1)
        cutoff = LOWEST_CUTOFF_HZ * math.pow(HIGHEST_CUTOFF_HZ / LOWEST_CUTOFF_HZ, fraction)
        alpha = math.exp(-2.0 * math.pi * cutoff / rate)
        weight = math.pow(cutoff, -WEIGHT_EXPONENT)
        white = uniform_stream(seed, index, 0, count) * 2.0
        total += weight * lfilter([1.0 - alpha], [1.0, -alpha], white)
        weight_sum += weight
    if weight_sum <= 0.0:
        return total
    return total / weight_sum


def control_count(duration_frames: int, sample_rate: int) -> int:
    """How many control-rate samples a track of this length needs."""
    return int(math.ceil(duration_frames * CONTROL_RATE / sample_rate)) + 2


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
    samples = np.arange(count, dtype=np.int64)
    scaled = samples * CONTROL_RATE
    lower = scaled // sample_rate
    remainder = scaled - lower * sample_rate
    upper = np.minimum(lower + 1, control.size - 1)
    fraction = remainder.astype(np.float64) / sample_rate
    values = control[lower] * (1.0 - fraction) + control[upper] * fraction
    return values
