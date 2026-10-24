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
from indiegen.gain import decibels_to_gain, millibels_to_gain
from indiegen.master.dither import tpdf
from indiegen.master.limiter import LOOKAHEAD_FRAMES, LimiterState, limit_block, peak_envelope_block
from indiegen.master.loudness import MEASURE_BLOCK, LoudnessMeter
from indiegen.plan import INT16_MAX, INT16_MIN, Plan
from indiegen.synth.env import fade_gain

INT16_SCALE: float = float(INT16_MAX)

# How close to the target the delivered loudness has to be before the chain
# stops correcting, and how many times it is allowed to correct.
LOUDNESS_TOLERANCE_LU: float = 0.2
MAX_ITERATIONS: int = 4


def _lufs_pass(samples: np.ndarray, rate: int) -> float:
    """The integrated loudness of a signal, fed one measure block at a time."""
    meter = LoudnessMeter(rate)
    frames = samples.shape[0]
    for start in range(0, frames, MEASURE_BLOCK):
        stop = min(frames, start + MEASURE_BLOCK)
        meter.feed(np.asarray(samples[start:stop], dtype=np.float64), measure_peak=False)
    return meter.integrated_lufs()


def _peak_window(samples: np.ndarray, start: int, stop: int) -> np.ndarray:
    """The peak envelope of ``[start, min(frames, stop + lookahead))``."""
    hi = min(samples.shape[0], stop + LOOKAHEAD_FRAMES)
    return peak_envelope_block(samples, start, hi)


def _limited_lufs_pass(samples: np.ndarray, rate: int, block: int, gain: float, ceiling: float) -> float:
    """The integrated loudness of the limited signal, without keeping it.

    The convergence loop needs the loudness of the limited mix for each
    gain it tries, and this measures it block by block: the limited block
    is fed to the meter and dropped, so the loop costs CPU and not memory.
    """
    meter = LoudnessMeter(rate)
    state: LimiterState | None = None
    frames = samples.shape[0]
    for start in range(0, frames, block):
        stop = min(frames, start + block)
        limited, state, _ = limit_block(samples, start, stop, gain, _peak_window(samples, start, stop), ceiling, state)
        meter.feed(limited, measure_peak=False)
    return meter.integrated_lufs()


def master(plan: Plan, stereo: np.ndarray, block: int) -> np.ndarray:
    """Measure the mix, gain it onto the target, limit it, dither it, quantise it.

    The chain streams: the loudness is measured a measure block at a time,
    the peak envelope is computed for the block in hand, and the limiter's
    deficit carries. Nothing but the int16 output and, when the opt-in
    saturation is on, a copy of the saturated mix is held whole. ``stereo``
    may be a memmap, which is how the longform render keeps the mix off the
    heap.
    """
    frames = stereo.shape[0]
    for start in range(0, frames, MEASURE_BLOCK):
        stop = min(frames, start + MEASURE_BLOCK)
        if not bool(np.all(np.isfinite(stereo[start:stop]))):
            raise RenderError(
                "non-finite sample in the mix", preset=plan.preset, seed=plan.seed, block_index=start // block
            )
    target = plan.target_lufs_millibels / 1000.0
    ceiling = millibels_to_gain(plan.ceiling_millibels)

    # Pre-limiter saturation (L21): tone shaping, not loudness. Sits before
    # the limiter so the ceiling stays the only loudness authority.
    drive = plan.saturation_drive_millibels
    sat_mix = plan.saturation_mix_permille / 1000.0
    processed: np.ndarray = stereo
    if sat_mix > 0 and drive > 0:
        gain_drive = millibels_to_gain(drive)
        saturated = np.tanh(np.asarray(stereo, dtype=np.float64) * gain_drive)
        processed = (1.0 - sat_mix) * np.asarray(stereo, dtype=np.float64) + sat_mix * saturated

    measured = _lufs_pass(processed, plan.sample_rate)
    gain = decibels_to_gain(target - measured) if math.isfinite(measured) else 1.0
    best: tuple[float, float] | None = None
    previous_error = 0.0
    for _ in range(MAX_ITERATIONS):
        measured = _limited_lufs_pass(processed, plan.sample_rate, block, gain, ceiling)
        if best is None or abs(target - measured) < abs(target - best[0]):
            best = (measured, gain)
        error = target - measured
        if abs(error) <= LOUDNESS_TOLERANCE_LU or not math.isfinite(error):
            break
        if previous_error and abs(error) >= abs(previous_error):
            # The limiter is holding the level down, and raising the gain
            # makes it hold harder: the loudness falls as the gain rises.
            # The ceiling is the limit and the target is a wish, so the
            # loudest the ceiling allows is what gets delivered.
            break
        previous_error = error
        gain *= decibels_to_gain(error)
    if best is not None:
        gain = best[1]

    out = np.empty((frames, stereo.shape[1]), dtype="<i2")
    state: LimiterState | None = None
    for start in range(0, frames, block):
        stop = min(frames, start + block)
        limited, state, _ = limit_block(
            processed, start, stop, gain, _peak_window(processed, start, stop), ceiling, state
        )
        weight = (fade_gain(plan, start, stop - start) >= 1.0).astype(np.float64)[:, np.newaxis]
        noise = tpdf(plan.dither_seed, stop - start, start)[:, np.newaxis] * plan.dither_lsb * weight
        quantized = np.round(limited * INT16_SCALE + noise)
        out[start:stop] = np.clip(quantized, float(INT16_MIN), INT16_SCALE).astype("<i2")
    return out
