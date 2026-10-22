"""The poly-period voice.

The oscillator runs on for the whole track; only the envelope cycles. Each
voice sounds for its on-window at the start of every cycle and is exactly
silent in between, so a cycle boundary is never a click and the silence
between cycles is exact zero rather than nearly zero.

The phase runs continuously through the track and the envelope is the only
thing that cycles. The voices have different periods, so their on-windows
never line up and the superpattern does not repeat.

The voice is rendered a block at a time. The phase is the sum of the
partial's frequency, so every voice and partial carries a running total.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain
from indiegen.plan import PolyPeriodEvent, PolyPeriodVoice
from indiegen.synth.env import dc_block_state
from indiegen.synth.osc import cumulative_sum, midi_to_hz


@dataclass(frozen=True)
class PolyPeriodState:
    """The running phase of every voice and partial, and the DC blocker."""

    carries: tuple[float, ...]
    dc: np.ndarray


def poly_period_state(event: PolyPeriodEvent) -> PolyPeriodState:
    """The zero state of a poly-period loop."""
    return PolyPeriodState(
        carries=tuple(0.0 for _ in range(len(event.voices) * len(event.partials))),
        dc=np.zeros(1, dtype=np.float64),
    )


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
    carries = list(state.carries)
    index = 0
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
            phase, carries[index] = cumulative_sum(carries[index], np.full(count, frequency, dtype=np.float64))
            voice += (
                envelope * np.sin(2.0 * np.pi * phase / sample_rate) * millibels_to_gain(partial.amplitude_millibels)
            )
            index += 1
    blocked, dc_carry = dc_block_state(voice, sample_rate, state.dc)
    return blocked, PolyPeriodState(carries=tuple(carries), dc=dc_carry)


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
