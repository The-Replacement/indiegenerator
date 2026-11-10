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

from indiegen.control import (
    CONTROL_RATE,
    PAN_STREAM,
    VELOCITY_STREAM,
    PinkState,
    control_slice,
    pink_state,
    stream_key,
    uniform_stream,
)
from indiegen.errors import PlanError
from indiegen.gain import millibels_to_gain
from indiegen.mix.bus import pan_gains
from indiegen.plan import BassEvent, BassHit, DrumHit, HatEvent, KickEvent, RhythmEvent, SnareEvent
from indiegen.synth.env import dc_block
from indiegen.synth.filter import apply_biquad, initial_state, lowpass_sos, one_pole_highpass, one_pole_lowpass
from indiegen.synth.osc import midi_to_hz

DrumEvent = KickEvent | SnareEvent | HatEvent | BassEvent

SNARE_STREAM: int = 0
HAT_STREAM: int = 1
CLICK_STREAM: int = 2


@dataclass(frozen=True)
class PendingHit:
    """A hit whose voice runs past the end of the block.

    The voice is carried, not its parameters: the 1/f control signals were
    read at the hit's own frame, and that frame is in the block that has
    already gone by.
    """

    voice: np.ndarray
    left: float
    right: float
    skip: int


@dataclass(frozen=True)
class DrumState:
    """The 1/f control signals of a drum pattern, and the hit cursor.

    The control signals are pink noise at the control rate: the velocity
    drifts and the pan drifts. They are the difference between a machine and
    a player, and both are continuous gains, so they do not care where a
    block starts. The micro-timing drift is NOT here: it moves a hit to a
    different frame, and a frame that depended on the block size would make
    the render depend on the block size (c33). It is in the Plan instead.
    """

    velocity: PinkState
    pan: PinkState
    cursor: int
    pending: tuple[PendingHit, ...] = ()


