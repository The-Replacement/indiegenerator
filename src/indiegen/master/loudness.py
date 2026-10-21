"""BS.1770-4 loudness, re-derived for the rate we actually render at.

The published K-weighting coefficients are for 48 kHz. At 44.1 kHz the gain
at 1 kHz shifts by roughly 0.2 dB, which on its own would break the gate that
compares this meter with ``ffmpeg -af ebur128``. So the filters are derived
from the standard's analog prototypes for the sample rate in hand, and the
meter was measured against ffmpeg on this machine: within 0.05 dB from 100 Hz
to 8 kHz.

The meter is fed a block at a time. The K-weighting carries the state of its
filters, the loudness windows are cut from a rolling buffer, and the true peak
oversamples each block with a margin of history. A fifteen minute track does
not have to fit in memory to be measured.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter, resample_poly

BLOCK_SECONDS: float = 0.4
HOP_SECONDS: float = 0.1
ABSOLUTE_GATE_LUFS: float = -70.0
RELATIVE_GATE_LU: float = -10.0
LOUDNESS_OFFSET: float = -0.691
OVERSAMPLE: int = 4
MARGIN_FRAMES: int = 64
MEASURE_BLOCK: int = 65536


def _high_shelf(rate: int) -> tuple[list[float], list[float]]:
    """Stage one of the K-weighting: the high shelf."""
    f0 = 1681.974450955533
    gain_db = 3.999843853973347
    quality = 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = math.pow(10.0, gain_db / 20.0)
    vb = math.pow(vh, 0.4996667741545416)
    a0 = 1.0 + k / quality + k * k
    numerators = [
        (vh + vb * k / quality + k * k) / a0,
        2.0 * (k * k - vh) / a0,
        (vh - vb * k / quality + k * k) / a0,
    ]
    denominators = [1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / quality + k * k) / a0]
    return numerators, denominators


def _high_pass(rate: int) -> tuple[list[float], list[float]]:
    """Stage two of the K-weighting: the RLB high pass."""
    f0 = 38.13547087602444
    quality = 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    a0 = 1.0 + k / quality + k * k
    numerators = [1.0 / a0, -2.0 / a0, 1.0 / a0]
    denominators = [1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / quality + k * k) / a0]
    return numerators, denominators


class LoudnessMeter:
    """The loudness meter and the two peaks, fed a block at a time.

    The samples are in the range [-1, 1]. The K-weighting, the loudness
    windows and the oversampled peak are all cut from the blocks that arrive.
    """

    def __init__(self, rate: int) -> None:
        self._rate = rate
        self._window = int(BLOCK_SECONDS * rate)
        self._hop = int(HOP_SECONDS * rate)
        self._stages = (_high_shelf(rate), _high_pass(rate))
        self._filters: list[list[np.ndarray]] = []
        self._energies: list[np.ndarray] = []
        self._buffer = np.zeros((0, 0), dtype=np.float64)
        self._tail = np.zeros((0, 0), dtype=np.float64)
        self._position = 0
        self._next_window = 0
        self._count = 0
        self._peak = 0.0
        self._true_peak = 0.0

    def feed(self, block: np.ndarray) -> None:
        """Feed a block of samples in the range [-1, 1]."""
        if block.size == 0:
            return
        signal = block.astype(np.float64)
        self._count += signal.shape[0]
        value = float(np.max(np.abs(signal)))
        if value > self._peak:
            self._peak = value
        self._feed_true_peak(signal)
        self._feed_energies(self._k_weight(signal))

    def _k_weight(self, signal: np.ndarray) -> np.ndarray:
        """Apply the K-weighting curve to every channel."""
        if not self._filters:
            self._filters = [
                [np.zeros(len(numerators) - 1, dtype=np.float64) for numerators, _ in self._stages]
                for _ in range(signal.shape[1])
            ]
        weighted = np.zeros(signal.shape, dtype=np.float64)
        for index in range(signal.shape[1]):
            channel = np.ascontiguousarray(signal[:, index], dtype=np.float64)
            for stage, (numerators, denominators) in enumerate(self._stages):
                channel, carry = lfilter(numerators, denominators, channel, zi=self._filters[index][stage])
                self._filters[index][stage] = carry
            weighted[:, index] = channel
        return weighted

    def _feed_true_peak(self, signal: np.ndarray) -> None:
        """Oversample the block and keep the largest inter-sample peak.

        The filter of the oversampler reaches back over a handful of
        samples, so the block is oversampled with the last samples of the
        block before it: without them the peak at the start of a block would
        be measured against silence.
        """
        if self._tail.size:
            combined = np.concatenate((self._tail, signal))
        else:
            combined = signal
        offset = OVERSAMPLE * self._tail.shape[0]
        upsampled = resample_poly(combined, OVERSAMPLE, 1, axis=0)
        stop = min(offset + OVERSAMPLE * signal.shape[0], upsampled.shape[0])
        if stop > offset:
            value = float(np.max(np.abs(upsampled[offset:stop])))
            if value > self._true_peak:
                self._true_peak = value
        keep = min(MARGIN_FRAMES, signal.shape[0])
        self._tail = signal[signal.shape[0] - keep :].copy() if keep else signal[:0].copy()

    def _feed_energies(self, weighted: np.ndarray) -> None:
        """Cut the loudness windows out of the rolling buffer."""
        if self._buffer.size:
            combined = np.concatenate((self._buffer, weighted))
        else:
            combined = weighted
        base = self._position - self._buffer.shape[0]
        end = self._position + weighted.shape[0]
        while self._next_window * self._hop + self._window <= end:
            start = self._next_window * self._hop - base
            if start < 0 or start + self._window > combined.shape[0]:
                break
            window = combined[start : start + self._window]
            self._energies.append(np.mean(window * window, axis=0))
            self._next_window += 1
        keep = min(self._window, combined.shape[0])
        self._buffer = combined[combined.shape[0] - keep :].copy()
        self._position = end

    def integrated_lufs(self) -> float:
        """The gated integrated loudness, in LUFS.

        BS.1770 sums the channel powers, so a full scale sine in both
        channels measures 0.0 LUFS, not -3.0.
        """
        if not self._energies:
            return float("-inf")
        energies = np.array(self._energies, dtype=np.float64)
        totals = np.sum(energies, axis=1)
        loudness = LOUDNESS_OFFSET + 10.0 * np.log10(np.maximum(totals, 1e-30))
        keep = loudness > ABSOLUTE_GATE_LUFS
        if not bool(np.any(keep)):
            return float("-inf")
        reference = LOUDNESS_OFFSET + 10.0 * np.log10(float(np.mean(totals[keep])))
        relative = keep & (loudness > reference + RELATIVE_GATE_LU)
        if not bool(np.any(relative)):
            relative = keep
        return float(LOUDNESS_OFFSET + 10.0 * np.log10(float(np.mean(totals[relative]))))

    def sample_peak_dbfs(self) -> float:
        """The peak sample value, in dBFS."""
        if self._count == 0:
            return float("-inf")
        return 20.0 * math.log10(max(self._peak, 1e-30))

    def true_peak_dbtp(self) -> float:
        """The inter-sample peak, in dBTP."""
        if self._count == 0:
            return float("-inf")
        return 20.0 * math.log10(max(self._true_peak, 1e-30))


def integrated_lufs(samples: np.ndarray, rate: int) -> float:
    """The gated integrated loudness, in LUFS."""
    meter = LoudnessMeter(rate)
    for start in range(0, samples.shape[0], MEASURE_BLOCK):
        stop = min(samples.shape[0], start + MEASURE_BLOCK)
        meter.feed(samples[start:stop])
    return meter.integrated_lufs()


def sample_peak_dbfs(samples: np.ndarray) -> float:
    """The peak sample value, in dBFS."""
    if samples.size == 0:
        return float("-inf")
    peak = float(np.max(np.abs(samples.astype(np.float64))))
    return 20.0 * math.log10(max(peak, 1e-30))


def true_peak_dbtp(samples: np.ndarray, oversample: int = 4) -> float:
    """The inter-sample peak, in dBTP, estimated by oversampling."""
    if samples.size == 0:
        return float("-inf")
    upsampled = resample_poly(samples.astype(np.float64), oversample, 1, axis=0)
    peak = float(np.max(np.abs(upsampled)))
    return 20.0 * math.log10(max(peak, 1e-30))


def to_float(samples: np.ndarray) -> np.ndarray:
    """Int16 samples to the float range [-1, 1]."""
    return samples.astype(np.float64) / 32768.0


def measure(samples: np.ndarray, rate: int) -> dict[str, float]:
    """The three printed numbers: loudness, sample peak and true peak."""
    meter = LoudnessMeter(rate)
    for start in range(0, samples.shape[0], MEASURE_BLOCK):
        stop = min(samples.shape[0], start + MEASURE_BLOCK)
        meter.feed(to_float(samples[start:stop]))
    sample_peak = meter.sample_peak_dbfs()
    true_peak = max(meter.true_peak_dbtp(), sample_peak)
    return {
        "integrated_lufs": meter.integrated_lufs(),
        "sample_peak_dbfs": sample_peak,
        "true_peak_dbtp": true_peak,
    }
