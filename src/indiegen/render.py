"""schedule() and the block renderer.

This module is the render path: it imports nothing from ``compose/`` and rolls
no dice. A block is rendered once, and the filter state crosses the block
boundary as a value.

The bus graph:

    pad / poly_period / drone --> MAIN BUS (stereo, the pan law)
    pluck ---------------------> KS BUS --> [dub chain] --> dotted-eighth delay --> wet --> MAIN BUS
    MAIN BUS --> [Frippertronics send] --> wet --> MAIN BUS
    MAIN BUS --> [reverb tap] --> reverb --> wet --> MAIN BUS
    MAIN BUS --> [sidechain: ducked by the kick] --> + kick
    MAIN BUS --> [the bus trims] --> [the mono low end]

The KS bus's dry output is never summed: the delay *is* the instrument's
voice, which is what makes the signature a per-instrument fact. The reverb
taps the main bus after the bus lowpass, and its wet is summed back before
the section and fade gains, so the tail is faded with the music and cannot
create trailing silence.

Every send has a level and every level is read: the delay's and the
reverb's send millibels scale what goes into the effect, so a send declared
at -6 dB is a send at -6 dB and not at unity.

When a lane declares no KS events, no delay send or no reverb, those stages
are skipped entirely - not "added as zeros" - so the signal never passes
through them.

The graph is walked a block at a time. The mix itself is the one array that
still spans the whole track, because the master chain needs its peak before
it can stage it; everything else - the voices, the delay, the filter, the
reverb, the gains - carries its state from one block to the next.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np

from indiegen.errors import PlanError
from indiegen.fx.delay import DelayState, delay_state, render_delay
from indiegen.fx.dub import DubChainState, dub_chain_state, render_dub_chain
from indiegen.fx.frippertronics import FrippertronicsState, frippertronics_state, render_frippertronics
from indiegen.fx.reverb import ReverbState, render_reverb, reverb_state
from indiegen.gain import millibels_to_gain
from indiegen.mix.bus import bus_gains, pan_gains, silent_bus, trim
from indiegen.mix.masking import DUCK_HIGH_HZ, DUCK_LOW_HZ, apply_duck, duck_band, duck_envelope
from indiegen.mix.sidechain import SidechainState, render_sidechain, sidechain_state
from indiegen.plan import (
    BassEvent,
    Event,
    HatEvent,
    KickEvent,
    Plan,
    PluckEvent,
    SnareEvent,
)
from indiegen.synth.drone import DroneState, drone_state, render_drone_block
from indiegen.synth.drumcomp import DrumCompState, drum_comp_state, render_drum_comp_block
from indiegen.synth.drums import DrumState, drum_state, render_drum_block
from indiegen.synth.env import fade_gain, note_envelope_block, section_gain
from indiegen.synth.filter import apply_biquad, bandpass_sos, initial_state, lowpass_sos
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
    frippertronics: FrippertronicsState | None
    dub: DubChainState | None
    sidechain: SidechainState | None
    trims: dict[str, float]
    drum_comp: DrumCompState | None
    duck: np.ndarray | None = None


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
    match event.kind:
        case "pluck":
            return pluck_state(event, sample_rate)
        case "poly_period":
            return poly_period_state(event)
        case "drone":
            return drone_state(event)
        case "kick" | "snare" | "hat" | "bass":
            return drum_state(event)
        case "pad":
            return pad_state(event)
        case unknown:
            raise PlanError(f"unknown event kind {unknown!r}")


def _voice_block(
    event: Event,
    sample_rate: int,
    start: int,
    stop: int,
    state: VoiceState,
) -> tuple[np.ndarray, VoiceState]:
    """The mono voice of one event, over its own frames ``[start, stop)``.

    The dispatch is on the event's own tag and the state is ``cast`` rather
    than ``assert``ed: an ``assert`` is stripped under ``python -O``, and a
    mismatched state must not reach the renderer just because optimisation is
    on. The cast is a static promise, checked by the tests at every block.
    """
    match event.kind:
        case "pluck":
            return render_pluck_block(event, sample_rate, start, stop, cast(PluckState, state))
        case "poly_period":
            return render_poly_period_block(event, sample_rate, start, stop, cast(PolyPeriodState, state))
        case "drone":
            return render_drone_block(event, sample_rate, start, stop, cast(DroneState, state))
        case "kick" | "snare" | "hat" | "bass":
            return render_drum_block(event, sample_rate, start, stop, cast(DrumState, state))
        case "pad":
            return render_pad_block(event, sample_rate, start, stop, cast(PadState, state))
        case unknown:
            raise PlanError(f"unknown event kind {unknown!r}")


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
    frippertronics: FrippertronicsState | None = None
    if plan.frippertronics is not None:
        frippertronics = frippertronics_state(plan.frippertronics)
    dub: DubChainState | None = None
    sidechain: SidechainState | None = None
    if plan.dub_chain is not None:
        dub = dub_chain_state(plan.dub_chain, plan.sample_rate)
        sidechain = sidechain_state()
    drum_comp = drum_comp_state() if plan.drum_bus_comp is not None else None
    # c31: the mask stage's filter state. The duck's band split restarts from
    # silence if it cannot carry a history, and a step every block is audible,
    # so a lane that declares a duck gets its state here.
    duck: np.ndarray | None = None
    if plan.duck is not None:
        duck = initial_state(bandpass_sos(DUCK_LOW_HZ, DUCK_HIGH_HZ, plan.sample_rate), plan.channels)
    return BusState(
        delay=delay,
        filter=filter_state,
        reverb=reverb,
        frippertronics=frippertronics,
        dub=dub,
        sidechain=sidechain,
        trims=bus_gains(plan.bus_gains),
        drum_comp=drum_comp,
        duck=duck,
    )


def _section_index_of(frame: int, plan: Plan) -> int:
    """The index of the section containing ``frame``, or -1 when none."""
    for index, section in enumerate(plan.sections):
        if section.start_frame <= frame < section.end_frame:
            return index
    return -1


def _is_muted(event: Event, section_index: int, plan: Plan) -> bool:
    """Whether ``event`` is silenced in its section by an arrangement mute."""
    return (event.kind, section_index) in {
        (mute.kind, mute.section_index) for mute in plan.arrangement_mutes if mute.mute == 1000
    }


def _mix_voices(
    plan: Plan,
    events: list[Event],
    voices: list[VoiceState],
    trims: dict[str, float],
    start: int,
    stop: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sum this block's voices into the main, kick and Karplus-Strong buses.

    The kick is kept apart because the sidechain ducks everything else with
    it; the plucks are kept apart because the delay and the dub chain are fed
    from them and not from the whole mix.
    """
    count = stop - start
    main = silent_bus(count, plan.channels)
    drum_bus = silent_bus(count, plan.channels)
    ks_bus = silent_bus(count, plan.channels)

    for index, event in enumerate(events):
        si = _section_index_of(event.start_frame, plan)
        if _is_muted(event, si, plan):
            # Advance voice state but produce no audio.
            _, voices[index] = _voice_block(event, plan.sample_rate, start, stop, voices[index])
            continue
        if isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            # A drum pattern plays itself: the hits carry their own pan, so
            # the block is already stereo.
            stereo, voices[index] = _voice_block(event, plan.sample_rate, start, stop, voices[index])
            level = trim(trims, event.kind)
            drum_bus += stereo * level
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
        voice = voice * trim(trims, event.kind)
        left, right = pan_gains(event.pan_permille)
        offset = overlap_start - start
        end = offset + voice.size
        if isinstance(event, PluckEvent):
            ks_bus[offset:end, 0] += voice * left
            ks_bus[offset:end, 1] += voice * right
        else:
            main[offset:end, 0] += voice * left
            main[offset:end, 1] += voice * right

    return main, drum_bus, ks_bus


