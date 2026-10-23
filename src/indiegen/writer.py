"""The write path.

Liquidsoap is watching the output directory, so a half written FLAC is a
production bug: the file is written to ``out/.tmp``, fsynced, and then moved
into place with an atomic rename. Nothing is ever visible in the watched
directory until it is complete.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from indiegen.errors import DecodeError, RenderError
from indiegen.metadata import apply_tags
from indiegen.plan import canonical_bytes

TEMP_DIR_NAME: str = ".tmp"


def _fsync_dir(path: Path) -> None:
    """Make a directory entry durable."""
    handle = os.open(path, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def _checked_target(out_dir: Path, name: str, *, preset: str, seed: int) -> Path:
    """The final path of ``name``, refusing anything that leaves ``out_dir``.

    The name is built from the plan, and a plan can come from a file
    (``--from-plan``) or from a preset. ``Path`` discards the directory when
    the right hand side is absolute, so an unsanitised token is an arbitrary
    file write; this is the last line of defence behind the slug.
    """
    if not name or Path(name).name != name:
        raise RenderError(f"refusing a path as a track name: {name!r}", preset=preset, seed=seed, block_index=0)
    target = out_dir / name
    if not target.resolve().is_relative_to(out_dir.resolve()):
        raise RenderError(f"refusing to write outside {out_dir}: {name}", preset=preset, seed=seed, block_index=0)
    return target


def read_pcm(path: Path) -> np.ndarray:
    """Decode a file to interleaved int16, or say which file would not decode."""
    try:
        data, _ = sf.read(path, dtype="int16", always_2d=True)
    except (OSError, RuntimeError) as exc:
        raise DecodeError(f"cannot decode {path}: {exc}") from exc
    return np.ascontiguousarray(data, dtype="<i2")


def pcm_sha256(samples: np.ndarray) -> str:
    """SHA-256 of the interleaved little endian int16 samples."""
    return hashlib.sha256(np.ascontiguousarray(samples, dtype="<i2").tobytes()).hexdigest()


def staging_dir(out_dir: Path) -> Path:
    """The directory a file is written to before it is published."""
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    temp_dir = out_dir / TEMP_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    return temp_dir


def publish_atomically(temp_path: Path, target: Path) -> None:
    """Fsync the staged file, then rename it into place and fsync the directory.

    The one write discipline of the program: Liquidsoap watches the target
    directory, so nothing is visible there until it is complete and durable.
    """
    with open(temp_path, "rb") as handle:
        os.fsync(handle.fileno())
    _fsync_dir(temp_path.parent)
    os.replace(temp_path, target)
    _fsync_dir(target.parent)


def write_flac_atomic(
    out_dir: Path,
    name: str,
    pcm: np.ndarray,
    sample_rate: int,
    tags: dict[str, str],
    *,
    preset: str = "",
    seed: int = 0,
) -> Path:
    """Write the master, atomically, and return its final path."""
    target = _checked_target(out_dir, name, preset=preset, seed=seed)
    temp_path = staging_dir(out_dir) / target.name
    try:
        sf.write(temp_path, pcm, sample_rate, subtype="PCM_16", format="FLAC")
        apply_tags(temp_path, tags)
        os.chmod(temp_path, 0o644)
        publish_atomically(temp_path, target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError(f"cannot write {name}: {exc}", preset=preset, seed=seed, block_index=0) from exc
    return target


def write_sidecar_atomic(
    out_dir: Path,
    name: str,
    payload: dict[str, Any],
    *,
    preset: str = "",
    seed: int = 0,
) -> Path:
    """Write the JSON sidecar next to the master, atomically."""
    sidecar = f"{Path(name).stem}.json"
    target = _checked_target(out_dir, sidecar, preset=preset, seed=seed)
    temp_path = staging_dir(out_dir) / target.name
    data = canonical_bytes(payload)
    try:
        with open(temp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
        os.chmod(temp_path, 0o644)
        publish_atomically(temp_path, target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError(f"cannot write sidecar for {name}: {exc}", preset=preset, seed=seed, block_index=0) from exc
    return target
