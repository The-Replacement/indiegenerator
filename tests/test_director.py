"""AC-24, AC-25, AC-5: the Director is pure, and it logs what it changed.

T14 makes the Director an arranger: it draws a transformation every 8 to
32 bars in a pulsed lane, applies it to the running plan, and writes down
what it did. The draw is compose()'s; the application is director()'s, and
it is a pure function over the plan.
"""

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


def test_the_log_holds_only_moves_that_changed_something(composed_plan: Plan) -> None:
    plan = director(composed_plan)
    for move in plan.director_log:
        assert move in plan.strategy_deck
    assert len(plan.director_log) <= len(plan.strategy_deck)


def test_the_deck_is_drawn_on_the_bar_grid(composed_plan: Plan) -> None:
    plan = composed_plan
    assert plan.strategy_deck
    bars = plan.frames_per_beat * plan.meter_numerator
    for move in plan.strategy_deck:
        assert move.sample % bars == 0
        assert move.sample < plan.duration_frames


def test_a_move_applies_only_to_the_instruments_it_lists(composed_plan: Plan) -> None:
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
    without_plucks = [event for event in composed_plan.events if event.kind != "pluck"]
    padded = composed_plan.model_copy(update={"events": [*without_plucks, pluck]})
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


def test_the_transposition_moves_the_material_up(composed_plan: Plan) -> None:
    """A transposition splits the sustained material and lifts the tail."""
    from indiegen.plan import DirectorMove

    move = DirectorMove(
        sample=44100,
        strategy="transpose_up_fourth",
        detail="transpose the sustained material up a fourth",
        parameter=5,
        crossfade_frames=11025,
        applies_to=["pad"],
    )
    plan = composed_plan.model_copy(update={"strategy_deck": [move]})
    directed = director(plan)
    assert len(directed.director_log) == 1
    before = {event.midi for event in composed_plan.events if event.kind == "pad"}
    after = {event.midi for event in directed.events if event.kind == "pad"}
    assert after != before
    assert any(midi - 5 in before for midi in after)


def test_the_motif_transforms_rewrite_the_appearances(composed_plan: Plan) -> None:
    """A motif move changes the plan's appearances and the plucks with them."""
    from indiegen.plan import DirectorMove

    assert composed_plan.motif_appearances
    later = [appearance for appearance in composed_plan.motif_appearances if appearance.start_frame > 44100]
    assert later
    before = {appearance.start_frame: tuple(appearance.notes) for appearance in later}
    move = DirectorMove(
        sample=44100,
        strategy="retrograde_motif",
        detail="play the motif backwards",
        parameter=0,
        crossfade_frames=0,
        applies_to=["motif"],
    )
    plan = composed_plan.model_copy(update={"strategy_deck": [move]})
    directed = director(plan)
    assert len(directed.director_log) == 1
    after = {appearance.start_frame: tuple(appearance.notes) for appearance in directed.motif_appearances}
    for start, notes in before.items():
        assert after[start] == tuple(reversed(notes))


def test_the_drum_drops_take_the_hits_out(composed_plan: Plan) -> None:
    """A drop removes the hits of its instruments inside its span."""
    from indiegen.plan import DirectorMove

    move = DirectorMove(
        sample=0,
        strategy="drop_drums",
        detail="take the drums out for a while",
        parameter=0,
        crossfade_frames=44100,
        applies_to=["kick", "snare", "hat"],
    )
    plan = composed_plan.model_copy(update={"strategy_deck": [move]})
    directed = director(plan)
    assert len(directed.director_log) == 1
    for event in directed.events:
        if event.instrument not in ("kick", "snare", "hat"):
            continue
        for hit in event.hits:
            assert not (0 <= hit.frame < 44100)


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
