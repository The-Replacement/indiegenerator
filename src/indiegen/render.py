"""schedule() and the block renderer.

This module is the render path: it imports nothing from ``compose/`` and rolls
no dice. A block is rendered once, and the filter state crosses the block
boundary as a value.

The bus graph:

    pad / poly_period / drone --> MAIN BUS (stereo, the pan law)
    pluck ---------------------> KS BUS --> dotted-eighth delay --> wet --> MAIN BUS

The KS bus's dry output is never summed: the delay *is* the instrument's
voice, which is what makes the signature a per-instrument fact. The reverb
taps the main bus after the bus lowpass, and its wet is summed back before
the section and fade gains, so the tail is faded with the music and cannot
create trailing silence.

When a lane declares no KS events, no delay send or no reverb, those stages
are skipped entirely - not "added as zeros" - so the signal never passes
through them.

The graph is walked a block at a time. The mix itself is the one array that
still spans the whole track, because the master chain needs its peak before
it can stage it; everything else - the voices, the delay, the filter, the
reverb, the gains - carries its state from one block to the next.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.errors import PlanError, RenderError
from indiegen.fx.delay import DelayState, delay_state, render_delay
from indiegen.fx.reverb import ReverbState, render_reverb, reverb_state
from indiegen.mix.bus import pan_gains
from indiegen.plan import (
    BassEvent,
    DroneEvent,
    Event,
    HatEvent,
    KickEvent,
    Plan,
    PluckEvent,
    PolyPeriodEvent,
    SnareEvent,
)
from indiegen.synth.drone import DroneState, drone_state, render_drone_block
from indiegen.synth.drums import DrumState, drum_state, render_drum_block
from indiegen.synth.env import fade_gain, note_envelope_block, section_gain
from indiegen.synth.filter import apply_biquad, initial_state, lowpass_sos
from indiegen.synth.ks import PluckState, pluck_state, render_pluck_block
from indiegen.synth.pad import PadState, pad_state, render_pad_block
from indiegen.synth.poly_period import PolyPeriodState, poly_period_state, render_poly_period_block

BLOCK_SIZE: int = 8192
RENDER_BLOCK: int = 131072

DrumEvent = KickEvent | SnareEvent | HatEvent | BassEvent

VoiceState = PadState | PolyPeriodState | DroneState | PluckState | DrumState


@dataclass(frozen=True)
class BusState:
    """The state of the bus stages, carried from one block to the next.

    A stage that the plan does not use has no state at all, and is skipped
    rather than run over zeros.
    """

    delay: DelayState | None
    filter: np.ndarray | None
    reverb: ReverbState | None


def schedule(plan: Plan) -> list[Event]:
    """Validate the events and put them in a stable, deterministic order."""
    events: list[Event] = []
    for event in plan.events:
        if event.start_frame + event.duration_frames > plan.duration_frames:
            raise PlanError("event runs past the end of the track", preset=plan.preset, seed=plan.seed)
        events.append(event)
    events.sort(key=lambda event: (event.start_frame, event.instrument, event.midi))
    return events


def _voice_state(event: Event, sample_rate: int) -> VoiceState:
    """The zero state of one event's voice."""
    if isinstance(event, PluckEvent):
        return pluck_state(event, sample_rate)
    if isinstance(event, PolyPeriodEvent):
        return poly_period_state(event)
    if isinstance(event, DroneEvent):
        return drone_state(event)
    if isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
        return drum_state(event)
    return pad_state(event)


def _voice_block(
    event: Event,
    sample_rate: int,
    start: int,
    stop: int,
    state: VoiceState,
) -> tuple[np.ndarray, VoiceState]:
    """The mono voice of one event, over its own frames ``[start, stop)``."""
    if isinstance(event, PluckEvent):
        assert isinstance(state, PluckState)
        return render_pluck_block(event, sample_rate, start, stop, state)
    if isinstance(event, PolyPeriodEvent):
        assert isinstance(state, PolyPeriodState)
        return render_poly_period_block(event, sample_rate, start, stop, state)
    if isinstance(event, DroneEvent):
        assert isinstance(state, DroneState)
        return render_drone_block(event, sample_rate, start, stop, state)
    if isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
        assert isinstance(state, DrumState)
        stereo, new_state = render_drum_block(event, sample_rate, start, stop, state)
        return stereo, new_state
    assert isinstance(state, PadState)
    return render_pad_block(event, sample_rate, start, stop, state)


