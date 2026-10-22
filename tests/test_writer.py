"""AC-27: the write path is atomic, because Liquidsoap is watching."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from indiegen.errors import RenderError
from indiegen.writer import write_flac_atomic, write_sidecar_atomic

TAGS: dict[str, str] = {
    "TITLE": "Low Tide",
    "ARTIST": "Hollow Signal",
    "ALBUM": "Sustained Weather",
    "DATE": "2026",
    "GENRE": "kosmische generative",
    "COMMENT": "seed=1042; preset=station; v1",
    "TRACKNUMBER": "1",
}


def _pcm(frames: int = 4410) -> np.ndarray:
    generator = np.random.default_rng(0)
    return generator.integers(-3000, 3000, size=(frames, 2), dtype=np.int16)


def test_the_happy_path_leaves_the_staging_directory_empty(tmp_path: Path) -> None:
    path = write_flac_atomic(tmp_path, "track.flac", _pcm(), 44100, TAGS)
    assert path.is_file()
    assert path.parent == tmp_path
    staging = tmp_path / ".tmp"
    assert staging.is_dir()
    assert list(staging.iterdir()) == []


def test_a_failure_before_the_rename_leaves_nothing_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(source: Any, destination: Any) -> None:
        raise OSError("injected failure")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(RenderError):
        write_flac_atomic(tmp_path, "track.flac", _pcm(), 44100, TAGS)
    staging = tmp_path / ".tmp"
    assert list(staging.iterdir()) == []
    assert not (tmp_path / "track.flac").exists()


def test_the_sidecar_is_written_atomically(tmp_path: Path) -> None:
    path = write_sidecar_atomic(tmp_path, "track.flac", {"plan": {"seed": 1}})
    assert path.is_file()
    assert path.name == "track.json"
    assert list((tmp_path / ".tmp").iterdir()) == []
