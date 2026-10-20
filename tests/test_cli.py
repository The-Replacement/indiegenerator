"""AC-4 to AC-11: the CLI surface, its output contract and its error paths."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indiegen.cli import app
from indiegen.plan import Plan, canonical_json, plan_sha256

EXPECTED_KEYS: tuple[str, ...] = (
    "path",
    "sidecar",
    "duration",
    "format",
    "peak",
    "true_peak",
    "loudness",
    "sections",
    "techniques",
    "plan_sha256",
    "pcm_sha256",
    "render_seconds",
)


def test_help_lists_render_and_explain(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "render" in result.stdout
    assert "explain" in result.stdout


def test_version_prints_and_exits_zero(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert re.search(r"\d+\.\d+\.\d+", result.stdout)


@pytest.mark.parametrize("command", ["batch", "validate", "catalog", "install"])
def test_unregistered_commands_do_not_exist(cli_runner: CliRunner, command: str) -> None:
    result = cli_runner.invoke(app, [command])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_render_prints_exactly_twelve_lines(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(
        app,
        ["render", "--preset", "station", "--seed", "1042", "--seconds", "10", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 12
    keys = tuple(line.split(": ", 1)[0] for line in lines)
    assert keys == EXPECTED_KEYS
    for line in lines:
        assert re.match(r"^[a-z0-9_]+: .+$", line)


def test_render_accepts_fractional_minutes(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(
        app,
        ["render", "--preset", "station", "--seed", "1042", "--minutes", "0.16666666666666666", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "duration: 10.000000" in result.stdout


def test_seconds_win_over_minutes(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(
        app,
        [
            "render",
            "--preset",
            "station",
            "--seed",
            "1042",
            "--minutes",
            "5",
            "--seconds",
            "10",
            "--out",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "duration: 10.000000" in result.stdout


def test_explain_writes_the_plan_to_stdout_and_the_hash_to_stderr(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["explain", "--preset", "station", "--seed", "1042", "--seconds", "10"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    plan = Plan.model_validate(payload)
    assert "plan_sha256:" in result.stderr
    digest = result.stderr.strip().split("plan_sha256: ")[1].split()[0]
    assert digest == plan_sha256(plan)
    assert canonical_json(plan) == result.stdout.encode("utf-8").rstrip(b"\n")


def test_explain_matches_the_rendered_plan(cli_runner: CliRunner, tmp_path: Path) -> None:
    explained = cli_runner.invoke(app, ["explain", "--preset", "station", "--seed", "1042", "--seconds", "10"])
    rendered = cli_runner.invoke(
        app,
        ["render", "--preset", "station", "--seed", "1042", "--seconds", "10", "--out", str(tmp_path)],
    )
    assert explained.exit_code == 0
    assert rendered.exit_code == 0
    assert (
        plan_sha256(Plan.model_validate(json.loads(explained.stdout)))
        == rendered.stdout.split("plan_sha256: ")[1].split()[0]
    )


def test_from_plan_rolls_nothing(cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from indiegen.compose.rng import SplitMix64

    first = cli_runner.invoke(
        app,
        ["render", "--preset", "station", "--seed", "1042", "--seconds", "10", "--out", str(tmp_path)],
    )
    assert first.exit_code == 0
    sidecar = next(tmp_path.glob("*.json"))

    def explode(self: SplitMix64) -> int:
        raise AssertionError("the render path must not draw")

    monkeypatch.setattr(SplitMix64, "next_u64", explode)
    second = cli_runner.invoke(app, ["render", "--from-plan", str(sidecar), "--out", str(tmp_path / "again")])
    assert second.exit_code == 0
    assert second.stdout.split("pcm_sha256: ")[1].split()[0] == first.stdout.split("pcm_sha256: ")[1].split()[0]


def test_from_plan_with_a_disagreeing_seed_fails(cli_runner: CliRunner, tmp_path: Path) -> None:
    cli_runner.invoke(
        app,
        ["render", "--preset", "station", "--seed", "1042", "--seconds", "10", "--out", str(tmp_path)],
    )
    sidecar = next(tmp_path.glob("*.json"))
    result = cli_runner.invoke(app, ["render", "--from-plan", str(sidecar), "--seed", "999", "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "Traceback (most recent call last)" not in result.output


def test_unknown_preset_names_the_preset_and_the_seed(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(
        app,
        ["render", "--preset", "nope", "--seed", "4242", "--seconds", "10", "--out", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "nope" in result.output
    assert "4242" in result.output
    assert "Traceback (most recent call last)" not in result.output


def test_a_missing_seed_is_a_plain_error(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(app, ["render", "--preset", "station", "--seconds", "10", "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert "Traceback (most recent call last)" not in result.output


def test_no_bare_except_in_the_source() -> None:
    import ast

    package = Path(__file__).resolve().parents[1] / "src" / "indiegen"
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                raise AssertionError(f"bare except in {path.name}")
