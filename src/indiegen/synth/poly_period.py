"""The poly-period voice.

The oscillator runs on for the whole track; only the envelope cycles. Each
voice sounds for its on-window at the start of every cycle and is exactly
silent in between, so a cycle boundary is never a click and the silence
between cycles is exact zero rather than nearly zero.
"""

from __future__ import annotations

import math

import numpy as np

from indiegen.plan import PolyPeriodEvent, PolyPeriodVoice
from indiegen.synth.env import dc_block
from indiegen.synth.osc import midi_to_hz


def voice_envelope(voice: PolyPeriodVoice, count: int, attack: int, release: int) -> np.ndarray:
    """The periodic envelope of one voice."""
    envelope = np.zeros(count, dtype=np.float64)
    start = voice.phase_frames
    while start < count:
        end = min(start + voice.on_frames, count)
        length = end - start
        if length > 0:
            shape = np.ones(length, dtype=np.float64)
            if attack > 0:
                ramp = min(attack, length)
                shape[:ramp] = np.linspace(0.0, 1.0, ramp)
            if release > 0:
                ramp = min(release, length)
                shape[length - ramp :] = np.linspace(1.0, 0.0, ramp)
            envelope[start:end] = np.maximum(envelope[start:end], shape)
        start += voice.period_frames
    return envelope


def render_poly_period(event: PolyPeriodEvent, sample_rate: int) -> np.ndarray:
    """One poly-period loop, as a mono buffer."""
    count = event.duration_frames
    times = np.arange(count, dtype=np.float64) / sample_rate
    voice = np.zeros(count, dtype=np.float64)
    for entry in event.voices:
        envelope = voice_envelope(entry, count, event.attack_frames, event.release_frames)
        base = midi_to_hz(entry.midi)
        for partial in event.partials:
            ratio = partial.ratio.numerator / partial.ratio.denominator
            frequency = base * ratio * math.pow(2.0, partial.detune_cents / 1200.0)
            phase = 2.0 * math.pi * np.cumsum(frequency) / sample_rate
            voice += envelope * np.sin(phase) * math.pow(10.0, partial.amplitude_millibels / 2000.0)
    del times
    return dc_block(voice, sample_rate)
