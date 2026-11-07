"""c39: the tension walk, the corridor, and the level trim that buys it.

The model is the section-level reduction of Farbood's parametric tension
(weighted feature slopes, a memory window, beta=5 on agreeing slopes) with
the loudness slope as its strongest term. The corridor is the budget the
station declares per section; the trim is the actuator, because the material
alone moves a step by about thirty permille while the graph's paths span
three hundred.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director, tension
from indiegen.config import load_preset
from indiegen.errors import PlanError
from indiegen.plan import SAMPLE_RATE, Plan, SectionProfile

SEED = 1042


def _features(**values: int) -> tension.FeatureSet:
    base = {"loudness": -9000, "onset": 6000, "pitch": 5500, "roughness": 2000}
    base.update(values)
    return tension.FeatureSet(**base)


def test_a_step_with_no_change_is_zero() -> None:
    """The same material twice spends nothing."""
    row = _features()
    assert tension.step(row, row, {}) == (0, {"loudness": 0, "onset": 0, "pitch": 0, "roughness": 0})


def test_one_loudness_standard_deviation_is_twenty_permille() -> None:
    """The weights are permille of the scale and the step divisor is two."""
    previous = _features()
    current = _features(loudness=previous.loudness + tension.TENSION_FEATURE_STD["loudness"])
    value, _ = tension.step(current, previous, {})
    assert value == 400 * 100 // (tension.TENSION_STEP_SCALE * tension.TENSION_STEP_DIVISOR)


def test_a_repeated_direction_is_amplified_by_beta() -> None:
    """Farbood's memory window: agreement multiplies the slope by five."""
    previous = _features()
    current = _features(loudness=previous.loudness + tension.TENSION_FEATURE_STD["loudness"])
    once, signs = tension.step(current, previous, {})
    twice, _ = tension.step(current, previous, signs)
    assert twice == once * tension.TENSION_BETA


def test_the_walk_clips_and_starts_at_the_neutral_midpoint() -> None:
    """A walk cannot leave 0..1000 and the first section has no step."""
    rows = [_features() for _ in range(3)]
    values, steps, levels = tension.walk(rows, [-9000] * 3, [(0, 1000)] * 3)
    assert values[0] == tension.TENSION_START
    assert steps[0] == 0
    assert levels == [-9000] * 3
    loud = [_features(loudness=-9000 + index * tension.TENSION_FEATURE_STD["loudness"] * 20) for index in range(5)]
    values, _, _ = tension.walk(loud, [-9000] * 5, [(0, 1000)] * 5)
    assert all(0 <= value <= 1000 for value in values)


def test_a_declared_corridor_is_met_and_a_default_one_is_a_no_op() -> None:
    """The station's corridors hold for the canonical cells it was measured on."""
    for lane in ("motorik", "kosmische", "ambient"):
        preset = load_preset(lane)
        nodes = {node.function: node for node in preset.station.section_graph}
        for seed in (1042, 2000):
            plan = compose(preset, seed, 60 * SAMPLE_RATE)
            for section in plan.sections:
                node = nodes[section.function]
                assert node.tension_delta_min_permille <= section.tension_delta_permille
                assert section.tension_delta_permille <= node.tension_delta_max_permille
                assert section.tension_delta_min_permille == node.tension_delta_min_permille
                assert section.tension_delta_max_permille == node.tension_delta_max_permille


def test_an_unreachable_corridor_spends_nothing() -> None:
    """No candidate inside spends nothing: the declared level stands and the miss is recorded.

    The corridor is the plan's intent and #10 is its judge, so an unreachable
    one does not raise and does not trim to the nearest miss: the plan states
    the step it actually spent at the declared level.
    """
    preset = load_preset("motorik")
    graph = [
        node.model_copy(update={"tension_delta_min_permille": 200, "tension_delta_max_permille": 220})
        if node.function == "build"
        else node
        for node in preset.station.section_graph
    ]
    tight = preset.model_copy(update={"station": preset.station.model_copy(update={"section_graph": graph})})
    declared = next(node for node in preset.station.section_graph if node.function == "build")
    plan = compose(tight, SEED, 60 * SAMPLE_RATE)
    section = next(section for section in plan.sections if section.function == "build")
    assert section.level_millibels == declared.level_millibels
    assert not 200 <= section.tension_delta_permille <= 220


def test_solve_at_an_unreachable_corridor_returns_the_material_step_at_declared() -> None:
    """AC-1.1: the step is the material step at the declared level, not a trim."""
    previous = _features()
    material = _features()
    expected_delta, _ = tension.step(_features(loudness=-6000), previous, {})
    level, current, delta, _ = tension.solve(previous, 500, {}, material, -6000, 200, 220)
    assert level == -6000
    assert delta == expected_delta
    assert current == 500 + expected_delta
    assert not 200 <= delta <= 220


def test_solve_inside_trims_to_the_nearest_declared() -> None:
    """When a candidate lands inside, the trim still fires: nearest wins."""
    previous = _features()
    material = _features()
    # Declared -6000 spends 16, outside [17, 17]; -5900 spends 17 inside.
    level, _, delta, _ = tension.solve(previous, 500, {}, material, -6000, 17, 17)
    assert level == -5900
    assert delta == 17


def test_solve_tie_first_scan_wins() -> None:
    """Equidistant inside candidates: the lower, first-scanned one wins.

    Declared -28050 is not on the -30000 + 100k scan grid, so -28100 and
    -28000 are both 50 away and both inside [-1, 0]; the scan is ascending.
    """
    previous = _features(loudness=-28050)
    material = _features(loudness=-28050)
    level, _, delta, _ = tension.solve(previous, 500, {}, material, -28050, -1, 0)
    assert level == -28100
    assert delta == -1


def test_solve_empty_scan_returns_declared() -> None:
    """An inverted scan (declared above the ceiling) returns declared, not an error."""
    previous = _features()
    material = _features()
    expected_delta, _ = tension.step(_features(loudness=3000), previous, {})
    level, current, delta, _ = tension.solve(previous, 500, {}, material, 3000, -1000, 1000)
    assert level == 3000
    assert delta == expected_delta
    assert current == 500 + expected_delta


def test_a_corridor_orders_its_bounds() -> None:
    """A corridor whose minimum is above its maximum is not a corridor."""
    with pytest.raises(PlanError):
        SectionProfile(
            function="build",
            next=["outro"],
            density=55,
            level_millibels=-6000,
            bars=8,
            reprise_of="",
            transform="identity",
            texture="open",
            tension_delta_min_permille=40,
            tension_delta_max_permille=-40,
        )


def test_the_plan_records_the_walk_it_spent() -> None:
    """Every section carries a tension, a step and the corridor it aimed at."""
    plan = director(compose(load_preset("motorik"), SEED, 60 * SAMPLE_RATE))
    assert all(0 <= section.tension_permille <= 1000 for section in plan.sections)
    assert plan.sections[0].tension_delta_permille == 0
    assert all(-1000 <= section.tension_delta_permille <= 1000 for section in plan.sections)
    assert isinstance(plan, Plan)
