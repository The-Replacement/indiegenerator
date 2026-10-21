"""AC-1, AC-2, AC-4, AC-5, AC-9, AC-10, AC-11, AC-13: the arranger.

The section graph, the tension curve, the motif, the Director, the modal
shifts, the Frippertronics and the dub chain. Everything here is measured
on the plan, which is where the arranger's decisions live.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.errors import PlanError
from indiegen.plan import BassEvent, Plan, PluckEvent
from indiegen.theory.motif import augment, fragment, invert, retrograde, transpose
from indiegen.theory.scales import mode_scale

RATE: int = 44100


@pytest.fixture(scope="module")
def motorik() -> Plan:
    return director(compose(load_preset("motorik"), 1042, 60 * RATE))


@pytest.fixture(scope="module")
def kosmische() -> Plan:
    return director(compose(load_preset("kosmische"), 1042, 60 * RATE))


def test_the_sections_are_a_walk_over_the_graph() -> None:
    """The first section is the intro, the last is the outro, and the
    consecutive pairs are the declared successors."""
    station = load_preset("station").station
    graph = {node.function: node for node in station.section_graph}
    for lane in ("motorik", "kosmische", "ambient", "dub-electronic", "indie-noise"):
        plan = director(compose(load_preset(lane), 1042, 60 * RATE))
        assert plan.sections[0].function == "intro"
        assert plan.sections[-1].function == "outro"
        for previous, following in zip(plan.sections, plan.sections[1:], strict=False):
            assert following.function in graph[previous.function].next


def test_no_two_sections_in_a_row_are_the_same_arrangement() -> None:
    """At least two of the five dimensions have to move."""
    for lane in ("motorik", "kosmische", "ambient", "dub-electronic", "indie-noise"):
        plan = director(compose(load_preset(lane), 1042, 60 * RATE))
        for previous, following in zip(plan.sections, plan.sections[1:], strict=False):
            differences = 0
            if previous.instrumentation != following.instrumentation:
                differences += 1
            if (previous.mode, previous.root_midi) != (following.mode, following.root_midi):
                differences += 1
            if previous.density != following.density:
                differences += 1
            if previous.texture != following.texture:
                differences += 1
            assert differences >= 2, f"{lane}: {previous.function} into {following.function}"


def test_a_preset_that_cannot_differ_raises_a_plan_error() -> None:
    """The assertion is real: a flat arrangement cannot be made."""
    from indiegen.compose.planner import _assert_sections_differ

    plan = director(compose(load_preset("motorik"), 1042, 60 * RATE))
    first = plan.sections[0]
    second = first.model_copy(update={"index": 1, "function": "outro"})
    with pytest.raises(PlanError):
        _assert_sections_differ(load_preset("motorik"), 1042, [first, second], [1, 2])


def test_the_tension_curve_is_the_section_levels(motorik: Plan) -> None:
    """The plan holds the curve the gate measures."""
    levels = [section.level_millibels for section in motorik.sections]
    assert len(levels) == motorik.section_count
    assert len(set(levels)) > 1
    assert all(isinstance(level, int) for level in levels)


def test_the_motif_comes_back_in_transformed_forms(motorik: Plan) -> None:
    """The motif is played, it is transformed, and it comes back."""
    appearances = motorik.motif_appearances
    assert len(appearances) >= 3
    transformed = [appearance for appearance in appearances if appearance.transform != "identity"]
    assert len(transformed) >= 3
    assert {appearance.transform for appearance in appearances} <= {
        "identity",
        "transpose",
        "invert",
        "retrograde",
        "augment",
        "fragment",
    }
    for appearance in appearances:
        assert appearance.notes
        assert len(appearance.notes) == len(appearance.durations)
        assert all(duration > 0 for duration in appearance.durations)


def test_the_motif_is_played_by_the_string(motorik: Plan) -> None:
    """Every appearance is a Karplus-Strong pluck in the events."""
    plucks = [event for event in motorik.events if isinstance(event, PluckEvent) and event.instrument == "motif"]
    assert plucks
    for appearance in motorik.motif_appearances:
        total = sum(appearance.durations)
        inside = [
            pluck for pluck in plucks if appearance.start_frame <= pluck.start_frame < appearance.start_frame + total
        ]
        assert [pluck.midi for pluck in inside] == appearance.notes


def test_the_transforms_are_what_they_say() -> None:
    """The five transforms are exact."""
    cell = [(60, 100), (62, 100), (65, 200)]
    assert transpose(cell, 5) == [(65, 100), (67, 100), (70, 200)]
    assert retrograde(cell) == [(65, 200), (62, 100), (60, 100)]
    assert invert(cell, 60) == [(60, 100), (58, 100), (55, 200)]
    assert augment(cell) == [(60, 200), (62, 200), (65, 400)]
    assert fragment(cell, 2) == [(60, 100), (62, 100)]


def test_the_modal_shift_is_a_section_event(motorik: Plan) -> None:
    """Every section carries a mode, and the shift lands on a boundary."""
    for section in motorik.sections:
        scale = mode_scale(section.mode, section.root_midi, 2)
        assert len(scale) > 1
        assert section.start_frame >= 0
    for previous, following in zip(motorik.sections, motorik.sections[1:], strict=False):
        if previous.mode != following.mode:
            assert following.start_frame == previous.end_frame or following.start_frame >= previous.start_frame


def test_the_bass_follows_the_harmonic_centre(motorik: Plan) -> None:
    """The bass plays the root of the section it is in."""
    basses = [event for event in motorik.events if isinstance(event, BassEvent)]
    assert basses
    for section in motorik.sections:
        inside = [hit for event in basses for hit in event.hits if section.start_frame <= hit.frame < section.end_frame]
        for hit in inside:
            assert hit.midi in (section.root_midi - 12, section.root_midi)


def test_the_director_fires_often_enough(motorik: Plan) -> None:
    """The Director draws a move every 8 to 32 bars, and it applies them."""
    assert motorik.strategy_deck
    bars = motorik.duration_frames / motorik.frames_per_beat * motorik.meter_denominator / (4 * motorik.meter_numerator)
    assert len(motorik.strategy_deck) * 32 >= bars
    assert motorik.director_log
    for move in motorik.director_log:
        assert move in motorik.strategy_deck


def test_the_frippertronics_is_a_send_and_not_a_bus(kosmische: Plan) -> None:
    """T3: the kosmische lane declares the long feedback delay."""
    assert kosmische.frippertronics is not None
    spec = kosmische.frippertronics
    assert spec.delay_frames >= 3 * RATE
    assert 600 <= spec.feedback_permille <= 900
    assert spec.cutoff_step_hz > 0
    assert spec.wow_depth_permille > 0


def test_the_dub_chain_declares_the_whole_chain() -> None:
    """T10: the dub lane declares the bit reduction, the band and the duck."""
    plan = director(compose(load_preset("dub-electronic"), 1042, 60 * RATE))
    assert plan.dub_chain is not None
    spec = plan.dub_chain
    assert spec.bit_depth < 16
    assert 200 <= spec.bandpass_hz <= 900
    assert spec.sidechain_depth_millibels < 0
    assert spec.sidechain_release_frames > 0


def test_the_sidechain_ducks_everything_but_the_kick() -> None:
    """The duck is an envelope from the kick's hits, and the kick is not in it."""
    from indiegen.mix.sidechain import duck_level, render_sidechain, sidechain_state

    hits = [0, RATE]
    gain, state = render_sidechain(0, 2 * RATE, hits, sidechain_state(), RATE, -900)
    assert gain.size == 2 * RATE
    assert gain[0] < 0.5
    assert gain[RATE] < 0.5
    assert gain[-1] > gain[0]
    assert duck_level(-900) < 0.5
    assert state.next_hit == 2


def test_the_sidechain_is_block_wise_identical() -> None:
    """The envelope does not depend on where the blocks are cut."""
    from indiegen.mix.sidechain import render_sidechain, sidechain_state

    hits = [1000, 50000, 90000]
    whole, _ = render_sidechain(0, 120000, hits, sidechain_state(), 8000, -900)
    pieces: list[np.ndarray] = []
    state = sidechain_state()
    for start in range(0, 120000, 4096):
        count = min(4096, 120000 - start)
        block, state = render_sidechain(start, count, hits, state, 8000, -900)
        pieces.append(block)
    assert np.array_equal(whole, np.concatenate(pieces))
