"""Flag-ON gate sweep for the CP harmonic progression (issue #12 slice 3).

Mirrors ``test_sweep_geodesic.py`` but enables ``harmony_cp_enabled`` on the
station model, so the arrangement-specific risk of CP-solved roots is exercised
across lanes.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.config import Preset, load_preset
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
SEEDS: tuple[int, ...] = (1042,)
SWEEP_SECONDS: int = 240
RATE: int = 44100


def _cases() -> list[tuple[str, int]]:
    return [(lane, seed) for lane in LANES for seed in SEEDS]


def _describe(failures: list[GateResult]) -> str:
    return "; ".join(f"gate {f.gate}: {f.check}: measured {f.measured:.4f} limit {f.limit:.4f}" for f in failures)


def _enabled_preset(lane: str) -> Preset:
    preset = load_preset(lane)
    return preset.model_copy(update={"station": preset.station.model_copy(update={"harmony_cp_enabled": True})})


@pytest.mark.sweep
@pytest.mark.parametrize(("lane", "seed"), _cases())
def test_lane_seed_renders_the_trajectory_gates_harmony_cp(lane: str, seed: int) -> None:
    plan: Plan = director(compose(_enabled_preset(lane), seed, SWEEP_SECONDS * RATE))
    mix = render_plan(plan)
    pcm = master(plan, mix, BLOCK_SIZE)

    failures: list[GateResult] = []
    failures += check_gate_4(plan, pcm)
    failures += check_gate_5(plan, mix)
    failures += check_gate_6(plan, mix)
    failures += check_gate_7(plan, pcm, plan.sample_rate)
    failures += check_gate_13(plan)

    assert not failures, _describe(failures)
