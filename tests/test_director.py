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
    assert move.applies_to == ["pad"]


def test_strategy_deck_holds_exactly_one_entry(composed_plan: Plan) -> None:
    assert len(composed_plan.strategy_deck) == 1


def test_a_move_applies_only_to_the_kinds_it_lists(composed_plan: Plan) -> None:
    """A move that lists the pad must not touch a pluck."""
    from indiegen.plan import PluckEvent, Rational

    pluck = PluckEvent(
        kind="pluck",
        instrument="ks",
        start_frame=0,
        duration_frames=44100,
        midi=38,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=998, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=300,
        detune_cents=0,
        excitation_seed=1,
    )
    padded = composed_plan.model_copy(update={"events": [*composed_plan.events, pluck]})
    directed = director(padded)
    plucks = [event for event in directed.events if event.kind == "pluck"]
    assert len(plucks) == 1
    assert plucks[0].midi == 38


def test_a_move_that_matched_nothing_is_not_logged(composed_plan: Plan) -> None:
    from indiegen.plan import PluckEvent, Rational

    only_pluck = PluckEvent(
        kind="pluck",
        instrument="ks",
        start_frame=0,
        duration_frames=44100,
        midi=38,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=998, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=300,
        detune_cents=0,
        excitation_seed=1,
    )
    padded = composed_plan.model_copy(update={"events": [only_pluck]})
    directed = director(padded)
    assert directed.director_log == []


def test_the_move_transposes_the_material(composed_plan: Plan) -> None:
    plan = director(composed_plan)
    pads = [event for event in plan.events if event.kind == "pad"]
    assert len(pads) == 2
    head, tail = pads
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