def _apply_effects(
    plan: Plan,
    main: np.ndarray,
    ks_bus: np.ndarray,
    bus: BusState,
    start: int,
    stop: int,
    count: int,
    kick_hits: list[int],
) -> tuple[np.ndarray, BusState]:
    """The effect chain of one block: dub, delay, filter, Frippertronics, reverb, sidechain.

    Returns the updated main bus and the bus state carrying the effect states
    across the block boundary. The drum-bus compressor and the section/fade
    gains are applied by the caller.
    """
    delay = bus.delay
    filter_state = bus.filter
    reverb = bus.reverb
    frippertronics = bus.frippertronics
    dub = bus.dub
    sidechain = bus.sidechain

    if dub is not None and plan.dub_chain is not None:
        # T10: the stabs are bit-reduced and bandpassed before the delay.
        ks_bus, dub = render_dub_chain(ks_bus, dub, plan.dub_chain, plan.sample_rate)
        level = millibels_to_gain(plan.dub_chain.send_millibels)
        ks_bus = ks_bus * level

    if delay is not None and plan.delay_sends:
        for send in plan.delay_sends:
            level = millibels_to_gain(send.send_millibels)
            wet, delay = render_delay(ks_bus * level, delay, send)
            main += wet

    if filter_state is not None and plan.fx_sends:
        for fx_send in plan.fx_sends:
            sos = lowpass_sos(fx_send.cutoff_hz, fx_send.q_num, fx_send.q_den, plan.sample_rate)
            filtered, filter_state = apply_biquad(sos, main, filter_state)
            from indiegen.errors import raise_if_nonfinite

            raise_if_nonfinite(
                filtered,
                "non-finite sample after filtering",
                preset=plan.preset,
                seed=plan.seed,
                block_index=start // BLOCK_SIZE,
            )
            level = millibels_to_gain(fx_send.send_millibels)
            main = main + (filtered - main) * level

    if frippertronics is not None and plan.frippertronics is not None:
        # T3: the long feedback delay, summed back into the main bus.
        wet, frippertronics = render_frippertronics(main, frippertronics, plan.frippertronics, plan.sample_rate)
        level = millibels_to_gain(plan.frippertronics.send_millibels)
        main = main + wet * level

    if reverb is not None and plan.reverb is not None:
        # The tap is the send: it is taken at the declared level, and the
        # reverb's wet comes back at unity.
        level = millibels_to_gain(plan.reverb.send_millibels)
        wet, reverb = render_reverb(main * level, reverb, plan.reverb, plan.sample_rate)
        main = main + wet

    if sidechain is not None and plan.dub_chain is not None:
        # T10: everything but the kick is ducked by the kick.
        gain, sidechain = render_sidechain(
            start,
            count,
            kick_hits,
            sidechain,
            plan.dub_chain.sidechain_release_frames,
            plan.dub_chain.sidechain_depth_millibels,
        )
        main = main * gain[:, np.newaxis]

    return main, replace(
        bus,
        delay=delay,
        filter=filter_state,
        reverb=reverb,
        frippertronics=frippertronics,
        dub=dub,
        sidechain=sidechain,
    )


