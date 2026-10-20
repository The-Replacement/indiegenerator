"""AC-16: every declared parameter group is declared in YAML and consumed.

The sweep copies the presets into a temporary directory, mutates exactly one
declared value in exactly one file, and checks that the composed Plan changes.
A group that is declared but ignored fails here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import canonical_json

SKIPPED_KEYS: frozenset[str] = frozenset({"kind", "lane", "strategy"})


def _mutate(value: Any) -> Any:
    """A changed value of the same shape, or None when there is none.

    Every integer leaf is incremented, so whichever value the composer draws
    from the group, the drawn result changes too. The keys that name a
    strategy or a lane are left alone: changing them would break the preset
    instead of changing what it produces.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return f"{value}x"
    if isinstance(value, list):
        if not value:
            return None
        return [_mutate(item) for item in value]
    if isinstance(value, dict):
        mutated = {key: _mutate(item) if key not in SKIPPED_KEYS else item for key, item in value.items()}
        if all(before == after for before, after in zip(value.values(), mutated.values(), strict=True)):
            return None
        return mutated
    return None


def _preset_name_for(path: Path) -> str:
    return "station" if path.name == "station.yaml" else path.stem


def _cases(presets_dir: Path) -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for path in sorted(presets_dir.iterdir()):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, value in raw.items():
            if key in SKIPPED_KEYS:
                continue
            if _mutate(value) is None:
                continue
            cases.append((path.name, key))
    return cases


def test_mutation_sweep_has_coverage(presets_dir: Path) -> None:
    cases = _cases(presets_dir)
    assert len(cases) >= 20
    files = {name for name, _ in cases}
    assert files == {
        "station.yaml",
        "ambient.yaml",
        "motorik.yaml",
        "kosmische.yaml",
        "dub-electronic.yaml",
        "indie-noise.yaml",
    }


@pytest.mark.parametrize("filename,key", _cases(Path(__file__).resolve().parents[1] / "presets"))
def test_mutating_one_declared_value_changes_the_plan(
    tmp_path: Path,
    filename: str,
    key: str,
) -> None:
    source_dir = Path(__file__).resolve().parents[1] / "presets"
    for path in source_dir.iterdir():
        (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    target = tmp_path / filename
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    raw[key] = _mutate(raw[key])
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    name = _preset_name_for(target)
    baseline = director(compose(load_preset(name, presets_dir=source_dir), 1042))
    changed = director(compose(load_preset(name, presets_dir=tmp_path), 1042))
    assert canonical_json(baseline) != canonical_json(changed)


def test_no_musical_literal_hides_in_the_source() -> None:
    forbidden = ("13230", "22050", "11025", "220500")
    package = Path(__file__).resolve().parents[1] / "src" / "indiegen"
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            assert value not in text, f"{value} is a musical literal in {path.name}"
