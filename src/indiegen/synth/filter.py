"""Biquads and one-pole filters.

The state is a value: coefficients in, audio and new state out. The one-pole
helpers live here too, so there is a single implementation of the formula.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter, sosfilt


def lowpass_sos(cutoff_hz: int, q_num: int, q_den: int, sample_rate: int) -> np.ndarray:
    """A resonant second-order lowpass as second-order sections.

    The classic RBJ design: one biquad, with the Q taken from the preset as
    an exact rational so that no float ever enters the coefficients twice.
    """
    quality = q_num / q_den
    omega = 2.0 * math.pi * cutoff_hz / sample_rate
    cosine = math.cos(omega)
    alpha = math.sin(omega) / (2.0 * quality)
    a0 = 1.0 + alpha
    b0 = (1.0 - cosine) / 2.0
    b1 = 1.0 - cosine
    b2 = (1.0 - cosine) / 2.0
    a1 = -2.0 * cosine
    a2 = 1.0 - alpha
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def initial_state(sos: np.ndarray, channels: int = 1) -> np.ndarray:
    """The zero state of a filter that starts from silence.

    ``sosfilt_zi`` would return the state for a *steady* input, which makes
    a render begin with an offset instead of with silence. The fades have
    been hiding that; it is not what a filter on a track that starts at zero
    should do.
    """
    state = np.zeros((sos.shape[0], 2), dtype=np.float64)
    if channels == 1:
        return state
    return np.repeat(state[:, :, np.newaxis], channels, axis=2)


def apply_biquad(sos: np.ndarray, block: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Filter one block, threading the filter state across the boundary.

    ``block`` is ``(n,)`` for a mono bus or ``(n, channels)`` for a stereo one.
    """
    filtered, new_state = sosfilt(sos, block, zi=state, axis=0)
    return np.asarray(filtered, dtype=np.float64), np.asarray(new_state, dtype=np.float64)


def _coefficient(cutoff_hz: float, sample_rate: int) -> float:
    return math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)


def one_pole_lowpass(signal: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """A one-pole low pass: (1 - r) / (1 - r z^-1)."""
    coefficient = _coefficient(cutoff_hz, sample_rate)
    filtered: np.ndarray = lfilter([1.0 - coefficient], [1.0, -coefficient], signal)
    return filtered


def one_pole_highpass(signal: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """A one-pole high pass: (1 - z^-1) / (1 - r z^-1)."""
    coefficient = _coefficient(cutoff_hz, sample_rate)
    filtered: np.ndarray = lfilter([1.0, -1.0], [1.0, -coefficient], signal)
    return filtered


def one_pole_highpass_state(
    signal: np.ndarray,
    cutoff_hz: float,
    sample_rate: int,
    state: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """The high pass, carrying its filter state across blocks."""
    coefficient = _coefficient(cutoff_hz, sample_rate)
    filtered, carry = lfilter([1.0, -1.0], [1.0, -coefficient], signal, zi=state)
    result: np.ndarray = filtered
    return result, carry
