"""Biquads. The state is a value: coefficients in, audio and new state out."""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import sosfilt, sosfilt_zi


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
    """The zero state for a block of ``channels`` interleaved channels."""
    state = sosfilt_zi(sos)
    if channels == 1:
        return np.asarray(state, dtype=np.float64)
    return np.repeat(np.asarray(state, dtype=np.float64)[:, :, np.newaxis], channels, axis=2)


def apply_biquad(sos: np.ndarray, block: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Filter one block, threading the filter state across the boundary.

    ``block`` is ``(n,)`` for a mono bus or ``(n, channels)`` for a stereo one.
    """
    filtered, new_state = sosfilt(sos, block, zi=state, axis=0)
    return np.asarray(filtered, dtype=np.float64), np.asarray(new_state, dtype=np.float64)
