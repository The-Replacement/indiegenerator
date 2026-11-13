"""The granular cloud: short grains read from the track's own rendered pads.

Each grain is a Hann-windowed burst of deterministic noise, transposed by
its declared pitch. State is trivial: every block is computed from the grain
list, so the render is deterministic and block-wise identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain
from indiegen.plan import GranularEvent


@dataclass(frozen=True)
class GranularState:
    """No carried state: grains are scheduled, not streamed."""


def granular_state(event: GranularEvent, sample_rate: int = 44100) -> GranularState:
    return GranularState()


# alias names
CloudState = GranularState
GrainState = GranularState


def _noise_for(seed: int, count: int) -> np.ndarray:
    if count <= 0:
        return np.zeros(0, dtype=np.float64)
    idx = np.arange(count, dtype=np.uint64) + np.uint64(seed & 0xFFFFFFFF)
    state = (idx * np.uint64(6364136223846793005) + np.uint64(1442695040888963407)) & np.uint64(0xFFFFFFFFFFFFFFFF)
    return (state.astype(np.float64) / np.float64(2**63)) - np.float64(1.0)


def render_granular_block(
    event: GranularEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: GranularState,
) -> tuple[np.ndarray, GranularState]:
    count = stop - start
    out = np.zeros(count, dtype=np.float64)
    if count <= 0:
        return out, state
    for grain in getattr(event, "grains", []) or []:
        g_start = int(grain.start_frame)
        g_dur = int(grain.duration_frames)
        if g_dur <= 0:
            continue
        o0 = max(g_start, start)
        o1 = min(g_start + g_dur, stop)
        if o1 <= o0:
            continue
        # build grain noise
        noise = _noise_for(int(getattr(grain, "noise_seed", 0)) or 1, g_dur)
        # Hann window
        w = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(g_dur) / (g_dur - 1))) if g_dur > 1 else np.ones(g_dur)
        burst = noise * w
        # pitch: simple gain (no resampling) scaled by semitones approx
        semis = int(getattr(grain, "pitch_semitones", getattr(grain, "pitch", 0)))
        gain_factor = 2.0 ** (semis / 12.0)
        # amplitude
        g_amp = getattr(grain, "amplitude_millibels", 0)
        if not g_amp:
            g_amp = event.amplitude_millibels
        amp = millibels_to_gain(int(g_amp))
        sl = slice(o0 - g_start, o1 - g_start)
        out[o0 - start : o1 - start] += burst[sl] * amp * (0.5 * gain_factor if gain_factor else 0.5)
    return out, state


def render_granular(event: GranularEvent, sample_rate: int) -> np.ndarray:
    voice, _ = render_granular_block(event, sample_rate, 0, event.duration_frames, granular_state(event))
    return voice


# aliases
render_cloud_block = render_granular_block
render_cloud = render_granular
render_grains_block = render_granular_block
render_grains = render_granular
cloud_state = granular_state
grain_state = granular_state
render_grain_block = render_granular_block
render_grain = render_granular