def _highpass(signal: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    return one_pole_highpass(signal, cutoff_hz, sample_rate)


def _lowpass(signal: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    return one_pole_lowpass(signal, cutoff_hz, sample_rate)


def _envelope(count: int, decay_frames: int, sample_rate: int) -> np.ndarray:
    """A decaying envelope, with a two millisecond attack."""
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    decay = np.exp(-times * np.float64(sample_rate) / np.float64(max(1, decay_frames)))
    attack = np.minimum(1.0, times * np.float64(sample_rate) / 88.0)
    return np.asarray(decay * attack, dtype=np.float64)


SNAP_DECAY_FRAMES: int = 176
"""The snap's decay: four milliseconds at forty-four-one hundred hertz."""

SNAP_LEVEL: float = 0.5
"""How loud the snap is at snap_permille 1000, relative to the voice."""


def _snap(event: RhythmEvent, hit: DrumHit | BassHit, count: int, sample_rate: int) -> np.ndarray | float:
    """A short noise transient on the hit's attack, scaled by ``snap_permille``.

    The snap is the part of a hit that lives above the body: the beater, the
    stick, the string meeting the drum head. It is a four millisecond noise
    burst and it is exactly zero at ``snap_permille == 0``, so the default
    hit is the hit it always was.
    """
    if event.snap_permille <= 0:
        return 0.0
    click = uniform_stream(event.noise_seed, hit.grid_frame(), CLICK_STREAM, count)
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    decay = np.exp(-times * np.float64(sample_rate) / float(SNAP_DECAY_FRAMES))
    level = SNAP_LEVEL * (event.snap_permille / 1000.0)
    return np.asarray(click * decay * level, dtype=np.float64)


def render_kick(event: KickEvent, hit: DrumHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One kick: a round body with a fast pitch drop and a soft transient."""
    count = event.decay_frames
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    tau = np.float64(max(1.0, event.drop_frames / sample_rate))
    frequency = np.float64(event.drop_hz) + np.float64(event.body_hz - event.drop_hz) * np.exp(-times / tau)
    phase = 2.0 * np.pi * np.cumsum(frequency) / np.float64(sample_rate)
    body = np.sin(phase)
    envelope = _envelope(count, event.decay_frames, sample_rate)
    click = uniform_stream(event.noise_seed, hit.grid_frame(), CLICK_STREAM, count)
    click = click * np.exp(-times * np.float64(sample_rate) / 88.0)
    voice = body * envelope + click * 0.2 + _snap(event, hit, count, sample_rate)
    # The click is a burst of noise and carries an offset with it; the
    # blocker takes the offset and leaves the click.
    voice = dc_block(voice, sample_rate)
    return np.asarray(voice * velocity, dtype=np.float64)


def render_snare(event: SnareEvent, hit: DrumHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One snare: a body tone and a noise burst, decaying apart."""
    count = max(event.body_decay_frames, event.noise_decay_frames)
    times = np.arange(count, dtype=np.float64) / np.float64(sample_rate)
    body = np.sin(2.0 * math.pi * np.float64(event.body_hz) * times)
    body = body * _envelope(count, event.body_decay_frames, sample_rate)
    noise = uniform_stream(event.noise_seed, hit.grid_frame(), SNARE_STREAM, count)
    noise = _highpass(noise, 220.0, sample_rate)
    noise = noise * _envelope(count, event.noise_decay_frames, sample_rate)
    voice = body + noise * 0.8 + _snap(event, hit, count, sample_rate)
    return np.asarray(voice * velocity, dtype=np.float64)


def _band_limit(voice: np.ndarray, lowpass_hz: int, sample_rate: int) -> np.ndarray:
    """The hat's upper corner, applied to the assembled voice.

    The snap is added before this and is bounded with the body: it is a four
    millisecond broadband burst, and leaving it unshaped would put back the
    high-frequency energy this corner exists to remove (c31 measured the
    unshaped hat wall at 90 % of the mix's energy above 14 kHz).

    At ``lowpass_hz <= 0`` the voice is returned unchanged, so a lane that
    declares no corner renders exactly the voice c30 shipped.
    """
    if lowpass_hz <= 0:
        return voice
    sos = lowpass_sos(lowpass_hz, 1, 1, sample_rate)
    filtered, _ = apply_biquad(sos, voice, initial_state(sos, 1))
    return filtered


def render_hat(event: HatEvent, hit: DrumHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One closed hat: a short burst of band-passed noise.

    ``cutoff_hz`` is the lower corner, because a closed hat is noise above it;
    this is a band pass, not a low pass.
    """
    count = event.decay_frames
    noise = uniform_stream(event.noise_seed, hit.grid_frame(), HAT_STREAM, count)
    shaped = _highpass(noise, float(event.cutoff_hz), sample_rate)
    voice = shaped * _envelope(count, event.decay_frames, sample_rate) + _snap(event, hit, count, sample_rate)
    voice = _band_limit(voice, event.lowpass_hz, sample_rate)
    return np.asarray(voice * velocity, dtype=np.float64)


def render_bass(event: BassEvent, hit: BassHit, sample_rate: int, velocity: float) -> np.ndarray:
    """One bass note: a filtered saw with a soft edge.

    The saw is not centred: a ramp that starts at zero has a mean that
    depends on where it stopped, and a bass that carries a DC offset puts
    the whole mix's offset over the gate's limit. The blocker is the same
    one the plucked strings get.
    """
    count = event.decay_frames
    frequency = midi_to_hz(hit.midi)
    if getattr(event, "oscillator", "naive") == "bandlimited":
        # Fourier-series saw: harmonics up to Nyquist, alias-free by
        # construction. DC-free (no k=0 term).
        phase = np.arange(count, dtype=np.float64) * frequency / np.float64(sample_rate)
        harmonics = int(sample_rate // (2.0 * frequency)) if frequency > 0 else 1
        harmonics = max(1, harmonics)
        saw = np.zeros(count, dtype=np.float64)
        for k in range(1, harmonics + 1):
            saw += (2.0 / (np.pi * k)) * np.sin(2.0 * np.pi * k * phase)
    else:
        phase = np.cumsum(np.full(count, frequency, dtype=np.float64)) / np.float64(sample_rate)
        saw = 2.0 * (phase - np.floor(phase)) - 1.0
    shaped = _lowpass(saw, float(event.cutoff_hz), sample_rate)
    voice = shaped * _envelope(count, event.decay_frames, sample_rate)
    voice = dc_block(voice, sample_rate)
    return np.asarray(voice * velocity, dtype=np.float64)


def voice_frames(event: KickEvent | SnareEvent | HatEvent | BassEvent) -> int:
    """How long one hit of this instrument lasts."""
    if isinstance(event, SnareEvent):
        return max(event.body_decay_frames, event.noise_decay_frames)
    return event.decay_frames


def drum_state(event: RhythmEvent) -> DrumState:
    """The zero state of a drum pattern."""
    return DrumState(velocity=pink_state(), pan=pink_state(), cursor=0, pending=())


def _clip(value: float) -> float:
    """The control signal, bounded."""
    return max(-1.0, min(1.0, value))


def _drum_voice(event: DrumEvent, hit: DrumHit | BassHit, sample_rate: int, gain: float) -> np.ndarray:
    """One hit's voice, dispatched on the pattern's own tag."""
    match event.kind:
        case "kick":
            return render_kick(event, cast(DrumHit, hit), sample_rate, gain)
        case "snare":
            return render_snare(event, cast(DrumHit, hit), sample_rate, gain)
        case "hat":
            return render_hat(event, cast(DrumHit, hit), sample_rate, gain)
        case "bass":
            return render_bass(event, cast(BassHit, hit), sample_rate, gain)
        case unknown:
            raise PlanError(f"unknown drum kind {unknown!r}")


def _mix_pending(pending: tuple[PendingHit, ...], block: np.ndarray, count: int) -> list[PendingHit]:
    """Mix the tails of the hits that began in the block that has gone by.

    Tails that still extend past this block are re-carried (c31 bug).
    """
    carried: list[PendingHit] = []
    for tail in pending:
        until = min(count, tail.voice.size - tail.skip)
        if until <= 0:
            continue
        block[:until, 0] += tail.voice[tail.skip : tail.skip + until] * tail.left
        block[:until, 1] += tail.voice[tail.skip : tail.skip + until] * tail.right
        if tail.skip + until < tail.voice.size:
            carried.append(PendingHit(voice=tail.voice, left=tail.left, right=tail.right, skip=tail.skip + until))
    return carried


def render_drum_block(
    event: DrumEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: DrumState,
) -> tuple[np.ndarray, DrumState]:
    """One block of a drum pattern, as a stereo buffer.

    The hits are resolved at compose time, drift included; this plays them,
    with the 1/f control signals riding on the velocity and the pan.
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

    length = voice_frames(event)
    cursor = state.cursor
    while cursor < len(event.hits) and event.hits[cursor].frame + length <= start:
        cursor += 1

    # The hits whose voice began in the last block: their tail is here.
    carried = _mix_pending(state.pending, block, count)

    for hit in event.hits[cursor:]:
        if hit.frame >= stop:
            break
        if hit.frame < start:
            # Its voice began in the block that has gone by, and it is
            # already carried.
            continue
        frame = hit.frame
        index = (frame * CONTROL_RATE) // sample_rate - low
        drift = _clip(float(velocity_control[index])) * event.velocity_depth_millibels
        gain = millibels_to_gain(hit.velocity_millibels + drift)
        pan = event.pan_permille + int(round(_clip(float(pan_control[index])) * event.pan_drift_permille))
        left, right = pan_gains(pan)
        voice = _drum_voice(event, hit, sample_rate, gain)
        at = frame - start
        until = min(count, at + voice.size)
        if until <= at:
            continue
        block[at:until, 0] += voice[: until - at] * left
        block[at:until, 1] += voice[: until - at] * right
        if until < at + voice.size:
            # The tail is in the next block.
            carried.append(PendingHit(voice=voice, left=left, right=right, skip=until - at))

    return block, DrumState(
        velocity=velocity_state,
        pan=pan_state,
        cursor=cursor,
        pending=tuple(carried),
    )
