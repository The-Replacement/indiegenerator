"""The spectral drone stack.

Each partial drifts on its own 1/f signal, in detune and in amplitude, and
the drift is clipped to the declared depth so the brief's five-to-fifteen
cent bound is hard rather than approximate. The partials are exact rational
ratios of the fundamental, so the beating between them is the movement.
"""

from __future__ import annotations

import math

import numpy as np

from indiegen.plan import DroneEvent
from indiegen.synth.env import dc_block
from indiegen.synth.noise import (
    AMPLITUDE_STREAM,
    CONTROL_RATE,
    DETUNE_STREAM,
    control_count,
    interpolate_to,
    pink_stream,
    stream_key,
)
from indiegen.synth.osc import midi_to_hz


def render_drone(event: DroneEvent, sample_rate: int) -> np.ndarray:
    """One drone stack, as a mono buffer."""
    count = event.duration_frames
    base = midi_to_hz(event.midi)
    control = control_count(count, sample_rate)
    voice = np.zeros(count, dtype=np.float64)

    for index, partial in enumerate(event.partials):
        detune_control = pink_stream(stream_key(event.noise_seed, index, DETUNE_STREAM), control, CONTROL_RATE)
        detune_signal = np.clip(interpolate_to(detune_control, count, sample_rate), -1.0, 1.0)
        detune = partial.detune_cents + partial.detune_lfo.depth_cents * detune_signal
        ratio = partial.ratio.numerator / partial.ratio.denominator
        frequency = base * ratio * np.exp(detune * (math.log(2.0) / 1200.0))
        phase = 2.0 * math.pi * np.cumsum(frequency) / sample_rate

        amplitude_control = pink_stream(stream_key(event.noise_seed, index, AMPLITUDE_STREAM), control, CONTROL_RATE)
        amplitude_signal = np.clip(interpolate_to(amplitude_control, count, sample_rate), -1.0, 1.0)
        millibels = partial.amplitude_millibels + partial.amplitude_lfo.depth_millibels * amplitude_signal
        voice += np.sin(phase) * np.exp(millibels * (math.log(10.0) / 2000.0))

    return dc_block(voice, sample_rate)
