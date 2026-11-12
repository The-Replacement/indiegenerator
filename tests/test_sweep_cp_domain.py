"""Flag-ON gate sweep for the CP domain consonance variants (issue #17 item 1).

Mirrors ``test_sweep_harmony_cp.py`` but adds the variant dimension, using the
in-memory patched planners from ``tools.cp_domain_variants``. Marked ``sweep``.
"""

from __future__ import annotations

import pytest
from tools.cp_domain_variants import GATE_SEEDS_DEFAULT, VARIANTS, run_cell

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
SEEDS: tuple[int, ...] = GATE_SEEDS_DEFAULT
SWEEP_SECONDS: int = 240
RATE: int = 44100


def _cases() -> list[tuple[str, str, int]]:
    return [(variant, lane, seed) for variant in VARIANTS for lane in LANES for seed in SEEDS]


def _describe(failures: list[GateResult]) -> str:
    return "; ".join(f"gate {f.gate}: {f.check}: measured {f.measured:.4f} limit {f.limit:.4f}" for f in failures)


def _enabled_preset(lane: str) -> Preset:
    preset = load_preset(lane)
    return preset.model_copy(
        update={
            "station": preset.station.model_copy(
                update={"harmony_cp_enabled": True, "consonance_scoring_enabled": True}
            )
        }
    )


@pytest.mark.sweep
@pytest.mark.parametrize(("variant", "lane", "seed"), _cases())
def test_variant_lane_seed_renders_the_trajectory_gates(variant: str, lane: str, seed: int) -> None:
    preset = _enabled_preset(lane)
    plan: Plan
    plan, _domain = run_cell(preset, seed, SWEEP_SECONDS * RATE, variant)
    mix = render_plan(plan)
    pcm = master(plan, mix, BLOCK_SIZE)

    failures: list[GateResult] = []
    failures += check_gate_4(plan, pcm)
    failures += check_gate_5(plan, mix)
    failures += check_gate_6(plan, mix)
    failures += check_gate_7(plan, pcm, plan.sample_rate)
    failures += check_gate_13(plan)

    assert not failures, _describe(failures)
