"""Envelopes. Every one of them is a pure function of the Plan."""

from __future__ import annotations

import numpy as np

from indiegen.gain import millibels_to_gain_array, unity_block
from indiegen.plan import EventBase, Plan
from indiegen.synth.filter import one_pole_highpass, one_pole_highpass_state

DC_BLOCKER_HZ: float = 20.0


def dc_blocker_state() -> np.ndarray:
    """Zero state for the DC blocker."""

    return np.zeros(1, dtype=np.float64)


def dc_blocked_block(signal: np.ndarray, sample_rate: int, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """DC-block a finished voice block, carrying the blocker state.

    This is the shared tail of the blockwise voice skeleton: allocate a
    silent block (``synth.osc.zero_block``), accumulate the voice's own
    partials into it - that loop is each instrument's alone and is not
    shared - then finish here. The pluck, the poly-period voice and the
    drone all end this way; the pad is the one exception, because it is
    never DC-blocked (see ``dc_block``).
    """
    return dc_block_state(signal, sample_rate, state)


def dc_block(signal: np.ndarray, sample_rate: int) -> np.ndarray:
    """Remove the DC offset with a one-pole high pass.

    A voice with an envelope correlates with its carrier, and a plucked string
    whose tail is cut leaves a small offset behind. Both are tiny in level
    and enormous in a reverb, whose combs have a DC gain of 1/(1-g) each.
    The block lives with the instruments rather than in the master chain, so
    the sustained pad - and with it the committed S0 artifact - is untouched.

    The transfer function is (1 - z^-1) / (1 - r z^-1): zero at DC, and a
    high pass above the corner.
    """
    return one_pole_highpass(signal, DC_BLOCKER_HZ, sample_rate)


def dc_block_state(
    signal: np.ndarray,
    sample_rate: int,
    state: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """The same block, with its state carried across the blocks.

    A block-wise filter that starts from zero every time leaves a residual
    behind on every block, and the reverb's comb bank multiplies that
    residual by fifty.
    """
    return one_pole_highpass_state(signal, DC_BLOCKER_HZ, sample_rate, state)


def note_envelope_block(event: EventBase, start: int, stop: int) -> np.ndarray:
    """The note's attack and release over the frames ``[start, stop)``.

    The edges are zero even when the attack and the release are empty: a
    note that starts or stops at full level is a click, and a plucked string
    has neither an attack nor a release of its own. The zero edges belong to
    the note, not to the block, so they are placed by the note's own frame
    numbers and not by the block's.
    """
    count = stop - start
    gain = unity_block(count)
    if event.attack_frames > 0:
        if event.envelope_curve == 1:
            ramp = 1.0 - np.exp(-4.0 * np.arange(start, stop, dtype=np.float64) / event.attack_frames)
            gain *= np.minimum(1.0, ramp)
        else:
            ramp = np.arange(start, stop, dtype=np.float64) / event.attack_frames
            gain *= np.minimum(1.0, ramp)
    if event.release_frames > 0:
        ramp = (
            np.arange(
                event.duration_frames - 1 - start,
                event.duration_frames - 1 - stop,
                -1,
                dtype=np.float64,
            )
            / event.release_frames
        )
        gain *= np.minimum(1.0, ramp)
    if count > 0:
        if start == 0:
            gain[0] = 0.0
        if stop == event.duration_frames:
            gain[-1] = 0.0
    return gain


def note_envelope(event: EventBase) -> np.ndarray:
    """The note's attack and release, linear, exactly zero at the very edges.

    The whole note in one block.
    """
    return note_envelope_block(event, 0, event.duration_frames)


def _base_level(plan: Plan, frame: int) -> float:
    """The level of a frame after the sections are laid down."""
    level = float(plan.sections[0].level_millibels) if plan.sections else 0.0
    for section in plan.sections:
        if section.start_frame <= frame < section.end_frame:
            level = float(section.level_millibels)
    return level


def _level_at(plan: Plan, frame: int, ramps: list[tuple[int, int, np.ndarray]]) -> float:
    """The level of a frame with the given crossfades already applied."""
    for low, high, ramp in reversed(ramps):
        if low <= frame < high:
            return float(ramp[frame - low])
    return _base_level(plan, frame)


def _crossfade_ramps(plan: Plan) -> list[tuple[int, int, np.ndarray]]:
    """The crossfades between the sections, as ramps over the whole track.

    The ramp's end points are the levels at the two ends of the crossfade,
    read after the sections are laid down and after the earlier crossfades
    have been applied - which is what the whole-track version does with its
    levels array, and the reason the ramps are resolved in order here.
    """
    ramps: list[tuple[int, int, np.ndarray]] = []
    if not plan.sections:
        return ramps
    half = plan.section_crossfade_frames // 2
    for section in plan.sections[1:]:
        low = max(0, section.start_frame - half)
        high = min(plan.duration_frames, section.start_frame + plan.section_crossfade_frames - half)
        if high <= low:
            continue
        start_value = _level_at(plan, low, ramps)
        end_value = _level_at(plan, min(high, plan.duration_frames - 1), ramps)
        ramps.append((low, high, np.linspace(start_value, end_value, high - low)))
    return ramps


def section_gain(plan: Plan, start: int, count: int) -> np.ndarray:
    """The arrangement's level over an absolute window, with crossfades.

    The crossfade ramps are cut over the whole track and sliced, because the
    ramp's end point is a level of the arrangement and not of the window.
    """
    stop = start + count
    levels = np.empty(count, dtype=np.float64)
    levels.fill(float(plan.sections[0].level_millibels) if plan.sections else 0.0)
    for section in plan.sections:
        low = max(start, section.start_frame)
        high = min(stop, section.end_frame)
        if high > low:
            levels[low - start : high - start] = float(section.level_millibels)
    for low, high, ramp in _crossfade_ramps(plan):
        block_low = max(start, low)
        block_high = min(stop, high)
        if block_high > block_low:
            levels[block_low - start : block_high - start] = ramp[block_low - low : block_high - low]
    return millibels_to_gain_array(levels)


def fade_gain(plan: Plan, start: int, count: int) -> np.ndarray:
    """The global fade in and out. Exactly zero at the first and last frame.

    The value of a frame depends only on the frame's own number, so a window
    of the fade is the same fade.
    """
    index = np.arange(start, start + count, dtype=np.float64)
    gain = unity_block(count)
    if plan.fade_in_frames > 0:
        mask = index < plan.fade_in_frames
        gain[mask] = index[mask] / plan.fade_in_frames
    if plan.fade_out_frames > 0:
        mask = index >= plan.duration_frames - plan.fade_out_frames
        gain[mask] = (plan.duration_frames - 1 - index[mask]) / plan.fade_out_frames
    return np.asarray(np.clip(gain, 0.0, 1.0), dtype=np.float64)
