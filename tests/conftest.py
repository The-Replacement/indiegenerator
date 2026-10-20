"""Shared fixtures for the S0 suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from typer.testing import CliRunner

from indiegen.compose import compose, director
from indiegen.config import load_preset

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
PRESETS_DIR: Path = REPO_ROOT / "presets"
GOLDEN_DIR: Path = Path(__file__).resolve().parent / "golden"
SEED: int = 1042
SECONDS: int = 10


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def presets_dir() -> Path:
    """The repository's preset directory."""
    return PRESETS_DIR


@pytest.fixture(scope="session")
def cli_runner() -> CliRunner:
    """A typer CLI runner."""
    return CliRunner()


@pytest.fixture(scope="session")
def composed_plan() -> Any:
    """The plan before the Director runs."""
    return compose(load_preset("station"), SEED, SECONDS * 44100)


@pytest.fixture(scope="session")
def reference_plan() -> Any:
    """The composed and directed plan for the canonical preset and seed."""
    return director(compose(load_preset("station"), SEED, SECONDS * 44100))


@pytest.fixture(scope="session")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One canonical render, reused across the suite."""
    out = tmp_path_factory.mktemp("render")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "indiegen.cli",
            "render",
            "--preset",
            "station",
            "--seed",
            str(SEED),
            "--seconds",
            str(SECONDS),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = dict(line.split(": ", 1) for line in result.stdout.strip().splitlines() if ": " in line)
    flac = next(out.glob("*.flac"))
    sidecar = next(out.glob("*.json"))
    return {
        "out_dir": out,
        "flac": flac,
        "sidecar": sidecar,
        "lines": lines,
        "stdout": result.stdout,
    }


@pytest.fixture(scope="session")
def decoded(rendered: dict[str, Any]) -> np.ndarray:
    """The decoded int16 of the canonical render."""
    import soundfile as sf

    data, _ = sf.read(rendered["flac"], dtype="int16", always_2d=True)
    return data
