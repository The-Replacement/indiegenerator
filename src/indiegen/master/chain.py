"""master(): the loudness pass, the limiter, the dither, the int16.

The master chain consumes the Plan's integer dither seed and constructs no
RNG of its own.

It is the one stage of the pipeline that looks at the audio it is given.
BRIEF 8 allows exactly one form of it - "a named second pass over a
finished stem" - and this is that: the loudness of the finished mix is
measured, the mix is gained onto the target, and the limiter holds the
true peak under the ceiling. The alternative, a declared gain, is measured
to fail: the loudness of a lane moves 1.3 to 5.1 dB from seed to seed, and
the gate allows one.

The limiter removes energy, so the loudness of the limited signal is not
the loudness of the mix. The chain measures what it is about to deliver
and corrects the gain, at most four times, until the delivered loudness is
within a fifth of a LU of the target.

The chain runs a block at a time. The limiter's gain may only fall, never
rise, so it carries one number from one block to the next; the dither is a
pure function of the seed and the sample index, so it carries nothing.
"""

from __future__ import annotations

import math

import numpy as np

from indiegen.errors import RenderError
from indiegen.master.dither import tpdf
from indiegen.master.limiter import limit, peak_envelope
from indiegen.master.loudness import integrated_lufs
from indiegen.plan import Plan
from indiegen.synth.env import fade_gain

INT16_SCALE: float = 32767.0
INT16_MIN: float = -32768.0
INT16_MAX: float = 32767.0

# How close to the target the delivered loudness has to be before the chain
# stops correcting, and how many times it is allowed to correct.
LOUDNESS_TOLERANCE_LU: float = 0.2
MAX_ITERATIONS: int = 4


def master(plan: Plan, stereo: np.ndarray, block: int) -> np.ndarray:
    """Measure the mix, gain it onto the target, limit it, dither it, quantise it."""
    if not bool(np.all(np.isfinite(stereo))):
        raise RenderError("non-finite sample in the mix", preset=plan.preset, seed=plan.seed, block_index=0)
    target = plan.target_lufs_millibels / 1000.0
    ceiling = math.pow(10.0, plan.ceiling_millibels / 2000.0)
    peaks = peak_envelope(stereo, block)

    # The first gain is the one that lands the mix on the target, and the
    # loop corrects it: the limiter removes energy, so the loudness of the
    # limited signal is not the loudness of the mix.
    measured = integrated_lufs(stereo, plan.sample_rate)
    gain = math.pow(10.0, (target - measured) / 20.0) if math.isfinite(measured) else 1.0
    limited = stereo
    for _ in range(MAX_ITERATIONS):
        limited, _, _ = limit(stereo, gain, peaks, ceiling, block)
        error = target - integrated_lufs(limited, plan.sample_rate)
        if abs(error) <= LOUDNESS_TOLERANCE_LU or not math.isfinite(error):
            break
        gain *= math.pow(10.0, error / 20.0)

    out = np.empty(stereo.shape, dtype="<i2")
    for start in range(0, stereo.shape[0], block):
        stop = min(stereo.shape[0], start + block)
        chunk = limited[start:stop]
        weight = (fade_gain(plan, start, stop - start) >= 1.0).astype(np.float64)[:, np.newaxis]
        noise = tpdf(plan.dither_seed, stop - start, start)[:, np.newaxis] * plan.dither_lsb * weight
        quantized = np.round(chunk * INT16_SCALE + noise)
        clipped: np.ndarray = np.clip(quantized, INT16_MIN, INT16_MAX)
        out[start:stop] = clipped.astype("<i2")
    return out
