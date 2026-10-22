"""S5: the four new commands and their output contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indiegen.cli import app


@pytest.fixture()
def short_preset_dir(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the presets whose forms are seconds long.

    The gates that need a track with a length are off for these: the gates
    have their own tests, and a four second track has no novelty in it to
    find.
    """
    import copy

    import yaml

    import indiegen.batch as batch_module
    from indiegen.config import load_preset

    monkeypatch.setattr(batch_module, "run_gates", lambda *args, **kwargs: None)

    presets = load_preset("motorik")
    station = copy.deepcopy(presets.station)
    directory = tmp_path / "presets"
    directory.mkdir()
    for path in (repo_root / "presets").iterdir():
        (directory / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    raw = yaml.safe_load((directory / "station.yaml").read_text(encoding="utf-8"))
    raw["forms"] = [
        {"form": card.form, "weight": card.weight, "duration_range_seconds": [4, 6]} for card in station.forms
    ]
    (directory / "station.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return directory


def test_the_batch_renders_and_writes_the_catalog(
    cli_runner: CliRunner, short_preset_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = cli_runner.invoke(
        app,
        [
            "batch",
            "--preset",
            "motorik",
            "--count",
            "2",
            "--seed-base",
            "3000",
            "--out",
            str(out),
            "--presets-dir",
            str(short_preset_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "tracks: 2" in result.stdout
    assert "catalog:" in result.stdout
    assert (out / "catalog.json").is_file()
    assert len(list(out.glob("*.flac"))) == 2


def test_the_batch_refuses_a_seed_that_is_already_in_the_library(
    cli_runner: CliRunner, short_preset_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    arguments = [
        "batch",
        "--preset",
        "motorik",
        "--count",
        "1",
        "--seed-base",
        "3000",
        "--out",
        str(out),
        "--presets-dir",
        str(short_preset_dir),
    ]
    assert cli_runner.invoke(app, arguments).exit_code == 0
    again = cli_runner.invoke(app, arguments)
    assert again.exit_code == 1
    assert "already in the library" in again.output


def test_the_catalog_command_reports_the_library(cli_runner: CliRunner, short_preset_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    cli_runner.invoke(
        app,
        [
            "batch",
            "--preset",
            "motorik",
            "--count",
            "2",
            "--seed-base",
            "3000",
            "--out",
            str(out),
            "--presets-dir",
            str(short_preset_dir),
        ],
    )
    result = cli_runner.invoke(app, ["catalog", "--dir", str(out)])
    assert result.exit_code == 0
    assert "tracks: 2" in result.stdout
    payload = json.loads((out / "catalog.json").read_text(encoding="utf-8"))
    assert payload["count"] == 2
    assert payload["total_bytes"] > 0


@pytest.fixture(scope="session")
def real_track(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real sixty second track, rendered once."""
    from indiegen.batch import render_track
    from indiegen.compose import compose, director
    from indiegen.config import load_preset

    plan = director(compose(load_preset("motorik"), 1042, 60 * 44100))
    out = tmp_path_factory.mktemp("track")
    result = render_track(plan, out)
    assert result.outcome is not None
    return result.outcome.path


def test_the_validate_command_checks_a_file(cli_runner: CliRunner, real_track: Path) -> None:
    result = cli_runner.invoke(app, ["validate", str(real_track), "--no-codec"])
    assert result.exit_code == 0, result.output
    assert "ok:" in result.stdout


def test_the_install_command_copies_the_valid_tracks(cli_runner: CliRunner, real_track: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / real_track.name).write_bytes(real_track.read_bytes())
    (out / real_track.with_suffix(".json").name).write_bytes(real_track.with_suffix(".json").read_bytes())
    target = tmp_path / "installed"
    result = cli_runner.invoke(
        app,
        ["install", "--dir", str(out), "--to", str(target), "--no-codec"],
    )
    assert result.exit_code == 0, result.output
    assert "installed: 1" in result.stdout
    assert len(list(target.glob("*.flac"))) == 1


def test_the_install_refuses_a_track_that_failed_the_gates(
    cli_runner: CliRunner, real_track: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / real_track.name).write_bytes(real_track.read_bytes())
    sidecar = out / real_track.with_suffix(".json").name
    payload = json.loads(real_track.with_suffix(".json").read_text(encoding="utf-8"))
    payload["plan"]["duration_range_frames"] = [10, 20]
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    target = tmp_path / "installed"
    result = cli_runner.invoke(
        app,
        ["install", "--dir", str(out), "--to", str(target), "--no-codec"],
    )
    assert result.exit_code == 2
    assert "refused:" in result.output
    assert not list(target.glob("*.flac"))


def test_the_commands_are_registered(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"])
    for command in ("render", "batch", "catalog", "validate", "install", "explain"):
        assert command in result.stdout
