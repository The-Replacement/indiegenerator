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
from indiegen.errors import PlanError
from indiegen.plan import canonical_json

# density_scale_permille is skipped here and covered by tests/test_c32.py
# instead. It moves a euclid pulse count, and with euclid_k as small as 16 a
# one-permille step almost never crosses a whole pulse, so this sweep's +1
# mutation would report a consumed key as ignored. The dedicated test asserts
# the pulse count and the crest it produces.
SKIPPED_KEYS: frozenset[str] = frozenset({"kind", "lane", "strategy", "density_scale_permille"})


def _mutate_section_graph(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The graph with its numbers moved and its names left alone."""
    mutated: list[dict[str, Any]] = []
    for node in value:
        entry = dict(node)
        entry["density"] = int(node["density"]) + 1
        entry["level_millibels"] = int(node["level_millibels"]) - 1
        mutated.append(entry)
    return mutated


# Two groups need a gentler touch: a chord's intervals cannot all be moved
# at once without leaving the scale, and a motif bank is consumed by drawing
# one cell, so every cell has to move for the draw to change.
def _mutate_forms(value: Any) -> Any:
    """The forms, with every range's lower bound moved by one.

    The form's names are literals and the weight is the batch's business:
    the range is what the plan draws its duration from, and moving its
    lower bound always moves the draw.
    """
    mutated: list[dict[str, Any]] = []
    for card in value:
        low, high = card["duration_range_seconds"]
        mutated.append({**card, "duration_range_seconds": [low + 1, high]})
    return mutated


KEY_MUTATIONS: dict[str, Any] = {
    "chord_intervals": lambda value: [*value[:-1], value[-1] + 1],
    "motif_bank": lambda value: [[*cell[:-1], cell[-1] + 1] for cell in value],
    # A named condition is a literal: the sweep cannot change it without
    # making the preset unreadable, so it is left alone.
    "condition": lambda value: value,
    # The mode names are literals too, and the graph's node names are the
    # edges the arranger walks: both have to stay readable, so the sweep
    # moves the numbers around them instead.
    "mode_pool": lambda value: list(reversed(value)),
    "pulse": lambda value: "seconds" if value == "bars" else "bars",
    "tuning_system": lambda value: 1 if value == 0 else 0,
    "section_graph": _mutate_section_graph,
    "forms": _mutate_forms,
}


def _mutate(value: Any, key: str = "") -> Any:
    """A changed value of the same shape, or None when there is none.

    Every integer leaf moves, so that a value the composer draws from a range
    always changes too: a draw of ``min + u % n`` would otherwise survive a
    change to the range's upper bound.
    """
    if key in KEY_MUTATIONS:
        return KEY_MUTATIONS[key](value)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return f"{value}x"
    if isinstance(value, list):
        return _mutate_list(value)
    if isinstance(value, dict):
        return _mutate_dict(value)
    return None


def _mutate_list(value: list[Any]) -> list[Any] | None:
    """Every element changed, or ``None`` when one of them cannot change."""
    if not value:
        return None
    mutated = list(value)
    for index, item in enumerate(mutated):
        changed = _mutate(item)
        if changed is None:
            return None
        mutated[index] = changed
    return mutated


def _mutate_dict(value: dict[str, Any]) -> dict[str, Any] | None:
    """Every key changed except the skipped ones, or ``None`` when one cannot."""
    if not value:
        return None
    mutated = dict(value)
    for name, item in value.items():
        if name in SKIPPED_KEYS:
            continue
        changed = _mutate(item, name)
        if changed is None:
            return None
        mutated[name] = changed
    return mutated


def _preset_name_for(path: Path) -> str:
    return "station" if path.name == "station.yaml" else path.stem


def _cases(presets_dir: Path) -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for path in sorted(presets_dir.iterdir()):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, value in raw.items():
            if key in SKIPPED_KEYS:
                continue
            if _mutate(value, key) is None:
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
    raw[key] = _mutate(raw[key], key)
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    name = _preset_name_for(target)
    baseline = director(compose(load_preset(name, presets_dir=source_dir), 1042))
    changed = director(compose(load_preset(name, presets_dir=tmp_path), 1042))
    assert canonical_json(baseline) != canonical_json(changed)


def test_no_musical_literal_hides_in_the_source() -> None:
    forbidden = ("13230", "22050", "11025", "220500", "132300", "2205")
    package = Path(__file__).resolve().parents[1] / "src" / "indiegen"
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            assert value not in text, f"{value} is a musical literal in {path.name}"


def test_the_sweep_would_catch_an_unconsumed_key(tmp_path: Path) -> None:
    """The sweep has teeth: a key the composer ignores cannot change the plan.

    This is the negative control for the mutation sweep. If a declared key
    were never read, mutating it would leave the plan untouched and the sweep
    above would be asserting nothing. The strict preset models are what make
    that impossible: a key nobody declared is rejected outright, and the
    composer is seeded from the preset's identity rather than its content, so
    the draw sequence does not move when a parameter does.
    """
    source_dir = Path(__file__).resolve().parents[1] / "presets"
    for path in source_dir.iterdir():
        (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    target = tmp_path / "ambient.yaml"
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    raw["unused_key"] = 1
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(PlanError):
        load_preset("ambient", presets_dir=tmp_path)

    # the composer seeds from the preset's identity, so the draw sequence
    # does not move when a parameter does: that is what lets the sweep tell
    # a parameter that is consumed from one that is merely declared.
    copied = tmp_path / "clean"
    copied.mkdir()
    for path in source_dir.iterdir():
        (copied / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    original = director(compose(load_preset("ambient", presets_dir=source_dir), 1042))
    duplicate = director(compose(load_preset("ambient", presets_dir=copied), 1042))
    assert canonical_json(original) == canonical_json(duplicate)
