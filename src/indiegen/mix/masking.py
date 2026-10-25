"""The masking stage: the bass-keyed duck on the band the bass and the pad share.

BRIEF 6 asks for the mix not to fight itself where the bass and the sustained
pad overlap, so the 200-500 Hz band is ducked under the bass envelope.

The duck is keyed on the bass HIT FRAMES and not on the bass audio - the
sidechain rule (``mix/sidechain.py``): the same envelope block-wise and
whole-track, for one exponential per second instead of one per sample.

The stage is a strict no-op when the Plan says ``None``, so a lane that
declares no duck cannot move.

The band split is a biquad cascade and carries its state from one block to the
next. A filter that restarts from zero history at every block boundary puts a
step into the signal every three seconds of audio; the state is what makes a
block-wise render agree with a whole-track one.
"""

from __future__ import annotations

import numpy as np

from indiegen.gain import millibels_to_gain, unity_block
from indiegen.mix.sidechain import hit_decay_envelope
from indiegen.plan import DuckSpec
from indiegen.synth.filter import apply_biquad, bandpass_sos

DUCK_LOW_HZ: int = 200
"""The duck's lower corner: below it the bass owns the space outright."""

DUCK_HIGH_HZ: int = 500
"""The duck's upper corner: above it the pad's body is no longer in the way."""


def duck_envelope(start: int, count: int, hits: list[int], spec: DuckSpec) -> np.ndarray:
    """The duck's gain over the frames ``[start, start + count)``.

    The most recent hit always gives the lowest gain, because the exponential
    has decayed the least since it, so the envelope is restarted at every hit
    and recovered over the release. Every value is a function of the ABSOLUTE
    frame index and the hit list, which is what makes a block-wise render and
    a whole-track one agree exactly - no state is carried and none is needed.
    """
    gain = unity_block(count)
    if not hits:
        return gain
    samples = np.arange(start, start + count, dtype=np.int64)
    ordered = np.asarray(hits, dtype=np.int64)
    # The last hit at or before each sample; -1 where the bass has not entered.
    position = np.searchsorted(ordered, samples, side="right") - 1
    active = position >= 0
    if not bool(active.any()):
        return gain
    level = millibels_to_gain(spec.depth_millibels)
    age = (samples[active] - ordered[position[active]]).astype(np.float64)
    gain[active] = hit_decay_envelope(age, level, spec.release_frames)
    return gain


def duck_band(signal: np.ndarray, state: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    """The 200-500 Hz band of ``signal``, carrying the filter state.

    Two Butterworth biquads in series (``bandpass_sos``), not the difference of
    two one-pole low passes: a one-pole difference is shallow enough that it
    passes a fifth of a tone in the middle of its own band and still leaks
    two octaves above it, so it would smear the carve across the mix. The
    state is the biquad's, and carrying it is what makes the carve the same
    block-wise and whole-track.
    """
    sos = bandpass_sos(DUCK_LOW_HZ, DUCK_HIGH_HZ, sample_rate)
    band, carry = apply_biquad(sos, signal, state)
    return band, carry


def apply_duck(signal: np.ndarray, gain: np.ndarray, band: np.ndarray, spec: DuckSpec | None) -> np.ndarray:
    """Attenuate ``band`` by the duck's gain, and return the signal.

    Identity when ``spec`` is None, so the default render cannot move.
    """
    if spec is None:
        return signal
    return np.asarray(signal - (1.0 - gain)[:, np.newaxis] * band, dtype=np.float64)
