"""The codec roundtrip and the ffmpeg cross-check.

BRIEF 11's gate 11 (our loudness against ``ffmpeg -af ebur128``) and gate 12
(FLAC -> MP3 128 -> decode) both need ffmpeg. ffmpeg is a dev tool on this
machine and not a runtime dependency of the generator, so these live here
and the tests call them; the render path never does.

The measurements are the ones the gates read: the integrated loudness, the
sample peak, the correlation and the number of clipped samples.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from pydantic import BaseModel, ConfigDict

from indiegen.master.loudness import integrated_lufs, sample_peak_dbfs


class CodecComparison(BaseModel):
    """What the codec roundtrip measured."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    lufs_before: float
    lufs_after: float
    peak_before: float
    peak_after: float
    correlation: float
    clipped: int


FFMPEG: str = shutil.which("ffmpeg") or "ffmpeg"
MP3_BITRATE: str = "128k"


class CodecError(RuntimeError):
    """ffmpeg is missing, or it did not do what was asked."""


def ebur128(path: Path) -> dict[str, float]:
    """The loudness, the range and the true peak, as ffmpeg measures them.

    The summary is at the end of ffmpeg's output, so the last match of
    each figure is the one that counts: the running lines print a figure
    for every tenth of a second.
    """
    try:
        # A fixed argv list, no shell: FFMPEG is a constant name and every
        # argument below is ours. S603 flags any subprocess call.
        result = subprocess.run(  # noqa: S603
            [
                FFMPEG,
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
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CodecError(f"ffmpeg could not measure {path.name}: {exc}") from exc
    text = result.stderr
    integrated = re.findall(r"I:\s+(-?[\d.]+)\s+LUFS", text)
    loudness_range = re.findall(r"LRA:\s+(-?[\d.]+)\s+LU", text)
    peak = re.findall(r"Peak:\s+(-?[\d.]+)\s+dBFS", text)
    if not integrated or not peak:
        raise CodecError(f"ffmpeg did not report a loudness for {path.name}")
    return {
        "integrated_lufs": float(integrated[-1]),
        "loudness_range_lu": float(loudness_range[-1]) if loudness_range else 0.0,
        "true_peak_dbfs": float(peak[-1]),
    }


def mp3_roundtrip(path: Path) -> CodecComparison:
    """The file through MP3 128 and back, measured on both sides."""
    original, rate = sf.read(path, always_2d=True)
    with tempfile.TemporaryDirectory() as directory:
        encoded = Path(directory) / "roundtrip.mp3"
        try:
            subprocess.run(  # noqa: S603 - fixed argv, no shell
                [
                    FFMPEG,
                    "-hide_banner",
                    "-nostats",
                    "-loglevel",
                    "error",
                    "-i",
                    str(path),
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    MP3_BITRATE,
                    str(encoded),
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CodecError(f"ffmpeg could not encode {path.name}: {exc}") from exc
        decoded, decoded_rate = sf.read(encoded, always_2d=True)
    if decoded_rate != rate:
        raise CodecError(f"the roundtrip changed the sample rate: {decoded_rate} and {rate}")
    left = original[:, 0].astype(np.float64)
    right = decoded[:, 0].astype(np.float64)
    left = left - left.mean()
    right = right - right.mean()
    denominator = float(np.sqrt(np.sum(left**2) * np.sum(right**2)))
    correlation = float(np.sum(left * right) / denominator) if denominator > 0 else 0.0
    clipped = int(np.count_nonzero(np.abs(decoded) >= 1.0))
    return CodecComparison(
        lufs_before=integrated_lufs(original, rate),
        lufs_after=integrated_lufs(decoded, decoded_rate),
        peak_before=sample_peak_dbfs(original),
        peak_after=sample_peak_dbfs(decoded),
        correlation=correlation,
        clipped=clipped,
    )
