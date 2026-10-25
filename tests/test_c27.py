"""c27: gate 5 does not fail a static plan for being static.

Gate 5 correlates the delivered per-second RMS with the plan's section level
curve. A plan whose whole curve spans less than the static threshold is exempt:
a sparse section's RMS swings for reasons that say nothing about the
arrangement (BRIEF 11: "a section the plan marked static must not be failed for
being static").

The exemption used to be exercised by the ambient lane, which could draw a
two-section intro -> outro plan with 0.2 dB of shape and passed the gate only
because of it. c27-C asked for a real arc instead, and the ambient lane now
runs 3-4 sections with 8-9 dB of it: the lane is the case the gate has to
CORRELATE, and the exemption is pinned here on plans built for it - at the
threshold, one millibel under it, and one millibel over it.

The mixes below are as long as the plan. A two-second mix correlates at exactly
+-1.0 by arithmetic, so a test that fed one could not fail whatever the gate
did, and the loosened version of this file passed for that reason alone.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import Plan
from indiegen.render import render_plan
from indiegen.validate import (
    STATIC_CENTROID_TOLERANCE,
    STATIC_LEVEL_SPREAD_MILLIBELS,
    check_gate_6,
    energy_correlation,
    timbre_measurement,
    timbre_ok,
)

RATE = 44100
AMBIENT_SECONDS = 90
AMBIENT_CENTROID_HZ = 560

# BRIEF 11: "4-8 sections per track (ambient 2-4)".
AMBIENT_SECTIONS = (2, 4)


def _falling_mix(plan: Plan) -> np.ndarray:
    """A mix whose energy falls while the plan's section levels rise.

    The plan under test rises and this signal falls, so a correlation of 1.0
    can only mean the static exemption fired: without it the same pair
    measures negative, which is what the over-threshold test asserts.
    """
    envelope = np.linspace(1.0, 0.0, plan.duration_frames, dtype=np.float64)
    return np.repeat(envelope[:, np.newaxis], 2, axis=1)


def _ambient(seed: int, seconds: int = AMBIENT_SECONDS) -> Plan:
    return compose(load_preset("ambient"), seed, seconds * RATE)


def _short_plan() -> Plan:
    """A five-section, sixty-second plan: short sections span the mix."""
    plan = compose(load_preset("motorik"), 1042, 60 * RATE)
    assert len(plan.sections) == 5
    return plan


def _with_levels(plan: Plan, levels: list[int]) -> Plan:
    sections = [
        section.model_copy(update={"level_millibels": level})
        for section, level in zip(plan.sections, levels, strict=True)
    ]
    return plan.model_copy(update={"sections": sections})


def _spread(plan: Plan) -> int:
    levels = [section.level_millibels for section in plan.sections]
    return max(levels) - min(levels)


def test_a_plan_at_the_declared_spread_is_static() -> None:
    """The threshold is inclusive: a spread equal to it is still static."""
    plan = _with_levels(_short_plan(), [-12000, -10500, -10000, -9500, -9000])
    assert _spread(plan) == STATIC_LEVEL_SPREAD_MILLIBELS
    assert energy_correlation(plan, _falling_mix(plan)) == 1.0


def test_a_plan_under_the_declared_spread_is_static() -> None:
    plan = _with_levels(_short_plan(), [-12000, -10750, -10500, -10250, -10000])
    assert _spread(plan) == 2000
    assert energy_correlation(plan, _falling_mix(plan)) == 1.0


def test_one_millibel_over_the_declared_spread_is_not_exempt() -> None:
    """One millibel past the threshold and the plan is measured like any other."""
    plan = _with_levels(_short_plan(), [-12000, -10500, -10000, -9500, -8999])
    assert _spread(plan) == STATIC_LEVEL_SPREAD_MILLIBELS + 1
    assert energy_correlation(plan, _falling_mix(plan)) < 0.0


def test_a_moving_plan_against_a_falling_mix_fails() -> None:
    moving = _with_levels(_short_plan(), [-14000, -12000, -10000, -8000, -6000])
    assert _spread(moving) > STATIC_LEVEL_SPREAD_MILLIBELS
    assert energy_correlation(moving, _falling_mix(moving)) < 0.0


@pytest.mark.parametrize(("seed", "sections", "spread"), [(1042, 4, 9000), (2000, 3, 8000), (3005, 4, 9000)])
def test_the_ambient_builds_a_real_arc(seed: int, sections: int, spread: int) -> None:
    """c27-C: the ambient no longer leans on the exemption.

    The lane used to draw a two-section plan with 0.2 dB of shape. It now
    declares a section graph of its own, so the arc is pinned here at the
    measured numbers and the spread is asserted to be above the threshold -
    the lane is the case the gate has to correlate, not the case it exempts.
    """
    plan = _ambient(seed)
    assert len(plan.sections) == sections
    assert AMBIENT_SECTIONS[0] <= len(plan.sections) <= AMBIENT_SECTIONS[1]
    assert _spread(plan) == spread
    assert _spread(plan) > STATIC_LEVEL_SPREAD_MILLIBELS


def test_the_ambient_arc_does_not_depend_on_the_duration() -> None:
    for seed, sections, spread in ((1042, 4, 9000), (2000, 3, 8000)):
        for seconds in (240, 480):
            plan = _ambient(seed, seconds)
            assert len(plan.sections) == sections
            assert _spread(plan) == spread


def test_the_directed_plan_is_what_gate_five_sees() -> None:
    """The Director may rewrite sections, and the gate reads what it wrote."""
    plan = _ambient(1042)
    directed = director(plan)
    assert [s.level_millibels for s in directed.sections] == [s.level_millibels for s in plan.sections]
    assert _spread(directed) > STATIC_LEVEL_SPREAD_MILLIBELS


def test_the_ambient_declares_a_flat_timbre() -> None:
    """c27-C: the flat table is the lane's declaration, not an oversight.

    The lane predicts no timbre arc, so every function declares the same
    centroid and gate 6 has to take its static branch. The measured reason
    is in the preset: the delivered per-section centroid moves with the
    track's duration, so a per-function table fitted at one duration does
    not hold at another.
    """
    plan = _ambient(1042)
    centroids = [section.centroid_hz for section in plan.sections]
    assert len(set(centroids)) == 1
    assert centroids[0] == AMBIENT_CENTROID_HZ
    planned = np.array(centroids, dtype=np.float64)
    assert planned.max() - planned.min() <= STATIC_CENTROID_TOLERANCE * planned.mean()


@pytest.mark.slow
def test_the_ambient_passes_gate_six_by_variance() -> None:
    """The declaration is what the gate actually measures on a real render."""
    plan = _ambient(1042)
    mix = render_plan(plan)
    measured, static = timbre_measurement(plan, mix)
    assert static == 1.0
    assert timbre_ok(measured, True)
    assert check_gate_6(plan, mix) == []
