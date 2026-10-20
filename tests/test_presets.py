"""AC-13, AC-14, AC-15, AC-17: the preset files and their identities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from indiegen.config import LANE_NAMES, load_preset
from indiegen.errors import PlanError

ALIAS_TABLE: dict[str, tuple[str, str]] = {
    "motorik": ("Steady Hand", "Sixteen Steps"),
    "kosmische": ("Hollow Signal", "Sustained Weather"),
    "ambient": ("Long Exposure", "Rooms in Half Light"),
    "dub-electronic": ("Silt", "Chamber Echoes"),
    "indie-noise": ("Tin Roof", "Loose Ends"),
}


def test_presets_dir_holds_exactly_six_files(presets_dir: Path) -> None:
    names = sorted(path.name for path in presets_dir.iterdir() if path.is_file())
    assert names == sorted(["station.yaml", *[f"{lane}.yaml" for lane in LANE_NAMES]])


def test_station_preset_loads(presets_dir: Path) -> None:
    preset = load_preset("station", presets_dir=presets_dir)
    assert preset.kind == "station"
    assert len(preset.lanes) == 5
    assert sum(entry.weight for entry in preset.station.lane_weights) == 100


@pytest.mark.parametrize("lane", LANE_NAMES)
def test_lane_preset_loads(presets_dir: Path, lane: str) -> None:
    preset = load_preset(lane, presets_dir=presets_dir)
    assert preset.kind == "lane"
    assert preset.lanes[0].lane == lane


def test_every_file_declares_its_kind(presets_dir: Path) -> None:
    for path in presets_dir.iterdir():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["kind"] == ("station" if path.name == "station.yaml" else "lane")


def test_unknown_key_is_rejected(tmp_path: Path, presets_dir: Path) -> None:
    for source in presets_dir.iterdir():
        (tmp_path / source.name).write_text(source.read_text(encoding="utf-8") + "\nunknown_key: 1\n")
    with pytest.raises(PlanError):
        load_preset("station", presets_dir=tmp_path)


def test_unknown_preset_raises_plan_error(presets_dir: Path) -> None:
    with pytest.raises(PlanError):
        load_preset("does-not-exist", presets_dir=presets_dir)


def test_empty_preset_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "station.yaml").write_text("", encoding="utf-8")
    with pytest.raises(PlanError):
        load_preset("station", presets_dir=tmp_path)


def test_no_merge_machinery_in_the_preset_files(presets_dir: Path) -> None:
    for path in presets_dir.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "<<" not in text
        assert "&" not in text
        assert "*" not in text
        assert "extends" not in text


@pytest.mark.parametrize("lane", sorted(ALIAS_TABLE))
def test_alias_table_is_exact(presets_dir: Path, lane: str) -> None:
    alias, album = ALIAS_TABLE[lane]
    parameters = load_preset(lane, presets_dir=presets_dir).lanes[0].parameters
    assert parameters.alias == alias
    assert parameters.album == album


def test_station_declares_no_artist_or_album(presets_dir: Path) -> None:
    raw: dict[str, Any] = yaml.safe_load((presets_dir / "station.yaml").read_text(encoding="utf-8"))
    assert "alias" not in raw
    assert "album" not in raw
    assert "artist" not in raw


def test_lane_file_token_has_no_hyphen(presets_dir: Path) -> None:
    for lane in LANE_NAMES:
        parameters = load_preset(lane, presets_dir=presets_dir).lanes[0].parameters
        assert "-" not in parameters.file_token
        assert parameters.file_token.isalnum()
