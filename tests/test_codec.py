"""S4: the codec roundtrip and the ffmpeg cross-check.

Both need ffmpeg, which is a dev tool on this machine and not a runtime
dependency of the generator, so the gates that use them are tested here
and never run in the render path.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from indiegen.master.codec import CodecError, ebur128, mp3_roundtrip
from indiegen.master.loudness import integrated_lufs, true_peak_dbtp
from indiegen.validate import check_gate_11, check_gate_12

RATE: int = 44100


def _signal(seconds: float = 6.0) -> np.ndarray:
    count = int(seconds * RATE)
    times = np.arange(count) / RATE
    left = 0.4 * np.sin(2.0 * math.pi * 220.0 * times) + 0.2 * np.sin(2.0 * math.pi * 55.0 * times)
    right = 0.35 * np.sin(2.0 * math.pi * 221.0 * times) + 0.18 * np.sin(2.0 * math.pi * 55.0 * times)
    generator = np.random.default_rng(17)
    noise = generator.normal(0.0, 0.01, count)
    return np.stack([left + noise, right + noise], axis=1)


@pytest.fixture()
def flac(tmp_path: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    path = tmp_path / "signal.flac"
    sf.write(path, _signal(), RATE, subtype="PCM_16")
    return path


def test_our_loudness_agrees_with_ffmpeg(flac: Path) -> None:
    decoded, rate = sf.read(flac, always_2d=True)
    ours = integrated_lufs(decoded, rate)
    theirs = ebur128(flac)
    assert check_gate_11(ours, theirs["integrated_lufs"]) == []


def test_our_true_peak_agrees_with_ffmpeg(flac: Path) -> None:
    decoded, rate = sf.read(flac, always_2d=True)
    ours = true_peak_dbtp(decoded)
    theirs = ebur128(flac)
    assert abs(ours - theirs["true_peak_dbfs"]) < 0.2


def test_the_mp3_roundtrip_keeps_the_loudness_and_the_shape(flac: Path) -> None:
    comparison = mp3_roundtrip(flac)
    assert check_gate_12(comparison) == []


def test_the_roundtrip_reports_what_it_measured(flac: Path) -> None:
    comparison = mp3_roundtrip(flac)
    assert comparison.correlation > 0.9
    assert comparison.clipped == 0
    assert abs(comparison.lufs_after - comparison.lufs_before) < 0.5


def test_a_missing_ffmpeg_is_an_error_not_a_crash(tmp_path: Path) -> None:
    from indiegen.master import codec

    original = codec.FFMPEG
    codec.FFMPEG = "ffmpeg-that-is-not-there"
    try:
        with pytest.raises(CodecError):
            codec.ebur128(tmp_path / "nothing.flac")
    finally:
        codec.FFMPEG = original
