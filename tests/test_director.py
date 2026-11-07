"""AC-24, AC-25, AC-5: the Director is pure, and it logs what it changed.

T14 makes the Director an arranger: it draws a transformation every 8 to
32 bars in a pulsed lane, applies it to the running plan, and writes down
what it did. The draw is compose()'s; the application is director()'s, and
it is a pure function over the plan.
"""

from __future__ import annotations

import ast
from pathlib import Path

from indiegen.compose import director, tension
from indiegen.plan import HatEvent, KickEvent, Plan, SnareEvent, canonical_json


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
    """A move that has nothing to move is not in the log.

    The moves are the ones the composer drew, so the test draws its own: a
    plan with a single pluck and a drop of the drums has nothing to drop,
    and the log stays empty.
    """
    from indiegen.plan import DirectorMove, PluckEvent, Rational

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
    move = DirectorMove(
        sample=0,
        strategy="drop_drums",
        detail="take the drums out for a while",
        parameter=0,
        crossfade_frames=44100,
        applies_to=["kick", "snare", "hat"],
    )
    padded = composed_plan.model_copy(update={"events": [only_pluck], "strategy_deck": [move]})
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


def _reharmonized(composed_plan: Plan) -> Plan:
    """The plan after one `reharmonize_relative` move over the whole track.

    The move is drawn here instead of left to the deck so that both tests
    below look at the same thing: every section moved, none of them skipped.
    """
    from indiegen.plan import DirectorMove

    move = DirectorMove(
        sample=0,
        strategy="reharmonize_relative",
        detail="reharmonize to the relative mode",
        parameter=0,
        crossfade_frames=0,
        applies_to=["bass"],
    )
    directed = director(composed_plan.model_copy(update={"strategy_deck": [move]}))
    assert len(directed.director_log) == 1
    return directed


def _notes_out_of_scale(plan: Plan) -> set[int]:
    """The melodic notes that sit outside the section they play in.

    The composer is allowed to write a chromatic note - the lane declares a
    chromatic budget and the motorik plan has one - so this is compared before
    and after a move rather than against empty: a move that adds one has
    broken the section's own claim on its notes.
    """
    from indiegen.plan import BassEvent, PluckEvent
    from indiegen.theory.scales import mode_scale

    found: set[int] = set()
    for section in plan.sections:
        scale = {note % 12 for note in mode_scale(section.mode, section.root_midi, 1)}
        for event in plan.events:
            if isinstance(event, BassEvent):
                notes = [(hit.frame, hit.midi) for hit in event.hits]
            elif isinstance(event, PluckEvent):
                notes = [(event.start_frame, event.midi)]
            else:
                continue
            for frame, midi in notes:
                if section.start_frame <= frame < section.end_frame and midi % 12 not in scale:
                    found.add(midi)
    return found


def test_the_reharmonize_move_puts_every_section_on_its_relative(composed_plan: Plan) -> None:
    """Every section moves to the mode it shares its notes with.

    That is the whole claim of a relative: the pitch content is unchanged and
    only the centre moves, which is what lets the notes already written stay
    inside the section after the Director has run. Nothing downstream
    re-derives a pitch from a section, so a mismatch would ship.
    """
    from indiegen.theory.scales import mode_scale, relative_of

    directed = _reharmonized(composed_plan)
    assert len(directed.sections) == len(composed_plan.sections)
    for before, after in zip(composed_plan.sections, directed.sections, strict=True):
        relative, interval = relative_of(before.mode)
        assert (after.mode, after.root_midi) == (relative, before.root_midi + interval)
        old_scale = {note % 12 for note in mode_scale(before.mode, before.root_midi, 1)}
        new_scale = {note % 12 for note in mode_scale(after.mode, after.root_midi, 1)}
        assert old_scale == new_scale, f"{before.mode} -> {after.mode} is not the same scale"


def test_the_reharmonize_move_follows_the_centre_with_the_bass_alone(composed_plan: Plan) -> None:
    """The bass moves to the new centre, the melody holds, nothing falls out.

    The last assertion is the one the old transposing move fails: it moved the
    plucks with the root, and a quarter of the motorik plucks then sat on a
    pitch class the section's own scale does not contain.
    """
    from indiegen.plan import BassEvent, PluckEvent

    directed = _reharmonized(composed_plan)
    bass_before = {hit.midi for e in composed_plan.events if isinstance(e, BassEvent) for hit in e.hits}
    bass_after = {hit.midi for e in directed.events if isinstance(e, BassEvent) for hit in e.hits}
    assert bass_after != bass_before, "the bass did not follow the new centre"
    melody_before = {event.midi for event in composed_plan.events if isinstance(event, PluckEvent)}
    melody_after = {event.midi for event in directed.events if isinstance(event, PluckEvent)}
    assert melody_after == melody_before, "the melody was moved instead of reinterpreted"
    assert _notes_out_of_scale(directed) <= _notes_out_of_scale(composed_plan)


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
        if not isinstance(event, (KickEvent, SnareEvent, HatEvent)):
            continue
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


def test_the_director_rederives_tension_from_the_final_events(composed_plan: Plan) -> None:
    """AC-4: the spent walk is recomputed from the final events, not copied.

    The deck rewrites pitched material, so the pre-Director walk is stale:
    the post-Director tension is the oracle walk over the final events at
    the final levels, starting at 500 with a zero first step.
    """
    directed = director(composed_plan)
    assert directed.sections[0].tension_permille == 500
    assert directed.sections[0].tension_delta_permille == 0
    # Oracle: the same section features and step, computed here rather than
    # by calling the re-derivation under test.
    pitched = tension.pitched_notes(directed.events)
    previous = None
    signs: dict[str, int] = {}
    current = tension.TENSION_START
    for section in directed.sections:
        features = tension.section_features(
            directed.events,
            section.start_frame,
            section.end_frame,
            section.bars,
            section.level_millibels,
            pitched,
        )
        if previous is None:
            expected_tension, expected_delta = tension.TENSION_START, 0
        else:
            expected_delta, signs = tension.step(features, previous, signs)
            current = max(0, min(1000, current + expected_delta))
            expected_tension = current
        assert (section.tension_permille, section.tension_delta_permille) == (expected_tension, expected_delta)
        previous = features
    # The pre-Director walk was stale: the dropped bass and the transposed
    # outro move material, so at least one section's walk differs.
    assert [s.tension_delta_permille for s in directed.sections] != [
        s.tension_delta_permille for s in composed_plan.sections
    ]


def test_rederivation_never_moves_levels_or_corridors(composed_plan: Plan) -> None:
    """AC-4.2: re-derivation is a statement, not a new trim."""
    directed = director(composed_plan)
    assert [s.level_millibels for s in directed.sections] == [s.level_millibels for s in composed_plan.sections]
    assert [(s.tension_delta_min_permille, s.tension_delta_max_permille) for s in directed.sections] == [
        (s.tension_delta_min_permille, s.tension_delta_max_permille) for s in composed_plan.sections
    ]
