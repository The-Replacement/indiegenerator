"""c22 smoke tests: drum comp carry-state determinism and bypass bit-identity."""

from __future__ import annotations

import numpy as np

from indiegen.plan import DrumBusComp
from indiegen.render import render_plan
from indiegen.synth.drumcomp import drum_comp_state, render_drum_comp_block


def test_drum_comp_restart_from_state_bit_identical() -> None:
    comp = DrumBusComp(
        threshold_millibels=-600,
        ratio_permille=4000,
        attack_frames=10,
        release_frames=1000,
        makeup_millibels=0,
        mix_permille=1000,
    )
    rng = np.random.default_rng(1)
    sig = (rng.standard_normal((500, 2)) * 0.4).astype(np.float64)
    st = drum_comp_state()
    full, _ = render_drum_comp_block(sig, st, comp, 44100)
    st = drum_comp_state()
    o0, st0 = render_drum_comp_block(sig[:250], st, comp, 44100)
    o1, _ = render_drum_comp_block(sig[250:], st0, comp, 44100)
    split = np.concatenate([o0, o1], axis=0)
    assert np.array_equal(full, split)


def test_drum_comp_bypass_mix_zero_bit_identical_to_none() -> None:
    # mix_permille=0 bypasses; comp present with mix=0 must equal no comp.
    from indiegen.compose.director import director
    from indiegen.compose.planner import compose
    from indiegen.config import load_preset

    plan = director(compose(load_preset("motorik"), 1042, 5 * 44100))
    comp_bypass = DrumBusComp(
        threshold_millibels=-600,
        ratio_permille=4000,
        attack_frames=10,
        release_frames=1000,
        makeup_millibels=0,
        mix_permille=0,
    )
    plan_bypass = plan.model_copy(update={"drum_bus_comp": comp_bypass})
    plan_none = plan.model_copy(update={"drum_bus_comp": None})
    a = render_plan(plan_bypass)
    b = render_plan(plan_none)
    assert np.array_equal(a, b)
