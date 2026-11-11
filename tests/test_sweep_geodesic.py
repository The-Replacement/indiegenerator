"""Flag-ON gate sweep for the geodesic voice-leading pass (issue #13 follow-up).

Mirrors ``test_sweep.py`` but enables ``geodesic_voice_leading`` on the station
model, so the arrangement-specific risk of the geodesic walk (quantising
plucks to chord tones and snapping the bass to section roots) is exercised
across lanes. Only the committed golden seed (1042) is used per lane to keep
the sweep CI-friendly; the verifier already confirmed 5 lanes x 3 seeds
flag-ON with 0 gate failures. Marked ``sweep`` and runs in the same CI job
as the flag-OFF sweep.
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
SEEDS: tuple[int, ...] = (1042,)
SWEEP_SECONDS: int = 240
RATE: int = 44100


def _cases() -> list[tuple[str, int]]:
    return [(lane, seed) for lane in LANES for seed in SEEDS]


def _describe(failures: list[GateResult]) -> str:
    return "; ".join(f"gate {f.gate}: {f.check}: measured {f.measured:.4f} limit {f.limit:.4f}" for f in failures)


def _enabled_preset(lane: str):
    preset = load_preset(lane)
    return preset.model_copy(update={"station": preset.station.model_copy(update={"geodesic_voice_leading": True})})


@pytest.mark.sweep
@pytest.mark.parametrize(("lane", "seed"), _cases())
def test_lane_seed_renders_the_trajectory_gates_geodesic(lane: str, seed: int) -> None:
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
