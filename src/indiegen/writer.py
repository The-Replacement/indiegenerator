"""The write path.

Liquidsoap is watching the output directory, so a half written FLAC is a
production bug: the file is written to ``out/.tmp``, fsynced, and then moved
into place with an atomic rename. Nothing is ever visible in the watched
directory until it is complete.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from indiegen.errors import RenderError
from indiegen.metadata import apply_tags

TEMP_DIR_NAME: str = ".tmp"


def _fsync_dir(path: Path) -> None:
    """Make a directory entry durable."""
    handle = os.open(path, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def read_pcm(path: Path) -> np.ndarray:
    """Decode a file to interleaved int16."""
    data, _ = sf.read(path, dtype="int16", always_2d=True)
    return np.ascontiguousarray(data, dtype="<i2")


def pcm_sha256(samples: np.ndarray) -> str:
    """SHA-256 of the interleaved little endian int16 samples."""
    return hashlib.sha256(np.ascontiguousarray(samples, dtype="<i2").tobytes()).hexdigest()


def write_flac_atomic(out_dir: Path, name: str, pcm: np.ndarray, sample_rate: int, tags: dict[str, str]) -> Path:
    """Write the master, atomically, and return its final path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = out_dir / TEMP_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / name
    target = out_dir / name
    try:
        sf.write(temp_path, pcm, sample_rate, subtype="PCM_16", format="FLAC")
        apply_tags(temp_path, tags)
        with open(temp_path, "rb") as handle:
            os.fsync(handle.fileno())
        _fsync_dir(temp_dir)
        os.replace(temp_path, target)
        _fsync_dir(out_dir)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError(f"cannot write {name}: {exc}", preset="", seed=0, block_index=0) from exc
    return target


def write_sidecar_atomic(out_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    """Write the JSON sidecar next to the master, atomically."""
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = out_dir / TEMP_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{Path(name).stem}.json"
    temp_path = temp_dir / f"{Path(name).stem}.json"
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    try:
        with open(temp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(temp_dir)
        os.replace(temp_path, target)
        _fsync_dir(out_dir)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError(f"cannot write sidecar for {name}: {exc}", preset="", seed=0, block_index=0) from exc
    return target
