"""schedule() and the block renderer.

This module is the render path: it imports nothing from ``compose/`` and rolls
no dice. A block is rendered once, and the filter state crosses the block
boundary as a value.
"""

from __future__ import annotations

import numpy as np

from indiegen.errors import PlanError, RenderError
from indiegen.mix.bus import pan_gains
from indiegen.plan import NoteEvent, Plan
from indiegen.synth.env import fade_gain, note_envelope, section_gain
from indiegen.synth.filter import apply_biquad, initial_state, lowpass_sos
from indiegen.synth.pad import render_pad

BLOCK_SIZE: int = 8192


def schedule(plan: Plan) -> list[NoteEvent]:
    """Validate the events and put them in a stable, deterministic order."""
    events: list[NoteEvent] = []
    for event in plan.events:
        if event.start_frame + event.duration_frames > plan.duration_frames:
            raise PlanError("event runs past the end of the track", preset=plan.preset, seed=plan.seed)
        events.append(event)
    events.sort(key=lambda event: (event.start_frame, event.instrument, event.midi))
    return events


def _filter_bus(plan: Plan, stereo: np.ndarray) -> np.ndarray:
    """The bus filter, applied in blocks with the state threaded across them."""
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
    stereo = np.zeros((frames, plan.channels), dtype=np.float64)
    for event in schedule(plan):
        voice = render_pad(event, plan.sample_rate) * note_envelope(event)
        left, right = pan_gains(event.pan_permille)
        start = event.start_frame
        stop = start + voice.size
        stereo[start:stop, 0] += voice * left
        stereo[start:stop, 1] += voice * right
    filtered = _filter_bus(plan, stereo)
    gain = section_gain(plan, 0, frames) * fade_gain(plan, 0, frames)
    out: np.ndarray = filtered * gain[:, np.newaxis]
    return out
