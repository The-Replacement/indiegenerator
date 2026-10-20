"""AC-24, AC-25: the Director is pure and logs every move."""

from __future__ import annotations

import ast
from pathlib import Path

from indiegen.compose import director
from indiegen.plan import Plan, canonical_json


def test_director_is_pure(composed_plan: Plan) -> None:
    once = director(composed_plan)
    twice = director(composed_plan)
    assert canonical_json(once) == canonical_json(twice)
    assert len(composed_plan.director_log) == 0


def test_director_log_records_exactly_one_move(composed_plan: Plan) -> None:
    plan = director(composed_plan)
    assert len(plan.director_log) == 1
    move = plan.director_log[0]
    assert move.sample == 220500
    assert "fourth" in move.strategy
    assert move.crossfade_frames == 11025


def test_strategy_deck_holds_exactly_one_entry(composed_plan: Plan) -> None:
    assert len(composed_plan.strategy_deck) == 1


def test_the_move_transposes_the_material(composed_plan: Plan) -> None:
    plan = director(composed_plan)
    assert len(plan.events) == 2
    head, tail = plan.events
    assert tail.midi == head.midi + 5
    assert tail.start_frame < 220500 < head.start_frame + head.duration_frames


def test_director_module_constructs_no_rng() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "indiegen" / "compose" / "director.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "random"
                assert not alias.name.startswith("numpy.random")
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") != "random"
        if isinstance(node, ast.Name):
            assert node.id not in {"default_rng", "RandomState", "Generator"}
