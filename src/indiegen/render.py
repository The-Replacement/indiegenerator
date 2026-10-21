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
"""

from __future__ import annotations

import numpy as np

from indiegen.errors import PlanError, RenderError
from indiegen.fx.delay import delay_state, render_delay
from indiegen.fx.reverb import render_reverb, reverb_state
from indiegen.mix.bus import pan_gains
from indiegen.plan import DroneEvent, Event, Plan, PluckEvent, PolyPeriodEvent
from indiegen.synth.drone import render_drone
from indiegen.synth.env import fade_gain, note_envelope, section_gain
from indiegen.synth.filter import apply_biquad, initial_state, lowpass_sos
from indiegen.synth.ks import render_pluck
from indiegen.synth.pad import render_pad
from indiegen.synth.poly_period import render_poly_period

BLOCK_SIZE: int = 8192


def schedule(plan: Plan) -> list[Event]:
    """Validate the events and put them in a stable, deterministic order."""
    events: list[Event] = []
    for event in plan.events:
        if event.start_frame + event.duration_frames > plan.duration_frames:
            raise PlanError("event runs past the end of the track", preset=plan.preset, seed=plan.seed)
        events.append(event)
    events.sort(key=lambda event: (event.start_frame, event.instrument, event.midi))
    return events


def _voice(event: Event, sample_rate: int) -> np.ndarray:
    """The mono voice of one event."""
    if isinstance(event, PluckEvent):
        return render_pluck(event, sample_rate)
    if isinstance(event, PolyPeriodEvent):
        return render_poly_period(event, sample_rate)
    if isinstance(event, DroneEvent):
        return render_drone(event, sample_rate)
    return render_pad(event, sample_rate)


def _filter_bus(plan: Plan, stereo: np.ndarray) -> np.ndarray:
    """The bus lowpass, applied in blocks with the state threaded across them."""
    if not plan.fx_sends:
        return stereo
    send = plan.fx_sends[0]
    sos = lowpass_sos(send.cutoff_hz, send.q_num, send.q_den, plan.sample_rate)
    state = initial_state(sos, plan.channels)
    wet = np.empty_like(stereo)
    for index, start in enumerate(range(0, stereo.shape[0], BLOCK_SIZE)):
        stop = min(stereo.shape[0], start + BLOCK_SIZE)
        filtered, state = apply_biquad(sos, stereo[start:stop], state)
        if not bool(np.all(np.isfinite(filtered))):
            raise RenderError(
                "non-finite sample after filtering",
                preset=plan.preset,
                seed=plan.seed,
                block_index=index,
            )
        wet[start:stop] = filtered
    level = float(np.power(10.0, send.send_millibels / 2000.0))
    blended: np.ndarray = stereo + (wet - stereo) * level
    return blended


def render_plan(plan: Plan) -> np.ndarray:
    """Render the plan into a stereo float64 buffer."""
    frames = plan.duration_frames
    main = np.zeros((frames, plan.channels), dtype=np.float64)
    ks_bus = np.zeros((frames, plan.channels), dtype=np.float64)
    has_ks = False

    for event in schedule(plan):
        voice = _voice(event, plan.sample_rate) * note_envelope(event)
        left, right = pan_gains(event.pan_permille)
        start = event.start_frame
        stop = start + voice.size
        if isinstance(event, PluckEvent):
            has_ks = True
            ks_bus[start:stop, 0] += voice * left
            ks_bus[start:stop, 1] += voice * right
        else:
            main[start:stop, 0] += voice * left
            main[start:stop, 1] += voice * right

    if has_ks and plan.delay_sends:
        send = plan.delay_sends[0]
        delay_line = delay_state(send)
        for start in range(0, frames, BLOCK_SIZE):
            stop = min(frames, start + BLOCK_SIZE)
            wet, delay_line = render_delay(ks_bus[start:stop], delay_line, send)
            main[start:stop] += wet

    filtered = _filter_bus(plan, main)

    if plan.reverb is not None:
        spec = plan.reverb
        reverb_line = reverb_state(spec)
        wet = np.empty_like(filtered)
        for start in range(0, frames, BLOCK_SIZE):
            stop = min(frames, start + BLOCK_SIZE)
            block, reverb_line = render_reverb(filtered[start:stop], reverb_line, spec, plan.sample_rate)
            wet[start:stop] = block
        filtered = filtered + wet

    gain = section_gain(plan, 0, frames) * fade_gain(plan, 0, frames)
    out: np.ndarray = filtered * gain[:, np.newaxis]
    return out
