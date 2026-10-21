"""AC-52, AC-53: the frozen S0 artifact must survive the S1 pipeline.

S0's committed canonical plan bytes are migrated field by field into the S1
model without changing a single value the renderer reads, and the result must
render to S0's ``pcm_sha256`` exactly. If the migration changed anything the
renderer looks at, this test fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from indiegen.master.chain import master
from indiegen.plan import Plan, canonical_json
from indiegen.render import render_plan
from indiegen.writer import pcm_sha256
from tests.conftest import GOLDEN_DIR

S0_PCM_SHA256: str = "892cb06a76244f43c97336295574d24910bc188d318ed29cd9ba696544e5cf78"


def migrate_s0_plan(payload: dict[str, Any]) -> Plan:
    """Migrate S0's committed plan into the S1 model.

    The migration adds the event discriminator, drops the field the renderer
    never read, turns the technique cards into names, adds the empty bus
    specifications and the Director's applicability, and changes the version.
    It changes no value the renderer reads.
    """
    migrated = json.loads(json.dumps(payload))
    events: list[dict[str, Any]] = []
    for event in migrated["events"]:
        event.pop("velocity_millibels", None)
        event["kind"] = "pad"
        events.append(event)
    migrated["events"] = events
    migrated["techniques"] = [card["name"].split("_")[0] for card in migrated["techniques"]]
    for move in migrated["strategy_deck"]:
        move["applies_to"] = ["pad"]
    for move in migrated["director_log"]:
        move["applies_to"] = ["pad"]
    migrated["delay_sends"] = []
    migrated["reverb"] = None
    migrated["version"] = 2
    return Plan.model_validate(migrated)


def test_the_frozen_s0_plan_renders_to_s0s_hash() -> None:
    payload = json.loads((GOLDEN_DIR / "plan_station_1042_s0.json").read_text(encoding="utf-8"))
    plan = migrate_s0_plan(payload)
    pcm = master(plan, render_plan(plan), 8192)
    assert pcm_sha256(pcm) == S0_PCM_SHA256


def test_the_migration_changes_no_value_the_renderer_reads() -> None:
    payload = json.loads((GOLDEN_DIR / "plan_station_1042_s0.json").read_text(encoding="utf-8"))
    plan = migrate_s0_plan(payload)
    original = payload["events"][0]
    migrated = plan.events[0].model_dump()
    for key, value in original.items():
        if key in {"velocity_millibels", "kind"}:
            continue
        assert migrated[key] == value, key


def test_the_pad_arithmetic_is_unchanged() -> None:
    """The whole-event cumsum stays: a block-wise one is not bit-identical."""
    source = (Path(__file__).resolve().parents[1] / "src" / "indiegen" / "synth" / "pad.py").read_text(encoding="utf-8")
    assert "np.cumsum(frequency)" in source
    assert "detunes = [0, *event.partial_detune_cents]" in source
    assert "np.power(2.0, drift / 1200.0)" in source


def test_the_migrated_plan_has_no_float_leaves() -> None:
    payload = json.loads((GOLDEN_DIR / "plan_station_1042_s0.json").read_text(encoding="utf-8"))
    plan = migrate_s0_plan(payload)
    assert isinstance(canonical_json(plan), bytes)
    for value in plan.model_dump(mode="json").values():
        assert not isinstance(value, float)
