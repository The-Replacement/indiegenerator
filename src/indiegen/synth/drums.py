"""The drums: a kick, a snare, a hat and a bass.

Every drum hit is rendered whole. A hit is short - a few hundred
milliseconds - and it is independent of the hits around it, so there is
nothing to carry from one hit to the next: the 1/f control signals are the
only state, and they are cut once for the pattern.

The noise comes from the project's counter-based mixer, not from a random
number generator: an instrument may not roll dice, and the variation it
needs is the integer seed on the event.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np
from scipy.signal import lfilter

from indiegen.mix.bus import pan_gains
from indiegen.plan import BassEvent, BassHit, DrumHit, HatEvent, KickEvent, RhythmEvent, SnareEvent
from indiegen.synth.noise import CONTROL_RATE, PinkState, control_slice, pink_state, stream_key, uniform_stream

SNARE_STREAM: int = 0
HAT_STREAM: int = 1
CLICK_STREAM: int = 2
VELOCITY_STREAM: int = 0
PAN_STREAM: int = 1
TIMING_STREAM: int = 2


@dataclass(frozen=True)
class DrumState:
    """The 1/f control signals of a drum pattern, and the hit cursor.

    The control signals are pink noise at the control rate: the velocity
    drifts, the pan drifts, and the micro-timing drifts. They are the
    difference between a machine and a player.
    """

    velocity: PinkState
    pan: PinkState
    timing: PinkState
    cursor: int


def _highpass(signal: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """A one-pole high pass: (1 - z^-1) / (1 - r z^-1)."""
    coefficient = math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    filtered: np.ndarray = lfilter([1.0, -1.0], [1.0, -coefficient], signal)
    return filtered


def _lowpass(signal: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """A one-pole low pass: (1 - r) / (1 - r z^-1)."""
    coefficient = math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    filtered: np.ndarray = lfilter([1.0 - coefficient], [1.0, -coefficient], signal)
    return filtered


def _envelope(count: int, decay_frames: int, sample_rate: int) -> np.ndarray:
    """A decaying envelope, with a two millisecond attack."""
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    decay = np.exp(-times * np.float64(sample_rate) / np.float64(max(1, decay_frames)))
    attack = np.minimum(1.0, times * np.float64(sample_rate) / 88.0)
    return np.asarray(decay * attack, dtype=np.float64)


def render_kick(event: KickEvent, hit: DrumHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One kick: a round body with a fast pitch drop and a soft transient."""
    count = event.decay_frames
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    tau = np.float64(max(1.0, event.drop_frames / sample_rate))
    frequency = np.float64(event.drop_hz) + np.float64(event.body_hz - event.drop_hz) * np.exp(-times / tau)
    phase = 2.0 * np.pi * np.cumsum(frequency) / np.float64(sample_rate)
    body = np.sin(phase)
    envelope = _envelope(count, event.decay_frames, sample_rate)
    click = uniform_stream(event.noise_seed, hit.frame, CLICK_STREAM, count)
    click = click * np.exp(-times * np.float64(sample_rate) / 88.0)
    voice = body * envelope + click * 0.2
    return np.asarray(voice * velocity, dtype=np.float64)


