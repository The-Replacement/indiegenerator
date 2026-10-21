"""master(): gain, safety limiter, seeded dither, int16.

The master chain consumes the Plan's integer dither seed and constructs no
RNG of its own. The limiter is a safety net, not a feature: the mix is staged
to the declared target peak, so the limiter should never engage.

The chain runs a block at a time. The limiter's gain may only fall, never
rise, so it carries one number from one block to the next; the dither is a
pure function of the seed and the sample index, so it carries nothing.
"""

from __future__ import annotations

import math

import numpy as np

from indiegen.errors import RenderError
from indiegen.master.dither import tpdf
from indiegen.plan import Plan
from indiegen.synth.env import fade_gain

INT16_SCALE: float = 32767.0
INT16_MIN: float = -32768.0
INT16_MAX: float = 32767.0


def _peak(signal: np.ndarray, block: int) -> float:
    """The loudest sample of the signal, without a full-length copy of it."""
    peak = 0.0
    for start in range(0, signal.shape[0], block):
        chunk = signal[start : start + block]
        if chunk.size:
            value = float(np.max(np.abs(chunk)))
            if value > peak:
                peak = value
    return peak


def master(plan: Plan, stereo: np.ndarray, block: int) -> np.ndarray:
    """Stage the mix, limit it, dither it and quantise it to int16."""
    peak = _peak(stereo, block)
    if not math.isfinite(peak):
        raise RenderError("non-finite sample in the mix", preset=plan.preset, seed=plan.seed, block_index=0)
    if peak > 0.0:
        gain_db = plan.master_gain_millibels / 100.0 - 20.0 * math.log10(peak)
        stage = math.pow(10.0, gain_db / 20.0)
    else:
        stage = 1.0
    ceiling = math.pow(10.0, plan.ceiling_millibels / 2000.0)
    out = np.empty(stereo.shape, dtype="<i2")
    gain = 1.0
    for start in range(0, stereo.shape[0], block):
        stop = min(stereo.shape[0], start + block)
        chunk = stereo[start:stop] * stage
        raw_peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
        if raw_peak > 0.0:
            gain = min(gain, ceiling / raw_peak)
        chunk *= gain
        weight = (fade_gain(plan, start, stop - start) >= 1.0).astype(np.float64)[:, np.newaxis]
        noise = tpdf(plan.dither_seed, stop - start, start)[:, np.newaxis] * plan.dither_lsb * weight
        quantized = np.round(chunk * INT16_SCALE + noise)
        clipped: np.ndarray = np.clip(quantized, INT16_MIN, INT16_MAX)
        out[start:stop] = clipped.astype("<i2")
    return out
