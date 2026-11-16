"""T8 radiophonic: a test-tone partial stack ring-modulated by a carrier."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain
from indiegen.plan import RadiophonicEvent
from indiegen.synth.osc import midi_to_hz


@dataclass(frozen=True)
class RadiophonicState:
    phase: float = 0.0


def radiophonic_state(event: RadiophonicEvent, sample_rate: int = 44100) -> RadiophonicState:
    return RadiophonicState(phase=0.0)


def render_radiophonic_block(
    event: RadiophonicEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: RadiophonicState,
) -> tuple[np.ndarray, RadiophonicState]:
    count = stop - start
    out = np.zeros(count, dtype=np.float64)
    if count <= 0:
        return out, state
    sr = sample_rate
    fundamental = midi_to_hz(event.midi)
    carrier_freq = fundamental * (event.carrier_ratio.numerator / event.carrier_ratio.denominator)
    t = (np.arange(count) + start) / sr
    # test-tone stack
    voice = np.zeros(count, dtype=np.float64)
    for p in event.partials or [1, 2, 3]:
        voice += np.sin(2 * np.pi * fundamental * p * t)
    carrier = np.sin(2 * np.pi * carrier_freq * t)
    out = voice * carrier
    amp = millibels_to_gain(event.amplitude_millibels)
    out = out * amp
    return out, state


def render_radiophonic(event: RadiophonicEvent, sample_rate: int) -> np.ndarray:
    voice, _ = render_radiophonic_block(event, sample_rate, 0, event.duration_frames, radiophonic_state(event))
    return voice


# aliases
RingModState = RadiophonicState
ring_mod_state = radiophonic_state
render_ring_mod_block = render_radiophonic_block
render_ring_mod = render_radiophonic
render_test_tone_block = render_radiophonic_block
render_test_tone = render_radiophonic
TestToneState = RadiophonicState
test_tone_state = radiophonic_state
T8State = RadiophonicState
t8_state = radiophonic_state
render_t8_block = render_radiophonic_block
render_t8 = render_radiophonic
