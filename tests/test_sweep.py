"""c28: the bounded seed sweep over the trajectory gates.

The committed suite pins one seed per lane (ambient 1042, motorik 1042), so a
gate failure that depends on the arrangement a seed draws is invisible until a
human watches a batch die. c27 was exactly that: 87 of 200 ambient seeds draw a
two-section plan, and seven of the ten rendered ones failed gate 5.

This sweep renders each lane at a few seeds and runs gates 4, 5, 6, 7 and 13 -
the gates that judge the arrangement against itself. It is marked ``sweep`` and
runs as its own CI job: it is minutes of rendering, and the default run should
not pay for it.

The seeds are chosen, not random: 1042 is the committed golden, 2000 and 4002
both drew a two-section ambient before c27-C widened the lane's section graph,
and every lane is rendered at each so a lane-specific failure cannot hide
behind a station blend.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.master.chain import master
from indiegen.plan import Plan
from indiegen.render import BLOCK_SIZE, render_plan
from indiegen.validate import (
    GateResult,
    check_gate_4,
    check_gate_5,
    check_gate_6,
    check_gate_7,
    check_gate_13,
)

LANES: tuple[str, ...] = ("motorik", "kosmische", "dub-electronic", "indie-noise", "ambient")
SEEDS: tuple[int, ...] = (1042, 2000, 4002)
SWEEP_SECONDS: int = 240
RATE: int = 44100


def _cases() -> list[tuple[str, int]]:
    return [(lane, seed) for lane in LANES for seed in SEEDS]


def _describe(failures: list[GateResult]) -> str:
    return "; ".join(f"gate {f.gate}: {f.check}: measured {f.measured:.4f} limit {f.limit:.4f}" for f in failures)


@pytest.mark.sweep
@pytest.mark.parametrize(("lane", "seed"), _cases())
def test_lane_seed_renders_the_trajectory_gates(lane: str, seed: int) -> None:
    plan: Plan = director(compose(load_preset(lane), seed, SWEEP_SECONDS * RATE))
    mix = render_plan(plan)
    pcm = master(plan, mix, BLOCK_SIZE)

    failures: list[GateResult] = []
    failures += check_gate_4(plan, pcm)
    failures += check_gate_5(plan, mix)
    failures += check_gate_6(plan, mix)
    failures += check_gate_7(plan, pcm, plan.sample_rate)
    failures += check_gate_13(plan)

    assert not failures, _describe(failures)
