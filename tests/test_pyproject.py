"""AC-1, AC-2, AC-3: the pinned toolchain."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

RUNTIME_PINS: dict[str, str] = {
    "numpy": "2.5.4",
    "scipy": "1.18.1",
    "soundfile": "0.14.0",
    "pydantic": "2.14.1",
    "typer": "0.27.3",
    "PyYAML": "6.0.3",
    "mutagen": "1.48.1",
}

DEV_PINS: dict[str, str] = {
    "pytest": "9.1.1",
    "ruff": "0.17.1",
    "mypy": "2.4.0",
}


def _pyproject(repo_root: Path) -> dict[str, Any]:
    with open(repo_root / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)


def test_the_build_backend_is_pinned(repo_root: Path) -> None:
    data = _pyproject(repo_root)
    assert data["build-system"]["requires"] == ["hatchling==1.32.4"]
    assert data["build-system"]["build-backend"] == "hatchling.build"


def test_the_project_metadata(repo_root: Path) -> None:
    project = _pyproject(repo_root)["project"]
    assert project["name"] == "indiegenerator"
    assert project["requires-python"] == ">=3.15,<3.16"
    assert "Apache-2.0" in str(project["license"])
    assert project["authors"] == [{"name": "Juan Manuel Daza", "email": "juanmanueldaza@gmail.com"}]
    assert project["scripts"] == {"indiegen": "indiegen.cli:main"}


def test_the_source_layout_is_declared(repo_root: Path) -> None:
    data = _pyproject(repo_root)
    assert data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/indiegen"]
    assert not (repo_root / "setup.py").exists()
    assert not (repo_root / "poetry.lock").exists()
    assert not (repo_root / "uv.lock").exists()


def test_every_dependency_is_pinned(repo_root: Path) -> None:
    project = _pyproject(repo_root)["project"]
    runtime = {entry.split("==")[0]: entry.split("==")[1] for entry in project["dependencies"]}
    assert runtime == RUNTIME_PINS
    dev = {entry.split("==")[0]: entry.split("==")[1] for entry in project["optional-dependencies"]["dev"]}
    assert dev == DEV_PINS
    for entry in [*project["dependencies"], *project["optional-dependencies"]["dev"]]:
        assert "==" in entry
        assert not any(symbol in entry for symbol in (">=", "<=", "~=", "!=", "*"))


def test_the_tool_configuration(repo_root: Path) -> None:
    data = _pyproject(repo_root)
    assert data["tool"]["ruff"]["line-length"] == 120
    assert data["tool"]["ruff"]["lint"]["select"] == ["E", "F", "I", "N", "W", "UP", "B", "S", "RET", "SIM", "C90"]
    # No mccabe override: ruff's default ceiling of 10 applies, so the number
    # in the config cannot drift away from the number in the linter.
    assert "mccabe" not in data["tool"]["ruff"]["lint"]
    assert "S101" in data["tool"]["ruff"]["lint"]["per-file-ignores"]["tests/*"]
    assert "slow" in data["tool"]["pytest"]["ini_options"]["markers"][0]
    assert data["tool"]["mypy"]["strict"] is True
    assert data["tool"]["mypy"]["files"] == ["src"]
