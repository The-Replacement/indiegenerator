"""AC-40, AC-41: the loudness meter agrees with ffmpeg, and the true peak does
not lie."""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from indiegen.master.loudness import integrated_lufs, loudness_range, measure, sample_peak_dbfs, true_peak_dbtp

RATE: int = 44100


def _ffmpeg_lufs(path: Path) -> float:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = result.stderr.split("Summary:")[-1]
    match = re.search(r"I:\s+(-?[\d.]+)\s+LUFS", summary)
    assert match is not None
    return float(match.group(1))


def _write(path: Path, samples: np.ndarray) -> None:
    sf.write(path, samples, RATE, subtype="PCM_16")


def test_the_meter_agrees_with_ffmpeg_on_a_one_kilohertz_sine(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    times = np.arange(RATE * 3) / RATE
    tone = np.sin(2.0 * math.pi * 1000.0 * times)
    path = tmp_path / "sine.wav"
    _write(path, np.stack([tone, tone], axis=1))
    ours = integrated_lufs(np.stack([tone, tone], axis=1), RATE)
    assert abs(ours - _ffmpeg_lufs(path)) <= 0.1


def test_the_meter_agrees_with_ffmpeg_on_a_noise_burst(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    generator = np.random.default_rng(3)
    noise = generator.standard_normal(RATE * 3) * (10.0 ** (-20.0 / 20.0))
    path = tmp_path / "noise.wav"
    _write(path, np.stack([noise, noise], axis=1))
    ours = integrated_lufs(np.stack([noise, noise], axis=1), RATE)
    assert abs(ours - _ffmpeg_lufs(path)) <= 0.1


def test_a_full_scale_sine_in_both_channels_reads_zero_lufs() -> None:
    times = np.arange(RATE * 3) / RATE
    tone = np.sin(2.0 * math.pi * 1000.0 * times)
    assert abs(integrated_lufs(np.stack([tone, tone], axis=1), RATE)) < 0.1


def test_true_peak_is_never_below_the_sample_peak() -> None:
    times = np.arange(RATE) / RATE
    tone = np.sin(2.0 * math.pi * 1000.0 * times)
    stereo = np.stack([tone, tone], axis=1)
    assert true_peak_dbtp(stereo) >= sample_peak_dbfs(stereo) - 1e-9


def test_true_peak_matches_the_analytic_inter_sample_maximum() -> None:
    times = np.arange(RATE) / RATE
    tone = np.sin(2.0 * math.pi * 1000.0 * times)
    stereo = np.stack([tone, tone], axis=1)
    analytic = 20.0 * math.log10(math.cos(math.pi * 1000.0 / RATE))
    assert abs(true_peak_dbtp(stereo) - analytic) < 0.1


def test_measure_returns_the_four_numbers() -> None:
    times = np.arange(RATE) / RATE
    tone = np.sin(2.0 * math.pi * 1000.0 * times) * 0.5
    values = measure(np.stack([tone, tone], axis=1), RATE)
    assert set(values) == {"integrated_lufs", "sample_peak_dbfs", "true_peak_dbtp", "loudness_range_lu"}
    assert values["sample_peak_dbfs"] < 0.0


def test_the_loudness_range_of_a_stationary_signal_is_almost_nothing() -> None:
    generator = np.random.default_rng(11)
    noise = generator.standard_normal(RATE * 20) * 0.1
    assert loudness_range(np.stack([noise, noise], axis=1), RATE) < 1.0


def test_the_loudness_range_of_a_ramp_is_its_span() -> None:
    times = np.arange(RATE * 40) / RATE
    ramp = 0.02 + 0.9 * times / 40.0
    tone = ramp * np.sin(2.0 * math.pi * 440.0 * times)
    assert loudness_range(np.stack([tone, tone], axis=1), RATE) > 8.0
