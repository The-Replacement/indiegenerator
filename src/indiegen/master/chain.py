"""master(): gain, safety limiter, seeded dither, int16.

The master chain consumes the Plan's integer dither seed and constructs no
RNG of its own. The limiter is a safety net, not a feature: the mix is staged
to the declared target peak, so the limiter should never engage.
"""

from __future__ import annotations

import math

import numpy as np

from indiegen.errors import RenderError
from indiegen.master.dither import tpdf
from indiegen.plan import Plan
from indiegen.synth.env import fade_weight

INT16_SCALE: float = 32767.0
INT16_MIN: float = -32768.0
INT16_MAX: float = 32767.0


def _limit(signal: np.ndarray, ceiling_millibels: int, block: int) -> np.ndarray:
    """A block-wise safety limiter. The output never exceeds the ceiling.

    The gain is monotonically non-increasing: it may only be reduced, never
    raised. Folding the accumulated gain into the measured peak and then
    dividing by it would let a louder block raise the gain again, and the
    limiter would overshoot by exactly the attenuation it had already applied.
    """
    ceiling = math.pow(10.0, ceiling_millibels / 2000.0)
    limited = signal.copy()
    gain = 1.0
    for start in range(0, limited.shape[0], block):
        chunk = limited[start : start + block]
        raw_peak = float(np.max(np.abs(chunk)))
        if raw_peak > 0.0:
            gain = min(gain, ceiling / raw_peak)
        chunk *= gain
    return limited


def master(plan: Plan, stereo: np.ndarray, block: int) -> np.ndarray:
    """Stage the mix, limit it, dither it and quantise it to int16."""
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if not math.isfinite(peak):
        raise RenderError("non-finite sample in the mix", preset=plan.preset, seed=plan.seed, block_index=0)
    if peak > 0.0:
        gain_db = plan.master_gain_millibels / 100.0 - 20.0 * math.log10(peak)
        staged = stereo * math.pow(10.0, gain_db / 20.0)
    else:
        staged = stereo.copy()
    limited = _limit(staged, plan.ceiling_millibels, block)
    weight = fade_weight(plan)[:, np.newaxis]
    noise = tpdf(plan.dither_seed, limited.shape[0])[:, np.newaxis] * plan.dither_lsb * weight
    quantized = np.round(limited * INT16_SCALE + noise)
    clipped: np.ndarray = np.clip(quantized, INT16_MIN, INT16_MAX)
    return clipped.astype("<i2")
