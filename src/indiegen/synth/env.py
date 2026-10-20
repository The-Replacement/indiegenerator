"""Envelopes. Every one of them is a pure function of the Plan."""

from __future__ import annotations

import numpy as np

from indiegen.plan import NoteEvent, Plan


def note_envelope(event: NoteEvent) -> np.ndarray:
    """The note's attack and release, linear, exactly zero at the very edges."""
    count = event.duration_frames
    gain = np.ones(count, dtype=np.float64)
    if event.attack_frames > 0:
        ramp = np.arange(count, dtype=np.float64) / event.attack_frames
        gain *= np.minimum(1.0, ramp)
    if event.release_frames > 0:
        ramp = np.arange(count - 1, -1, -1, dtype=np.float64) / event.release_frames
        gain *= np.minimum(1.0, ramp)
    return gain


def section_gain(plan: Plan, start: int, count: int) -> np.ndarray:
    """The arrangement's level over an absolute window, with crossfades."""
    levels = np.empty(count, dtype=np.float64)
    levels.fill(float(plan.sections[0].level_millibels) if plan.sections else 0.0)
    for section in plan.sections:
        low = max(start, section.start_frame)
        high = min(start + count, section.end_frame)
        if high > low:
            levels[low - start : high - start] = float(section.level_millibels)
    half = plan.section_crossfade_frames // 2
    for section in plan.sections[1:]:
        low = max(start, section.start_frame - half)
        high = min(start + count, section.start_frame + plan.section_crossfade_frames - half)
        if high > low:
            ramp = np.linspace(levels[low - start], levels[min(high - start, count - 1)], high - low)
            levels[low - start : high - start] = ramp
    return np.power(10.0, levels / 2000.0)


def fade_gain(plan: Plan, start: int, count: int) -> np.ndarray:
    """The global fade in and out. Exactly zero at the first and last frame."""
    index = np.arange(start, start + count, dtype=np.float64)
    gain = np.ones(count, dtype=np.float64)
    if plan.fade_in_frames > 0:
        mask = index < plan.fade_in_frames
        gain[mask] = index[mask] / plan.fade_in_frames
    if plan.fade_out_frames > 0:
        mask = index >= plan.duration_frames - plan.fade_out_frames
        gain[mask] = (plan.duration_frames - 1 - index[mask]) / plan.fade_out_frames
    return np.clip(gain, 0.0, 1.0)


def fade_weight(plan: Plan) -> np.ndarray:
    """One where the track is not inside a fade, zero where it is."""
    gain = fade_gain(plan, 0, plan.duration_frames)
    return (gain >= 1.0).astype(np.float64)
