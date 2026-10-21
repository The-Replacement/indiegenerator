"""The poly-period voice.

The oscillator runs on for the whole track; only the envelope cycles. Each
voice sounds for its on-window at the start of every cycle and is exactly
silent in between, so a cycle boundary is never a click and the silence
between cycles is exact zero rather than nearly zero.

The voice is rendered a block at a time. The envelope of a cycle is cut over
the whole cycle and sliced, because the ramp of a cycle is a function of the
cycle and not of the block: a ramp cut short would be a different ramp.

KNOWN DEFECT: the phase does not advance. The partial's frequency is a
plain float, and ``np.cumsum`` of a float is a one-element array, so the
phase is the same number for the whole event and the voice is the envelope
times a constant. The loops of T1 are therefore inaudible: the voice's RMS
is 0.0002 against the drone's, some 74 dB down. This is kept exactly as it
is, because the block-wise render must not move the audio; the fix is to
carry the running phase the way the pad and the drone do, which moves the
ambient golden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from indiegen.plan import PolyPeriodEvent, PolyPeriodVoice
from indiegen.synth.env import dc_block_state
from indiegen.synth.osc import midi_to_hz


@dataclass(frozen=True)
class PolyPeriodState:
    """The DC blocker of a poly-period loop."""

    dc: np.ndarray


def poly_period_state(event: PolyPeriodEvent) -> PolyPeriodState:
    """The zero state of a poly-period loop."""
    return PolyPeriodState(dc=np.zeros(1, dtype=np.float64))


def voice_envelope_block(
    voice: PolyPeriodVoice,
    start: int,
    stop: int,
    count: int,
    attack: int,
    release: int,
) -> np.ndarray:
    """The periodic envelope of one voice, over the frames ``[start, stop)``.

    The shape of a cycle is cut over the whole cycle and sliced, because the
    ramp of a cycle is a function of the cycle and not of the block: a ramp
    cut short would be a different ramp.
    """
    envelope = np.zeros(stop - start, dtype=np.float64)
    cycle = voice.phase_frames
    while cycle < stop:
        window_start = cycle
        window_end = min(cycle + voice.on_frames, count)
        overlap_start = max(window_start, start)
        overlap_end = min(window_end, stop)
        if overlap_end > overlap_start:
            length = overlap_end - overlap_start
            base = overlap_start - window_start
            window_length = window_end - window_start
            shape = np.ones(length, dtype=np.float64)
            if attack > 0:
                ramp = min(attack, window_length)
                values = np.linspace(0.0, 1.0, ramp)
                begin = base
                end = min(ramp, base + length)
                if end > begin:
                    shape[: end - begin] = values[begin:end]
            if release > 0:
                ramp = min(release, window_length)
                values = np.linspace(1.0, 0.0, ramp)
                ramp_start = window_length - ramp
                begin = max(base, ramp_start)
                end = base + length
                if end > begin:
                    shape[begin - base : end - base] = values[begin - ramp_start : end - ramp_start]
            envelope[overlap_start - start : overlap_end - start] = np.maximum(
                envelope[overlap_start - start : overlap_end - start],
                shape,
            )
        cycle += voice.period_frames
    return envelope


def render_poly_period_block(
    event: PolyPeriodEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: PolyPeriodState,
) -> tuple[np.ndarray, PolyPeriodState]:
    """One poly-period loop, over the local frames ``[start, stop)``."""
    count = stop - start
    voice = np.zeros(count, dtype=np.float64)
    for entry in event.voices:
        envelope = voice_envelope_block(
            entry,
            start,
            stop,
            event.duration_frames,
            event.attack_frames,
            event.release_frames,
        )
        base = midi_to_hz(entry.midi)
        for partial in event.partials:
            ratio = partial.ratio.numerator / partial.ratio.denominator
            frequency = base * ratio * math.pow(2.0, partial.detune_cents / 1200.0)
            phase = 2.0 * np.pi * np.cumsum(frequency) / sample_rate
            voice += envelope * np.sin(phase) * math.pow(10.0, partial.amplitude_millibels / 2000.0)
    blocked, dc_carry = dc_block_state(voice, sample_rate, state.dc)
    return blocked, PolyPeriodState(dc=dc_carry)


def render_poly_period(event: PolyPeriodEvent, sample_rate: int) -> np.ndarray:
    """One poly-period loop, as a mono buffer."""
    blocked, _ = render_poly_period_block(
        event,
        sample_rate,
        0,
        event.duration_frames,
        poly_period_state(event),
    )
    return blocked
