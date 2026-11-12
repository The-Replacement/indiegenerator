"""The catalog: what the library holds.

The catalog is built from the sidecars, not by re-rendering. The sidecar is
the plan's half of the artifact and the FLAC next to it is the other half:
the sidecar carries the plan, the plan hash, the PCM hash and the
measurements, so the catalog can be read without rendering a second time and
cannot disagree with what is on disk.

The key is the decoded PCM's SHA-256, which is the identity of the audio.
Two seeds that produce the same audio share a key, and the catalog says so
rather than losing one of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from indiegen.errors import RenderError
from indiegen.plan import canonical_bytes
from indiegen.writer import publish_atomically, staging_dir

SCHEMA: str = "indiegen/catalog/1"
CATALOG_NAME: str = "catalog.json"


@dataclass(frozen=True)
class CatalogEntry:
    """One track in the library."""

    pcm_sha256: str
    seed: int
    preset: str
    lane: str
    form: str
    duration_seconds: float
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range_lu: float
    techniques: list[str]
    sections: list[dict[str, Any]]
    director_log: list[dict[str, Any]]
    path: str
    size_bytes: int
    alias: str = ""
    album: str = ""
    title: str = ""


@dataclass
class Catalog:
    """The library, keyed by the decoded PCM's hash."""

    entries: dict[str, CatalogEntry] = field(default_factory=dict)
    duplicate_seeds: list[dict[str, Any]] = field(default_factory=list)
    duplicate_hashes: list[dict[str, Any]] = field(default_factory=list)
    total_bytes: int = 0
    unsided: list[str] = field(default_factory=list)
    """FLACs in the directory that carry no readable sidecar.

    They cannot be catalogued - the sidecar IS the metadata - and leaving them
    out without saying so turns "the library has eleven tracks" into "the
    library has nothing" while still printing success (c36). A directory that
    takes hand-dropped audio, like the radio's, will legitimately have some.
    """

    def as_json(self) -> dict[str, Any]:
        """The catalog as the JSON that lands on disk."""
        return {
            "schema": SCHEMA,
            "count": len(self.entries),
            "total_bytes": self.total_bytes,
            "duplicate_seeds": self.duplicate_seeds,
            "duplicate_hashes": self.duplicate_hashes,
            "tracks": {
                digest: {
                    "pcm_sha256": entry.pcm_sha256,
                    "seed": entry.seed,
                    "preset": entry.preset,
                    "lane": entry.lane,
                    "form": entry.form,
                    "alias": entry.alias,
                    "album": entry.album,
                    "title": entry.title,
                    "duration_seconds": round(entry.duration_seconds, 3),
                    "integrated_lufs": round(entry.integrated_lufs, 3),
                    "true_peak_dbtp": round(entry.true_peak_dbtp, 3),
                    "loudness_range_lu": round(entry.loudness_range_lu, 3),
                    "techniques": list(entry.techniques),
                    "sections": entry.sections,
                    "director_log": entry.director_log,
                    "path": entry.path,
                    "size_bytes": entry.size_bytes,
                }
                for digest, entry in sorted(self.entries.items())
            },
        }


MAX_SIDECAR_BYTES: int = 50 * 1024 * 1024


def _reject_json_constant(value: str) -> Any:
    """Sidecars are data, not code: NaN/Infinity are not valid measurements."""
    raise ValueError(f"invalid JSON constant in sidecar: {value}")


def read_sidecar(path: Path) -> dict[str, Any] | None:
    """Read one sidecar, or nothing if it is not a sidecar."""
    try:
        if path.stat().st_size > MAX_SIDECAR_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except OSError, json.JSONDecodeError, ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != "indiegen/sidecar/1":
        return None
    return payload


def entry_from_sidecar(path: Path, payload: dict[str, Any], size_bytes: int) -> CatalogEntry | None:
    """The catalog entry of one track, from its sidecar."""
    digest = payload.get("pcm_sha256")
    plan = payload.get("plan")
    measurements = payload.get("measurements")
    if not isinstance(digest, str) or not isinstance(plan, dict) or not isinstance(measurements, dict):
        return None
    return CatalogEntry(
        pcm_sha256=digest,
        seed=int(payload.get("seed", 0)),
        preset=str(payload.get("preset", "")),
        lane=str(payload.get("lane", "")),
        form=str(plan.get("form", "")),
        alias=str(plan.get("alias", "")),
        album=str(plan.get("album", "")),
        title=str(plan.get("title", "")),
        duration_seconds=float(measurements.get("duration_seconds", 0.0)),
        integrated_lufs=float(measurements.get("integrated_lufs", 0.0)),
        true_peak_dbtp=float(measurements.get("true_peak_dbtp", 0.0)),
        loudness_range_lu=float(measurements.get("loudness_range_lu", 0.0)),
        techniques=[str(name) for name in plan.get("techniques", [])],
        sections=[dict(section) for section in plan.get("sections", [])],
        director_log=[dict(move) for move in plan.get("director_log", [])],
        path=str(path),
        size_bytes=size_bytes,
    )


def build_catalog(directory: Path) -> Catalog:
    """Read every sidecar of a directory and build the catalog."""
    catalog = Catalog()
    seeds_by_hash: dict[str, list[int]] = {}
    paths_by_hash: dict[str, list[str]] = {}
    paths_by_seed: dict[int, list[str]] = {}
    if not directory.is_dir():
        return catalog
    catalog.unsided = [
        str(flac) for flac in sorted(directory.glob("*.flac")) if read_sidecar(flac.with_suffix(".json")) is None
    ]
    for sidecar in sorted(directory.glob("*.json")):
        if sidecar.name == CATALOG_NAME:
            continue
        payload = read_sidecar(sidecar)
        if payload is None:
            continue
        flac = sidecar.with_suffix(".flac")
        size = flac.stat().st_size if flac.is_file() else 0
        try:
            entry = entry_from_sidecar(flac, payload, size)
        except TypeError, ValueError, KeyError:
            # A malformed sidecar must not take down the whole catalog: skip it.
            continue
        if entry is None:
            continue
        catalog.entries[entry.pcm_sha256] = entry
        # The total is what the library occupies on disk, duplicates included:
        # it is a disk-usage number, while `entries` is the set of distinct
        # audio. A duplicate that overwrites an entry is not lost to the
        # catalog: its path is kept with its hash below.
        catalog.total_bytes += entry.size_bytes
        seeds_by_hash.setdefault(entry.pcm_sha256, []).append(entry.seed)
        paths_by_hash.setdefault(entry.pcm_sha256, []).append(entry.path)
        paths_by_seed.setdefault(entry.seed, []).append(entry.pcm_sha256)
    catalog.duplicate_seeds = [
        {"seed": seed, "pcm_sha256": digests} for seed, digests in sorted(paths_by_seed.items()) if len(digests) > 1
    ]
    catalog.duplicate_hashes = [
        {"pcm_sha256": digest, "seeds": sorted(set(seed_list)), "paths": sorted(paths_by_hash[digest])}
        for digest, seed_list in sorted(seeds_by_hash.items())
        if len(set(seed_list)) > 1
    ]
    return catalog


def write_catalog(directory: Path, catalog: Catalog) -> Path:
    """Write catalog.json into a directory, atomically."""
    target = directory / CATALOG_NAME
    temp_path = staging_dir(directory) / CATALOG_NAME
    data = canonical_bytes(catalog.as_json())
    try:
        with open(temp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
        publish_atomically(temp_path, target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError(f"cannot write the catalog: {exc}", preset="", seed=0, block_index=0) from exc
    return target
