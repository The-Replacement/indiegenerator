"""Render-time instruments. No RNG here: an instrument may not roll dice."""

from __future__ import annotations

import math

import numpy as np

A4_HZ: float = 440.0
A4_MIDI: int = 69


def midi_to_hz(midi: int) -> float:
    """The frequency of a MIDI note in equal temperament."""
    return A4_HZ * math.pow(2.0, (midi - A4_MIDI) / 12.0)


def zero_carries(count: int) -> tuple[float, ...]:
    """Zero initial carries."""
    return tuple(0.0 for _ in range(count))


def zero_block(count: int) -> np.ndarray:
    """A silent mono block of ``count`` frames.

    The shared allocation of the blockwise voices: every voice accumulates
    into exact float64 silence, so a block-wise render holds the same bits
    as a whole-track one. Only the count is a parameter - shape and dtype
    are the knowledge being kept in one place.
    """
    return np.zeros(count, dtype=np.float64)


def sine_from_phase(phase: np.ndarray, sample_rate: int) -> np.ndarray:
    """A sine wave from a running phase: ``sin(2 * pi * phase / sample_rate)``.

    ``phase`` is the running sum of a frequency (see ``cumulative_sum``).
    The gain deliberately stays at the call site: the voices scale by a
    scalar, by an array, and on different sides of the product, and keeping
    that multiplication where it is written keeps every call bit-identical.
    """
    return np.sin(2.0 * np.pi * phase / sample_rate)


def sine(frequency_hz: float, count: int, sample_rate: int) -> np.ndarray:
    """A sine of ``count`` samples. The phase starts at zero."""
    times = np.arange(count, dtype=np.float64) / sample_rate
    return np.sin(2.0 * np.pi * frequency_hz * times)


def cumulative_sum(carry: float, block: np.ndarray) -> tuple[np.ndarray, float]:
    """A running sum that continues a previous total, exactly.

    ``np.cumsum`` is a strict left-to-right fold, so a block-wise running
    sum is bit-identical to a single-shot one as long as the carry is folded
    in *before* the block's first element. Adding the carry to the block's
    own cumsum afterwards regroups the additions and changes the last bits:
    measured over half a million samples, that form differs by 3.6e-06 and
    this one by nothing at all.

    The phase of an oscillator is the sum of its frequencies, so this is what
    lets a voice be rendered a block at a time without moving the audio.
    """
    if block.size == 0:
        return block, carry
    values = np.cumsum(np.concatenate((np.array([carry], dtype=np.float64), block)))[1:]
    return values, float(values[-1])
