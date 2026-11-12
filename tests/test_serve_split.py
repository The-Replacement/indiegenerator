"""SDD #65: dual-root publish/rotation (audio_root + meta_root)."""

from __future__ import annotations

import json
from pathlib import Path

from indiegen.serve import rotate_library


def _touch(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _stage_batch(stage: Path, names: list[str]) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    for name in names:
        if name.endswith(".json") or name == "catalog.json":
            payload = {"name": name}
            (stage / name).write_text(json.dumps(payload), encoding="utf-8")
        else:
            _touch(stage / name, b"FLACDATA:" + name.encode())


def test_rotate_library_splits_audio_and_metadata(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    audio = tmp_path / "audio"
    meta = tmp_path / "meta"
    _stage_batch(stage, ["a.flac", "a.json", "b.flac", "b.json", "catalog.json"])

    installed, removed = rotate_library(stage, audio, meta)

    assert set(installed) == {"a.flac", "b.flac", "a.json", "b.json", "catalog.json"}
    assert removed == []
    # Audio root: only flac
    assert sorted(p.name for p in audio.iterdir() if p.is_file()) == ["a.flac", "b.flac"]
    assert list(audio.glob("*.json")) == []
    assert not (audio / "catalog.json").exists()
    # Meta root: sidecars + catalog only
    assert sorted(p.name for p in meta.iterdir() if p.is_file()) == ["a.json", "b.json", "catalog.json"]
    assert list(meta.glob("*.flac")) == []
    # Catalog written last in install order
    assert installed[-1] == "catalog.json"


def test_rotate_library_removes_stale_per_root(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    audio = tmp_path / "audio"
    meta = tmp_path / "meta"
    audio.mkdir()
    meta.mkdir()
    # stale managed files
    _touch(audio / "old.flac", b"old")
    _touch(meta / "old.json", b"{}")
    _touch(meta / "catalog.json", b"{}")

    _stage_batch(stage, ["new.flac", "new.json", "catalog.json"])
    installed, removed = rotate_library(stage, audio, meta)

    assert set(installed) == {"new.flac", "new.json", "catalog.json"}
    assert set(removed) == {"old.flac", "old.json"}
    assert (audio / "new.flac").exists() and not (audio / "old.flac").exists()
    assert (meta / "new.json").exists() and not (meta / "old.json").exists()
    assert (meta / "catalog.json").exists()
    assert not (audio / "catalog.json").exists()
    assert not (audio / "new.json").exists()


def test_rotate_library_legacy_single_dir(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    music = tmp_path / "music"
    _stage_batch(stage, ["a.flac", "a.json", "catalog.json"])

    installed, removed = rotate_library(stage, music)

    assert removed == []
    assert sorted(p.name for p in music.iterdir() if p.is_file()) == ["a.flac", "a.json", "catalog.json"]


def test_rotate_library_publish_before_delete_per_root(tmp_path: Path) -> None:
    # Ensures new set is fully present; stale removed after publish.
    stage = tmp_path / "stage"
    audio = tmp_path / "audio"
    meta = tmp_path / "meta"
    audio.mkdir()
    meta.mkdir()
    _touch(audio / "keep.flac", b"old-keep")
    _touch(meta / "keep.json", b"{}")
    _stage_batch(stage, ["keep.flac", "keep.json", "catalog.json"])

    rotate_library(stage, audio, meta)

    assert (audio / "keep.flac").read_bytes().startswith(b"FLACDATA")
    assert (meta / "keep.json").exists()
    assert (meta / "catalog.json").exists()
