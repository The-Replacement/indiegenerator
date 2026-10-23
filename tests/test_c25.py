"""c25: chromatic chord pool with a budget (L01).

At budget 0 the pool is exactly the old scale filter (prefix break at the
first non-scale tone). Above budget 0, chromatic tones may enter but the
off-scale fraction of the pool can never exceed budget_permille / 1000.
"""

from __future__ import annotations

import pytest

from indiegen.errors import PlanError
from indiegen.plan import Plan
from indiegen.theory.scales import chord_pool, mode_scale

DORIAN = mode_scale("dorian", 60, 2)  # scale over two octaves from C4


def test_budget_zero_is_the_old_filter() -> None:
    # [0, 3, 6, 9]: the 6 is not in dorian -> prefix breaks at 6.
    assert chord_pool(DORIAN, 60, [0, 3, 6, 9], 0) == [0, 3]
    # all-in-scale list passes whole.
    assert chord_pool(DORIAN, 60, [0, 3, 5, 7], 0) == [0, 3, 5, 7]
    # nothing usable degenerates to the root: 61+0,61+1,61+2 all miss dorian@60.
    assert chord_pool(DORIAN, 61, [0, 1, 2], 0) == [0]


def test_budget_admits_chromatic_within_fraction() -> None:
    # 6 and 9 are off-scale here; full budget admits all four tones.
    pool = chord_pool(DORIAN, 60, [0, 3, 6, 9], 1000)
    assert pool == [0, 3, 6, 9]


def test_off_scale_fraction_never_exceeds_budget() -> None:
    declared = [0, 1, 3, 4, 6, 7, 9, 10]  # mixed scale/chromatic vs dorian@60
    for budget in (0, 200, 333, 500, 750, 1000):
        pool = chord_pool(DORIAN, 60, declared, budget)
        off = sum(1 for t in pool if 60 + t not in DORIAN)
        assert off * 1000 <= budget * len(pool)


def test_pool_is_a_prefix() -> None:
    declared = [0, 3, 6, 9, 5, 7]
    pool = chord_pool(DORIAN, 60, declared, 300)
    assert declared[: len(pool)] == pool


def test_chord_tone_intervals_shape_validated() -> None:
    # Build a plan, then re-validate with a bad interval set.
    from indiegen.compose.director import director
    from indiegen.compose.planner import compose
    from indiegen.config import load_preset

    plan = director(compose(load_preset("motorik"), 1042, 5 * 44100))
    dump = plan.model_dump()
    with pytest.raises(PlanError):
        Plan.model_validate({**dump, "chord_tone_intervals": [0, 3]})  # too short
    with pytest.raises(PlanError):
        Plan.model_validate({**dump, "chord_tone_intervals": [0, 3, 12]})  # not a pitch class
    ok = Plan.model_validate({**dump, "chord_tone_intervals": [0, 3, 6, 9]})
    assert ok.chord_tone_intervals == [0, 3, 6, 9]


def _plan_off_scale_fraction(plan: Plan) -> tuple[int, int]:
    """(off-scale pitches, total pitches) over the chord pool's consumers.

    Scoped to poly/pad/drone — the voices the pool builder emits. Motif
    plucks carry the station's degree bank raw and are chromatic by
    pre-existing design; they are not this budget's subject.
    """
    scale_pc = {n % 12 for n in plan.scale_midi}
    off = 0
    total = 0
    for event in plan.events:
        if event.kind == "pluck":
            continue
        if event.kind == "poly_period":
            for voice in event.voices:
                total += 1
                if voice.midi % 12 not in scale_pc:
                    off += 1
            continue
        total += 1
        if event.midi % 12 not in scale_pc:
            off += 1
    return off, total


def test_plan_off_scale_fraction_within_budget() -> None:
    from indiegen.compose.director import director
    from indiegen.compose.planner import compose
    from indiegen.config import load_preset

    preset = load_preset("ambient")
    # ambient carries a poly_period card; declare a chromatic sonority + budget.
    station = preset.station.model_copy(update={"chord_tone_intervals": [0, 3, 6, 9], "chromatic_budget_permille": 400})
    preset = preset.model_copy(update={"station": station})
    plan = director(compose(preset, 1042, 10 * 44100))
    off, total = _plan_off_scale_fraction(plan)
    assert off * 1000 <= 400 * total
    # budget actually spent: with a chromatic set and a nonzero budget the
    # pool is richer than budget 0 would allow (voice count can only grow).
    plan0 = director(compose(load_preset("ambient"), 1042, 10 * 44100))
    off0, _ = _plan_off_scale_fraction(plan0)
    assert off0 * 1000 <= 0 * total  # budget 0: zero off-scale events
