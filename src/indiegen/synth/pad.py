"""The pad: a fundamental from the lane's scale plus partials 2..N.

Each partial carries its own integer cent detune, and a slow rational LFO
drifts that detune. The drifting frequency is integrated into a phase, so
the result is a true frequency modulation rather than a chirp.

The pad is rendered a block at a time. The phase is the sum of the drifting
frequency, so every partial carries a running total.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from indiegen.plan import PadEvent
from indiegen.synth.osc import cumulative_sum, midi_to_hz


@dataclass(frozen=True)
class PadState:
    """The running phase of every partial."""

    carries: tuple[float, ...]


def pad_state(event: PadEvent) -> PadState:
    """The zero state of the pad."""
    return PadState(carries=tuple(0.0 for _ in range(1 + len(event.partial_detune_cents))))


def render_pad_block(
    event: PadEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: PadState,
) -> tuple[np.ndarray, PadState]:
    """The pad, over the local frames ``[start, stop)``."""
    count = stop - start
    times = np.arange(start, stop, dtype=np.float64) / sample_rate
    rate = event.lfo_rate.numerator / event.lfo_rate.denominator
    lfo = np.sin(2.0 * np.pi * rate * times)
    base = midi_to_hz(event.midi)
    detunes = [0, *event.partial_detune_cents]
    voice = np.zeros(count, dtype=np.float64)
    carries = list(state.carries)
    for index, detune in enumerate(detunes):
        partial = index + 1
        drift = detune + event.lfo_depth_cents * lfo
        frequency = base * partial * np.power(2.0, drift / 1200.0)
        phase, carries[index] = cumulative_sum(carries[index], frequency)
        voice += np.sin(2.0 * np.pi * phase / sample_rate)
    amplitude = math.pow(10.0, event.amplitude_millibels / 2000.0)
    return voice * amplitude, PadState(carries=tuple(carries))


def render_pad(event: PadEvent, sample_rate: int) -> np.ndarray:
    """The pad, as a mono buffer."""
    voice, _ = render_pad_block(event, sample_rate, 0, event.duration_frames, pad_state(event))
    return voice