def render_snare(event: SnareEvent, hit: DrumHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One snare: a body tone and a noise burst, decaying apart."""
    count = max(event.body_decay_frames, event.noise_decay_frames)
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    body = np.sin(2.0 * math.pi * np.float64(event.body_hz) * times)
    body = body * _envelope(count, event.body_decay_frames, sample_rate)
    noise = uniform_stream(event.noise_seed, hit.frame, SNARE_STREAM, count)
    noise = _highpass(noise, 220.0, sample_rate)
    noise = noise * _envelope(count, event.noise_decay_frames, sample_rate)
    voice = body + noise * 0.8
    return np.asarray(voice * velocity, dtype=np.float64)


def render_hat(event: HatEvent, hit: DrumHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One closed hat: a short burst of high-passed noise."""
    count = event.decay_frames
    noise = uniform_stream(event.noise_seed, hit.frame, HAT_STREAM, count)
    shaped = _highpass(noise, float(event.cutoff_hz), sample_rate)
    voice = shaped * _envelope(count, event.decay_frames, sample_rate)
    return np.asarray(voice * velocity, dtype=np.float64)


def render_bass(event: BassEvent, hit: BassHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One bass note: a filtered saw with a soft edge."""
    count = event.decay_frames
    frequency = 440.0 * math.pow(2.0, (hit.midi - 69) / 12.0)
    phase = np.cumsum(np.full(count, frequency, dtype=np.float64)) / np.float64(sample_rate)
    saw = 2.0 * (phase - np.floor(phase)) - 1.0
    shaped = _lowpass(saw, float(event.cutoff_hz), sample_rate)
    voice = shaped * _envelope(count, event.decay_frames, sample_rate)
    return np.asarray(voice * velocity, dtype=np.float64)


def voice_frames(event: KickEvent | SnareEvent | HatEvent | BassEvent) -> int:
    """How long one hit of this instrument lasts."""
    if isinstance(event, SnareEvent):
        return max(event.body_decay_frames, event.noise_decay_frames)
    return event.decay_frames


def drum_state(event: RhythmEvent) -> DrumState:
    """The zero state of a drum pattern."""
    return DrumState(velocity=pink_state(), pan=pink_state(), timing=pink_state(), cursor=0)


def _clip(value: float) -> float:
    """The control signal, bounded."""
    return max(-1.0, min(1.0, value))


def render_drum_block(
    event: KickEvent | SnareEvent | HatEvent | BassEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: DrumState,
) -> tuple[np.ndarray, DrumState]:
    """One block of a drum pattern, as a stereo buffer.

    The hits are resolved at compose time; this plays them, with the 1/f
    control signals riding on the velocity, the pan and the micro-timing.
    """
    count = stop - start
    block = np.zeros((count, 2), dtype=np.float64)
    low = start * CONTROL_RATE // sample_rate
    high = (stop - 1) * CONTROL_RATE // sample_rate + 1

    velocity_control, velocity_state = control_slice(
        state.velocity, stream_key(event.noise_seed, 0, VELOCITY_STREAM), low, high, CONTROL_RATE
    )
    pan_control, pan_state = control_slice(
        state.pan, stream_key(event.noise_seed, 1, PAN_STREAM), low, high, CONTROL_RATE
    )
    timing_control, timing_state = control_slice(
        state.timing, stream_key(event.noise_seed, 2, TIMING_STREAM), low, high, CONTROL_RATE
    )

    length = voice_frames(event)
    cursor = state.cursor
    while cursor < len(event.hits) and event.hits[cursor].frame + length <= start:
        cursor += 1

    for hit in event.hits[cursor:]:
        if hit.frame >= stop:
            break
        offset = int(
            round(
                _clip(float(timing_control[(hit.frame * CONTROL_RATE) // sample_rate - low]))
                * event.micro_timing_frames
            )
        )
        frame = hit.frame + offset
        if frame < start or frame >= stop:
            continue
        index = (frame * CONTROL_RATE) // sample_rate - low
        drift = _clip(float(velocity_control[index])) * event.velocity_depth_millibels
        gain = math.pow(10.0, (hit.velocity_millibels + drift) / 2000.0)
        pan = event.pan_permille + int(round(_clip(float(pan_control[index])) * event.pan_drift_permille))
        left, right = pan_gains(pan)
        if isinstance(event, BassEvent):
            voice = render_bass(event, cast(BassHit, hit), sample_rate, gain)
        elif isinstance(event, KickEvent):
            voice = render_kick(event, cast(DrumHit, hit), sample_rate, gain)
        elif isinstance(event, SnareEvent):
            voice = render_snare(event, cast(DrumHit, hit), sample_rate, gain)
        else:
            voice = render_hat(event, cast(DrumHit, hit), sample_rate, gain)
        at = frame - start
        until = min(count, at + voice.size)
        if until <= at:
            continue
        block[at:until, 0] += voice[: until - at] * left
        block[at:until, 1] += voice[: until - at] * right

    return block, DrumState(velocity=velocity_state, pan=pan_state, timing=timing_state, cursor=cursor)
