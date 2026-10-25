"""c27: gate 5 does not fail a static plan for being static.

The two-section ambient (intro -> outro) spans exactly 2000 millibels, and
the delivered per-second RMS of a sparse sixteen-minute section swings by
far more than that for reasons that are not the arrangement. Gate 5 now
treats a planned level spread at or under 3000 millibels as static, the way
gate 6 already treats a static timbre, and only correlates a curve that
actually moves.
"""

from __future__ import annotations

import numpy as np

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import Plan
from indiegen.validate import STATIC_LEVEL_SPREAD_MILLIBELS, energy_correlation

RATE = 44100
AMBIENT_SECONDS = 480


def _noise_mix(seconds: int) -> np.ndarray:
    return np.random.default_rng(0).standard_normal((seconds * RATE, 2))


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


def test_the_two_section_ambient_is_static() -> None:
    plan = _ambient(2000)
    assert len(plan.sections) >= 2
    levels = [section.level_millibels for section in plan.sections]
    assert max(levels) - min(levels) >= 2000
    assert energy_correlation(plan, _noise_mix(2)) == 1.0


def test_the_other_failing_seed_is_static_too() -> None:
    plan = _ambient(3005)
    assert len(plan.sections) >= 2
    assert energy_correlation(plan, _noise_mix(2)) == 1.0


def test_the_boundary_is_the_declared_spread() -> None:
    plan = _short_plan()
    at_floor = _with_levels(plan, [-12000, -9000, -12000, -9000, -12000])
    assert (
        max(s.level_millibels for s in at_floor.sections) - min(s.level_millibels for s in at_floor.sections)
        == STATIC_LEVEL_SPREAD_MILLIBELS
    )
    assert energy_correlation(at_floor, _noise_mix(60)) == 1.0

    over_floor = _with_levels(plan, [-12000, -8990, -12000, -9000, -12000])
    assert energy_correlation(over_floor, _noise_mix(60)) != 1.0


def test_a_moving_plan_is_still_correlated() -> None:
    moving = _with_levels(_short_plan(), [-14000, -12000, -10000, -8000, -6000])
    # A signal whose energy falls while the plan rises: the gate must see
    # the disagreement, not the static exemption.
    envelope = np.linspace(1.0, 0.0, 60 * RATE)
    mix = np.repeat(envelope[:, np.newaxis], 2, axis=1)
    assert energy_correlation(moving, mix) < 0.0


def test_a_normal_ambient_is_not_exempt() -> None:
    plan = _ambient(1042)
    assert len(plan.sections) >= 3
    levels = [section.level_millibels for section in plan.sections]
    assert max(levels) - min(levels) > STATIC_LEVEL_SPREAD_MILLIBELS


def test_the_exemption_is_duration_independent() -> None:
    for seed in (2000, 3005):
        plan = _ambient(seed, seconds=240)
        assert len(plan.sections) >= 2
        assert energy_correlation(plan, _noise_mix(2)) == 1.0


def test_the_directed_plan_is_what_gate_five_sees() -> None:
    plan = director(_ambient(2000))
    assert energy_correlation(plan, _noise_mix(2)) == 1.0
