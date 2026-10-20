"""Render-time instruments. No RNG here: an instrument may not roll dice."""

from __future__ import annotations

import math

import numpy as np

from indiegen.plan import NoteEvent
from indiegen.synth.osc import midi_to_hz


def render_pad(event: NoteEvent, sample_rate: int) -> np.ndarray:
    """The pad: a fundamental from the lane's scale plus partials 2..N.

    Each partial carries its own integer cent detune, and a slow rational LFO
    drifts that detune. The drifting frequency is integrated into a phase, so
    the result is a true frequency modulation rather than a chirp.
    """
    count = event.duration_frames
    times = np.arange(count, dtype=np.float64) / sample_rate
    rate = event.lfo_rate.numerator / event.lfo_rate.denominator
    lfo = np.sin(2.0 * np.pi * rate * times)
    base = midi_to_hz(event.midi)
    detunes = [0, *event.partial_detune_cents]
    voice = np.zeros(count, dtype=np.float64)
    for index, detune in enumerate(detunes):
        partial = index + 1
        drift = detune + event.lfo_depth_cents * lfo
        frequency = base * partial * np.power(2.0, drift / 1200.0)
        phase = 2.0 * np.pi * np.cumsum(frequency) / sample_rate
        voice += np.sin(phase)
    amplitude = math.pow(10.0, event.amplitude_millibels / 2000.0)
    return voice * amplitude
