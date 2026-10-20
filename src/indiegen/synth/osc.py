"""Render-time instruments. No RNG here: an instrument may not roll dice."""

from __future__ import annotations

import math

import numpy as np

A4_HZ: float = 440.0
A4_MIDI: int = 69


def midi_to_hz(midi: int) -> float:
    """The frequency of a MIDI note in equal temperament."""
    return A4_HZ * math.pow(2.0, (midi - A4_MIDI) / 12.0)


def sine(frequency_hz: float, count: int, sample_rate: int) -> np.ndarray:
    """A sine of ``count`` samples. The phase starts at zero."""
    times = np.arange(count, dtype=np.float64) / sample_rate
    return np.sin(2.0 * math.pi * frequency_hz * times)
