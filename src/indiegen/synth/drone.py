"""The spectral drone stack.

Each partial drifts on its own 1/f signal, in detune and in amplitude, and
the drift is clipped to the declared depth so the brief's five-to-fifteen
cent bound is hard rather than approximate. The partials are exact rational
ratios of the fundamental, so the beating between them is the movement.

The stack is rendered a block at a time. The phase of a partial is the sum
of its frequencies, so it carries a running total; the drift streams are
counter-based, so they carry the state of their one-pole filters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from indiegen.plan import DroneEvent
from indiegen.synth.env import dc_block_state
from indiegen.synth.noise import (
    AMPLITUDE_STREAM,
    CONTROL_RATE,
    DETUNE_STREAM,
    PinkState,
    control_count,
    control_slice,
    interpolate_block,
    pink_state,
    stream_key,
)
from indiegen.synth.osc import cumulative_sum, midi_to_hz


@dataclass(frozen=True)
class DroneState:
    """The drift streams, the phase and the DC blocker of a drone stack."""

    detune: tuple[PinkState, ...]
    amplitude: tuple[PinkState, ...]
    carries: tuple[float, ...]
    dc: np.ndarray


def drone_state(event: DroneEvent) -> DroneState:
    """The zero state of a drone stack."""
    return DroneState(
        detune=tuple(pink_state() for _ in event.partials),
        amplitude=tuple(pink_state() for _ in event.partials),
        carries=tuple(0.0 for _ in event.partials),
        dc=np.zeros(1, dtype=np.float64),
    )


def render_drone_block(
    event: DroneEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: DroneState,
) -> tuple[np.ndarray, DroneState]:
    """One drone stack, over the local frames ``[start, stop)``."""
    count = stop - start
    base = midi_to_hz(event.midi)
    total_control = control_count(event.duration_frames, sample_rate)
    low = start * CONTROL_RATE // sample_rate
    high = (stop - 1) * CONTROL_RATE // sample_rate + 1

    voice = np.zeros(count, dtype=np.float64)
    detune_states = list(state.detune)
    amplitude_states = list(state.amplitude)
    carries = list(state.carries)

    for index, partial in enumerate(event.partials):
        detune_control, detune_states[index] = control_slice(
            detune_states[index],
            stream_key(event.noise_seed, index, DETUNE_STREAM),
            low,
            high,
            CONTROL_RATE,
        )
        detune_signal = np.clip(
            interpolate_block(detune_control, count, sample_rate, start, low, total_control),
            -1.0,
            1.0,
        )
        detune = partial.detune_cents + partial.detune_lfo.depth_cents * detune_signal
        ratio = partial.ratio.numerator / partial.ratio.denominator
        frequency = base * ratio * np.exp(detune * (math.log(2.0) / 1200.0))
        phase, carries[index] = cumulative_sum(carries[index], frequency)

        amplitude_control, amplitude_states[index] = control_slice(
            amplitude_states[index],
            stream_key(event.noise_seed, index, AMPLITUDE_STREAM),
            low,
            high,
            CONTROL_RATE,
        )
        amplitude_signal = np.clip(
            interpolate_block(amplitude_control, count, sample_rate, start, low, total_control),
            -1.0,
            1.0,
        )
        millibels = partial.amplitude_millibels + partial.amplitude_lfo.depth_millibels * amplitude_signal
        voice += np.sin(2.0 * np.pi * phase / sample_rate) * np.exp(millibels * (math.log(10.0) / 2000.0))

    blocked, dc_carry = dc_block_state(voice, sample_rate, state.dc)
    return blocked, DroneState(
        detune=tuple(detune_states),
        amplitude=tuple(amplitude_states),
        carries=tuple(carries),
        dc=dc_carry,
    )


def render_drone(event: DroneEvent, sample_rate: int) -> np.ndarray:
    """One drone stack, as a mono buffer."""
    blocked, _ = render_drone_block(event, sample_rate, 0, event.duration_frames, drone_state(event))
    return blocked
