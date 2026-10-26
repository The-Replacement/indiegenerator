"""c36: the sidecar travels with the track, and a catalog says what it skipped.

The install copied only the audio, so a freshly installed directory held FLACs
the catalog could not read and `catalog` reported a successful zero. The sidecar
is half the artifact, so the copy takes both. And a FLAC without a sidecar is
now named instead of silently dropped - the radio directory legitimately holds
hand-dropped audio, so this is a report, not a refusal.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from indiegen.catalog import build_catalog
from indiegen.cli import app


def _orphan(directory: Path, name: str = "hand_dropped.flac") -> Path:
    """A FLAC with no sidecar, of the kind the radio directory may hold."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"not really audio, but it is a file")
    return path


def test_a_flac_without_a_sidecar_is_named_not_dropped(tmp_path: Path) -> None:
    orphan = _orphan(tmp_path)
    catalog = build_catalog(tmp_path)
    assert catalog.entries == {}
    assert catalog.unsided == [str(orphan)]


def test_a_flac_with_a_sidecar_is_not_reported_as_unsided(tmp_path: Path) -> None:
    _orphan(tmp_path, "tracked.flac")
    (tmp_path / "tracked.json").write_text('{"schema": "indiegen/sidecar/1"}', encoding="utf-8")
    catalog = build_catalog(tmp_path)
    assert catalog.unsided == []


def test_the_catalog_command_says_what_it_cannot_read(tmp_path: Path) -> None:
    _orphan(tmp_path)
    result = CliRunner().invoke(app, ["catalog", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "tracks: 0" in result.output
    assert "no_sidecar: 1" in result.output
    assert "hand_dropped.flac" in result.output
