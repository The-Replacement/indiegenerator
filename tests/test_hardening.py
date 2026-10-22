"""The hardening pass: inputs that arrive from outside the program.

Every plan can arrive from a file (``--from-plan``) or from a preset, and every
track on disk can arrive from somebody else's render. These are the tests of
the boundaries where that data enters.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from typer.testing import CliRunner

from indiegen import plan as plan_module
from indiegen.catalog import build_catalog
from indiegen.cli import app
from indiegen.errors import PlanError, RenderError
from indiegen.metadata import filename_for
from indiegen.plan import MAX_DURATION_FRAMES, Plan
from indiegen.writer import write_flac_atomic

TAGS: dict[str, str] = {
    "TITLE": "Low Tide",
    "ARTIST": "Hollow Signal",
    "ALBUM": "Sustained Weather",
    "DATE": "2026",
    "GENRE": "kosmische generative",
    "COMMENT": "seed=1042; preset=station; v1",
    "TRACKNUMBER": "1",
}


def _pcm(frames: int = 441) -> np.ndarray:
    return np.zeros((frames, 2), dtype=np.int16)


def test_a_hostile_file_token_never_becomes_a_path(reference_plan: Any) -> None:
    for token in ("../../../../etc/passwd", "/tmp/escape", "a/b", "", ".."):
        plan = reference_plan.model_copy(update={"file_token": token})
        name = filename_for(plan)
        assert Path(name).name == name, name
        assert "/" not in name and "\\" not in name
        assert ".." not in name


def test_the_writer_refuses_a_name_that_leaves_the_output_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    for name in ("/tmp/absolute.flac", "../outside.flac", "sub/dir.flac"):
        with pytest.raises(RenderError):
            write_flac_atomic(tmp_path / "out", name, _pcm(), 44100, TAGS)
    assert list(outside.iterdir()) == []


def test_a_plan_over_the_station_ceiling_is_refused(reference_plan: Any) -> None:
    payload = reference_plan.model_dump()
    payload["duration_frames"] = MAX_DURATION_FRAMES + 1
    with pytest.raises(PlanError):
        Plan.model_validate(payload)
    payload["duration_frames"] = 0
    with pytest.raises(PlanError):
        Plan.model_validate(payload)


def test_a_plan_with_too_many_events_is_refused(reference_plan: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_module, "MAX_EVENTS", 2)
    with pytest.raises(PlanError):
        Plan.model_validate(reference_plan.model_dump())


def test_a_plan_with_too_many_hits_is_refused(reference_plan: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_module, "MAX_HITS", 1)
    with pytest.raises(PlanError):
        Plan.model_validate(reference_plan.model_dump())


def test_the_validate_command_reports_a_corrupt_file(cli_runner: CliRunner, rendered: dict[str, Any]) -> None:
    directory = rendered["out_dir"]
    bad = directory / "corrupt.flac"
    bad.write_bytes(b"not audio")
    shutil.copy(rendered["sidecar"], directory / "corrupt.json")
    try:
        result = cli_runner.invoke(app, ["validate", str(bad)])
    finally:
        bad.unlink(missing_ok=True)
        (directory / "corrupt.json").unlink(missing_ok=True)
    assert result.exit_code == 1
    assert "error: corrupt.flac" in result.output
    assert "LibsndfileError" not in result.output


def test_the_catalog_keeps_the_path_of_a_duplicate(cli_runner: CliRunner, rendered: dict[str, Any]) -> None:
    directory = rendered["out_dir"]
    twin = directory / "twin.flac"
    shutil.copy(rendered["flac"], twin)
    sidecar = json.loads(rendered["sidecar"].read_text(encoding="utf-8"))
    sidecar["seed"] = 9999
    (directory / "twin.json").write_text(json.dumps(sidecar), encoding="utf-8")
    try:
        built = build_catalog(directory)
    finally:
        twin.unlink(missing_ok=True)
        (directory / "twin.json").unlink(missing_ok=True)
    assert built.duplicate_hashes, "the twin shares the PCM hash and the catalog did not say so"
    duplicate = built.duplicate_hashes[0]
    assert 9999 in duplicate["seeds"]
    assert len(duplicate["paths"]) == 2


def test_the_install_command_reports_skipped_codec_gates(cli_runner: CliRunner, rendered: dict[str, Any]) -> None:
    target = rendered["out_dir"].parent / "installed-skipped"
    shutil.rmtree(target, ignore_errors=True)
    result = cli_runner.invoke(
        app,
        ["install", "--dir", str(rendered["out_dir"]), "--to", str(target), "--no-codec"],
    )
    shutil.rmtree(target, ignore_errors=True)
    assert result.exit_code == 0, result.output
    assert "skipped: 1" in result.output
