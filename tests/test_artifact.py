"""AC-19, AC-22, AC-23, AC-33, AC-42: the S0 artifact, end to end."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from tests.conftest import SECONDS, SEED

RATE: int = 44100
FRAMES: int = RATE * SECONDS


def test_exactly_one_flac_is_written(rendered: dict[str, Any]) -> None:
    flacs = list(rendered["out_dir"].glob("*.flac"))
    assert len(flacs) == 1
    assert rendered["flac"].name == flacs[0].name


def test_the_file_is_44100_hertz_stereo_sixteen_bit(rendered: dict[str, Any]) -> None:
    info = sf.info(rendered["flac"])
    assert info.samplerate == RATE
    assert info.channels == 2
    assert info.frames == FRAMES
    assert info.subtype == "PCM_16"


def test_the_first_and_last_samples_are_exactly_zero(decoded: np.ndarray) -> None:
    assert int(decoded[0, 0]) == 0
    assert int(decoded[0, 1]) == 0
    assert int(decoded[-1, 0]) == 0
    assert int(decoded[-1, 1]) == 0


def _mono(decoded: np.ndarray) -> np.ndarray:
    return decoded.astype(np.float64).mean(axis=1)


def _rms(signal: np.ndarray) -> float:
    """The energy of a window.

    The design claim is about the energy trajectory, not about a single
    sample: a peak test is decided by whichever transient happens to land
    in the window, so micro-timing can move a peak in or out and flip the
    result without the music changing. BRIEF 6's tension curve and gate
    5's per-second RMS are energy measures; this is the same yardstick.
    """
    return float(np.sqrt(np.mean(np.square(signal))))


def test_the_opening_is_quieter_than_the_body(decoded: np.ndarray) -> None:
    mono = _mono(decoded)
    opening = _rms(mono[: 300 * RATE // 1000])
    body = _rms(mono[RATE : 3 * RATE])
    assert opening < 0.8 * body


def test_the_closing_is_quieter_than_the_body(decoded: np.ndarray) -> None:
    mono = _mono(decoded)
    closing = _rms(mono[-500 * RATE // 1000 :])
    body = _rms(mono[RATE : 3 * RATE])
    assert closing < 0.8 * body


def test_no_internal_dropout(decoded: np.ndarray) -> None:
    mono = _mono(decoded)
    window = RATE // 10
    for start in range(RATE, mono.size - 600 * RATE // 1000, window):
        segment = mono[start : start + window]
        rms = 20.0 * np.log10(max(float(np.sqrt(np.mean(segment * segment))), 1e-12))
        assert rms > -60.0


def test_the_sample_peak_is_in_the_declared_band(decoded: np.ndarray) -> None:
    peak = 20.0 * np.log10(max(float(np.max(np.abs(decoded.astype(np.float64)))) / 32768.0, 1e-12))
    assert -5.0 <= peak <= -3.5


def test_the_hashes_agree_with_the_file(rendered: dict[str, Any], decoded: np.ndarray) -> None:
    digest = hashlib.sha256(np.ascontiguousarray(decoded, dtype="<i2").tobytes()).hexdigest()
    assert rendered["lines"]["pcm_sha256"] == digest
    sidecar = json.loads(rendered["sidecar"].read_text(encoding="utf-8"))
    assert sidecar["pcm_sha256"] == digest
    assert sidecar["plan_sha256"] == rendered["lines"]["plan_sha256"]


def test_the_sidecar_holds_no_wall_clock(rendered: dict[str, Any]) -> None:
    sidecar = json.loads(rendered["sidecar"].read_text(encoding="utf-8"))
    assert "date" not in sidecar
    assert "DATE" not in sidecar
    assert "timestamp" not in sidecar


@pytest.mark.slow
def test_two_processes_agree_on_both_hashes(tmp_path: Path) -> None:
    outputs: list[dict[str, str]] = []
    for index in range(2):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "indiegen.cli",
                "render",
                "--preset",
                "motorik",
                "--seed",
                str(SEED),
                "--seconds",
                str(SECONDS),
                "--out",
                str(tmp_path / str(index)),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(dict(line.split(": ", 1) for line in result.stdout.strip().splitlines() if ": " in line))
    assert outputs[0]["plan_sha256"] == outputs[1]["plan_sha256"]
    assert outputs[0]["pcm_sha256"] == outputs[1]["pcm_sha256"]


@pytest.mark.slow
def test_the_ambient_piece_matches_its_golden(tmp_path: Path) -> None:
    """The 90 s ambient piece is pinned by its decoded PCM hash."""

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "indiegen.cli",
            "render",
            "--preset",
            "ambient",
            "--seed",
            str(SEED),
            "--seconds",
            "90",
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    digest = result.stdout.split("pcm_sha256: ")[1].split()[0]
    golden = (Path(__file__).resolve().parent / "golden" / "pcm_ambient_1042.sha256").read_text().strip()
    assert digest == golden


@pytest.mark.slow
def test_a_different_seed_produces_different_audio(tmp_path: Path) -> None:
    hashes: list[str] = []
    for seed in (1042, 1043):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "indiegen.cli",
                "render",
                "--preset",
                "motorik",
                "--seed",
                str(seed),
                "--seconds",
                str(SECONDS),
                "--out",
                str(tmp_path / str(seed)),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        hashes.append(result.stdout.split("pcm_sha256: ")[1].split()[0])
    assert hashes[0] != hashes[1]