def _bus_state(plan: Plan, events: list[Event]) -> BusState:
    """The zero state of the bus stages the plan actually uses."""
    has_ks = any(isinstance(event, PluckEvent) for event in events)
    delay: DelayState | None = None
    if has_ks and plan.delay_sends:
        delay = delay_state(plan.delay_sends[0])
    filter_state: np.ndarray | None = None
    if plan.fx_sends:
        send = plan.fx_sends[0]
        sos = lowpass_sos(send.cutoff_hz, send.q_num, send.q_den, plan.sample_rate)
        filter_state = initial_state(sos, plan.channels)
    reverb: ReverbState | None = None
    if plan.reverb is not None:
        reverb = reverb_state(plan.reverb)
    return BusState(delay=delay, filter=filter_state, reverb=reverb)


def _render_block(
    plan: Plan,
    events: list[Event],
    voices: list[VoiceState],
    bus: BusState,
    start: int,
    stop: int,
) -> tuple[np.ndarray, BusState]:
    """One block of the bus graph."""
    count = stop - start
    main = np.zeros((count, plan.channels), dtype=np.float64)
    ks_bus = np.zeros((count, plan.channels), dtype=np.float64)

    for index, event in enumerate(events):
        if isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            # A drum pattern plays itself: the hits carry their own pan, so
            # the block is already stereo.
            stereo, voices[index] = _voice_block(event, plan.sample_rate, start, stop, voices[index])
            main += stereo
            continue
        event_start = event.start_frame
        event_stop = event_start + event.duration_frames
        overlap_start = max(start, event_start)
        overlap_stop = min(stop, event_stop)
        if overlap_stop <= overlap_start:
            continue
        local_start = overlap_start - event_start
        local_stop = overlap_stop - event_start
        voice, voices[index] = _voice_block(event, plan.sample_rate, local_start, local_stop, voices[index])
        voice = voice * note_envelope_block(event, local_start, local_stop)
        left, right = pan_gains(event.pan_permille)
        offset = overlap_start - start
        end = offset + voice.size
        if isinstance(event, PluckEvent):
            ks_bus[offset:end, 0] += voice * left
            ks_bus[offset:end, 1] += voice * right
        else:
            main[offset:end, 0] += voice * left
            main[offset:end, 1] += voice * right

    delay = bus.delay
    filter_state = bus.filter
    reverb = bus.reverb

    if delay is not None and plan.delay_sends:
        wet, delay = render_delay(ks_bus, delay, plan.delay_sends[0])
        main += wet

    if filter_state is not None and plan.fx_sends:
        send = plan.fx_sends[0]
        sos = lowpass_sos(send.cutoff_hz, send.q_num, send.q_den, plan.sample_rate)
        filtered, filter_state = apply_biquad(sos, main, filter_state)
        if not bool(np.all(np.isfinite(filtered))):
            raise RenderError(
                "non-finite sample after filtering",
                preset=plan.preset,
                seed=plan.seed,
                block_index=start // BLOCK_SIZE,
            )
        level = float(np.power(10.0, send.send_millibels / 2000.0))
        main = main + (filtered - main) * level

    if reverb is not None and plan.reverb is not None:
        wet, reverb = render_reverb(main, reverb, plan.reverb, plan.sample_rate)
        main = main + wet

    gain = section_gain(plan, start, count) * fade_gain(plan, start, count)
    return main * gain[:, np.newaxis], BusState(delay=delay, filter=filter_state, reverb=reverb)


def render_plan(plan: Plan) -> np.ndarray:
    """Render the plan into a stereo float64 buffer."""
    frames = plan.duration_frames
    events = schedule(plan)
    voices = [_voice_state(event, plan.sample_rate) for event in events]
    bus = _bus_state(plan, events)
    mix = np.zeros((frames, plan.channels), dtype=np.float64)
    for start in range(0, frames, RENDER_BLOCK):
        stop = min(frames, start + RENDER_BLOCK)
        block, bus = _render_block(plan, events, voices, bus, start, stop)
        mix[start:stop] = block
    return mix
