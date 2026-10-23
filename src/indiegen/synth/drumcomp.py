"""Drum-bus compressor with carry state.

A single compressor stage applied to the drum bus between the drum sum and
the bus mix. Envelope follower with attack/release carry state; parallel
comp via mix. Determinism: restart-from-stated-block renders bit-identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain
from indiegen.plan import DrumBusComp


@dataclass(frozen=True)
class DrumCompState:
    """Carry state: the envelope follower level."""

    envelope: float


def drum_comp_state() -> DrumCompState:
    return DrumCompState(envelope=0.0)


def render_drum_comp_block(
    signal: np.ndarray,
    state: DrumCompState,
    comp: DrumBusComp,
    sample_rate: int,
) -> tuple[np.ndarray, DrumCompState]:
    """Apply the compressor to a stereo block, carrying the envelope."""
    if comp.mix_permille <= 0:
        # Bypass: output = input, envelope still tracks for determinism? Track anyway.
        # Track envelope but don't apply gain.
        env = state.envelope
        out = signal.copy()
        # update envelope lightly to keep state meaningful
        for i in range(signal.shape[0]):
            x = float(np.max(np.abs(signal[i])))
            if x > env:
                env = env + (x - env) / max(1, comp.attack_frames)
            else:
                env = env + (x - env) / max(1, comp.release_frames)
        return out, DrumCompState(envelope=env)

    threshold = millibels_to_gain(comp.threshold_millibels)
    makeup = millibels_to_gain(comp.makeup_millibels)
    ratio = comp.ratio_permille / 1000.0
    mix = comp.mix_permille / 1000.0
    attack = max(1, comp.attack_frames)
    release = max(1, comp.release_frames)

    env = state.envelope
    out = np.zeros_like(signal)
    n = signal.shape[0]
    for i in range(n):
        x = float(np.max(np.abs(signal[i])))
        env = env + (x - env) / attack if x > env else env + (x - env) / release
        # gain reduction
        if env > threshold and threshold > 0:
            gr = (threshold / env) ** ((ratio - 1.0) / ratio) if ratio > 1 else 1.0
        elif env > threshold:
            # threshold <=0 (in dB, threshold linear could be <1); handle threshold in linear
            gr = (threshold / env) ** ((ratio - 1.0) / ratio) if env > 0 else 1.0
        else:
            gr = 1.0
        wet = signal[i] * gr * makeup
        out[i] = (1.0 - mix) * signal[i] + mix * wet

    return out, DrumCompState(envelope=env)
