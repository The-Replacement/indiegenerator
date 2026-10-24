"""The true-peak limiter.

BRIEF 11's gate 1 is in dBTP, so the ceiling has to hold on the inter-sample
peaks and not only on the samples. The limiter therefore measures the peak
of every base sample at four times the sample rate, and the gain it applies
is computed from that.

The three parts of it:

* **The measurement.** The signal is oversampled four times with
  ``resample_poly`` and the largest of the four inter-sample peaks inside
  every base sample is kept. The two channels are linked: the loudest one
  decides, so the stereo image survives the gain.
* **The lookahead.** The gain at a sample is the smallest gain that any of
  the next ``LOOKAHEAD_FRAMES`` samples will need, so the gain is already
  down when the peak arrives and the attack is a ramp and not a corner.
  The minimum is taken over a chunk decomposition: the suffix minimum of the
  chunk the sample is in and the prefix minimum of the next one.
* **The release.** The gain may only fall fast and rise slowly, so the
  deficit (one minus the gain) is held and released exponentially. The
  recursion ``D[i] = max(w[i], r * D[i-1])`` has a closed form: a running
  maximum of the scaled deficits, which is what the code does.

The state is a value: the deficit that is carried from one block to the
next, and nothing else. The block size does not change the result, as long
as it is a multiple of the lookahead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import resample_poly

from indiegen.gain import decibels_to_gain

OVERSAMPLE: int = 4
MARGIN_FRAMES: int = 64
LOOKAHEAD_FRAMES: int = 256
# Forty milliseconds of release at 44.1 kHz.
RELEASE_FRAMES: int = 1764

# The limiter's model of the output is the gain times the input's peak, and
# the real output is the reconstruction of the gain-modified signal, which
# is a little louder than the model: the interpolation mixes samples that
# carry different gains. Measured on white noise at full scale, the model
# is 0.19 dB under the truth, so the limiter works a third of a dB below
# the ceiling it is given.
MODEL_MARGIN_DB: float = 0.3

# resample_poly's interpolation filter is symmetric and centred: the output
# index j is the signal at the time j / OVERSAMPLE, so the four
# inter-sample peaks of a base sample are the output indices 4i..4i+3.
FILTER_DELAY: int = 0

TINY: float = 1e-30


@dataclass(frozen=True)
class LimiterState:
    """The limiter's state, as a value.

    The deficit is one minus the gain, and it is the only thing that has to
    survive the block boundary.
    """

    deficit: float = 0.0


def peak_envelope(mix: np.ndarray, block: int) -> np.ndarray:
    """The inter-sample peak of every sample of the mix.

    One value per base sample: the largest of the four inter-sample peaks
    inside it, over both channels.

    The block is measured with a margin of samples on both sides, because
    the interpolation filter reaches over a handful of samples: without the
    margin the first samples of the block would be measured against
    silence. The margin is silence where the track has none, and the
    offset accounts for it, so the peak of a base sample is attributed to
    that base sample and not to its neighbour.
    """
    frames = mix.shape[0]
    peaks = np.zeros(frames, dtype=np.float64)
    for start in range(0, frames, block):
        stop = min(frames, start + block)
        context_start = max(0, start - MARGIN_FRAMES)
        context_stop = min(frames, stop + MARGIN_FRAMES)
        front = start - context_start
        back = (stop + MARGIN_FRAMES) - context_stop
        context = mix[context_start:context_stop]
        if front or back:
            padding = np.zeros((front + back, mix.shape[1]), dtype=np.float64)
            context = np.concatenate([padding[:front], context, padding[front:]])
        upsampled = resample_poly(context, OVERSAMPLE, 1, axis=0)
        lead = start + front - context_start
        offset = OVERSAMPLE * lead + FILTER_DELAY
        count = stop - start
        for channel in range(mix.shape[1]):
            column = upsampled[:, channel]
            window = np.abs(column[offset : offset + count * OVERSAMPLE])
            peaks[start:stop] = np.maximum(peaks[start:stop], window.reshape(count, OVERSAMPLE).max(axis=1))
    return peaks


def peak_envelope_block(mix: np.ndarray, start: int, stop: int) -> np.ndarray:
    """The inter-sample peak of base samples ``[start, stop)``.

    This is the body of :func:`peak_envelope` for one block, and it is
    exposed because the streaming master needs the envelope of the block it
    is limiting and nothing else. The value of a base sample depends only
    on the ``MARGIN_FRAMES`` of context on either side of it, so this
    reproduces the whole-track call's value exactly, block partition or no.
    """
    frames = mix.shape[0]
    context_start = max(0, start - MARGIN_FRAMES)
    context_stop = min(frames, stop + MARGIN_FRAMES)
    front = start - context_start
    back = (stop + MARGIN_FRAMES) - context_stop
    context = np.array(mix[context_start:context_stop], dtype=np.float64)
    if front or back:
        padding = np.zeros((front + back, mix.shape[1]), dtype=np.float64)
        context = np.concatenate([padding[:front], context, padding[front:]])
    upsampled = resample_poly(context, OVERSAMPLE, 1, axis=0)
    lead = start + front - context_start
    offset = OVERSAMPLE * lead + FILTER_DELAY
    count = stop - start
    peaks = np.zeros(count, dtype=np.float64)
    for channel in range(mix.shape[1]):
        column = upsampled[:, channel]
        window = np.abs(column[offset : offset + count * OVERSAMPLE])
        peaks = np.maximum(peaks, window.reshape(count, OVERSAMPLE).max(axis=1))
    return peaks


def lookahead_min(values: np.ndarray, chunk: int, count: int) -> np.ndarray:
    """The smallest of the next ``chunk`` values, for every value.

    ``values`` holds the block's values and the lookahead beyond them; the
    result holds ``count`` values, one per sample of the block.
    """
    blocks = -(-values.size // chunk)
    padded = np.concatenate([values, np.full(blocks * chunk - values.size, np.inf)])
    grid = padded.reshape(blocks, chunk)
    suffix = np.minimum.accumulate(grid[:, ::-1], axis=1)[:, ::-1]
    prefix = np.minimum.accumulate(grid, axis=1)
    shifted = np.empty((blocks - 1, chunk), dtype=np.float64)
    shifted[:, 0] = np.inf
    shifted[:, 1:] = prefix[1:, :-1]
    return np.minimum(suffix[:-1], shifted).reshape(-1)[:count]


def decayed_max(values: np.ndarray, decay: float, carry: float) -> tuple[np.ndarray, float]:
    """The recursion ``D[i] = max(values[i], decay * D[i-1])``, in closed form.

    The carry is the value of ``D`` before the first sample of the block.
    """
    count = values.size
    index = np.arange(count, dtype=np.float64)
    running = np.maximum.accumulate(values * np.power(decay, -index))
    out = np.power(decay, index) * np.maximum(running, decay * carry)
    return out, float(out[-1])


def limit_block(
    mix: np.ndarray,
    start: int,
    stop: int,
    gain: float,
    peaks: np.ndarray,
    ceiling: float,
    state: LimiterState | None,
) -> tuple[np.ndarray, LimiterState, float]:
    """Limit base samples ``[start, stop)`` given their peak envelope.

    ``peaks`` holds the envelope of ``[start, min(frames, stop +
    LOOKAHEAD_FRAMES))``, so the lookahead is in hand and the state carries
    the deficit. The whole-track :func:`limit` is this function in a loop,
    and the streaming master is this function over a memmap.
    """
    count = stop - start
    decay = math.exp(-1.0 / RELEASE_FRAMES)
    limit_ceiling = ceiling * decibels_to_gain(-MODEL_MARGIN_DB)
    required = np.minimum(1.0, (limit_ceiling / np.maximum(peaks, TINY)) / gain)
    if required.size < count + LOOKAHEAD_FRAMES:
        required = np.concatenate([required, np.full(count + LOOKAHEAD_FRAMES - required.size, 1.0)])
    look = lookahead_min(required, LOOKAHEAD_FRAMES, count)
    carry = state.deficit if state is not None else 0.0
    deficit, carry = decayed_max(1.0 - look, decay, carry)
    curve = 1.0 - deficit
    out = mix[start:stop] * (gain * curve)[:, np.newaxis]
    return out, LimiterState(deficit=carry), float(curve.min())


def limit(
    mix: np.ndarray,
    gain: float,
    peaks: np.ndarray,
    ceiling: float,
    block: int,
    state: LimiterState | None = None,
) -> tuple[np.ndarray, float, LimiterState]:
    """Limit the mix to the ceiling and return it, the deepest cut and the state.

    ``peaks`` is the inter-sample peak envelope of the *unscaled* mix, so
    the same envelope serves every gain: the signal that reaches the
    limiter is the mix times ``gain``, and its peak is the envelope times
    ``gain``.
    """
    frames = mix.shape[0]
    out = np.empty_like(mix)
    carry: LimiterState | None = state
    deepest = 1.0
    for start in range(0, frames, block):
        stop = min(frames, start + block)
        window = peaks[start : min(frames, stop + LOOKAHEAD_FRAMES)]
        limited, carry, curve_min = limit_block(mix, start, stop, gain, window, ceiling, carry)
        out[start:stop] = limited
        deepest = min(deepest, curve_min)
    return out, deepest, (carry if carry is not None else LimiterState())