def _duck_stage(
    plan: Plan,
    main: np.ndarray,
    bus: BusState,
    start: int,
    count: int,
    bass_hits: list[int],
) -> tuple[np.ndarray, BusState]:
    """c31: the bass-keyed 200-500 Hz duck, on the main bus.

    This runs BEFORE the drum bus is summed in, and that placement is the
    point: the bass lives in the drum bus, so a duck applied after the sum
    would attenuate the bass with its own envelope.

    The band carries its filter state across blocks; the envelope carries
    nothing, because every value of it is a function of the absolute frame
    index and the hit list.
    """
    if plan.duck is None or bus.duck is None:
        return main, bus
    band, duck = duck_band(main, bus.duck, plan.sample_rate)
    gain = duck_envelope(start, count, bass_hits, plan.duck)
    return apply_duck(main, gain, band, plan.duck), replace(bus, duck=duck)


def _render_block(
    plan: Plan,
    events: list[Event],
    voices: list[VoiceState],
    bus: BusState,
    start: int,
    stop: int,
    kick_hits: list[int],
    bass_hits: list[int],
) -> tuple[np.ndarray, BusState]:
    """One block of the bus graph: the voices, then the effect chain."""
    count = stop - start
    main, drum_bus, ks_bus = _mix_voices(plan, events, voices, bus.trims, start, stop)

    main, bus = _apply_effects(plan, main, ks_bus, bus, start, stop, count, kick_hits)

    # c31: the masking duck carves the bass's band out of the main bus. It has
    # to run before the drum bus joins, or the bass would duck itself.
    main, bus = _duck_stage(plan, main, bus, start, count, bass_hits)

    # Drum-bus compressor: applied to the drum bus before it joins the mix.
    drum_comp = bus.drum_comp
    if drum_comp is not None and plan.drum_bus_comp is not None:
        drum_bus, drum_comp = render_drum_comp_block(drum_bus, drum_comp, plan.drum_bus_comp, plan.sample_rate)
    # The drum bus is summed into the main mix here.
    main += drum_bus

    gain = section_gain(plan, start, count) * fade_gain(plan, start, count)
    main = main * gain[:, np.newaxis]

    return main, replace(bus, drum_comp=drum_comp)


def render_plan(plan: Plan) -> np.ndarray:
    """Render the plan into a stereo float64 buffer."""
    mix = silent_bus(plan.duration_frames, plan.channels)
    _render_into(plan, mix)
    return mix


def _render_into(plan: Plan, target: np.ndarray) -> None:
    """Render the plan's blocks into ``target``, one render block at a time."""
    frames = plan.duration_frames
    events = schedule(plan)
    voices = [_voice_state(event, plan.sample_rate) for event in events]
    bus = _bus_state(plan, events)
    # c33: the bus keyframes are GRID frames, not played frames. The duck and
    # the kick sidechain were always keyed on where the arrangement put a hit,
    # and the drift moved the audio away from that key by up to
    # micro_timing_frames. Keeping the grid here makes c33 a representation
    # move that changes no audio. Re-keying them on the played frame is a
    # real, audible change (measured: 9.4e-2 in the 200-500 Hz band on
    # motorik) and it belongs in its own change with its own gates.
    kick_hits = [hit.grid_frame() for event in events if isinstance(event, KickEvent) for hit in event.hits]
    bass_hits = sorted(hit.grid_frame() for event in events if isinstance(event, BassEvent) for hit in event.hits)
    for start in range(0, frames, RENDER_BLOCK):
        stop = min(frames, start + RENDER_BLOCK)
        block, bus = _render_block(plan, events, voices, bus, start, stop, kick_hits, bass_hits)
        target[start:stop] = block


def write_mix_stem(plan: Plan, path: Path) -> tuple[int, int]:
    """Render the plan to a float64 memmap stem and return its shape.

    The stem is the mix on disk: the master reads it twice and the gates
    read it through the memmap, so the whole-track array never has to be on
    the heap. The float64 bits are the bytes the in-memory render would have
    held, so the master is bit-identical over the stem.
    """
    frames = plan.duration_frames
    shape = (frames, plan.channels)
    stem = np.memmap(path, dtype=np.float64, mode="w+", shape=shape)
    _render_into(plan, stem)
    stem.flush()
    del stem
    return shape
