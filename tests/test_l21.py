"""L21 (wired): pre-limiter saturation stage.

Default mix=0 is a no-op (bit-identity, covered by ambient golden). This test
pins the bypass contract and the stage's existence on the Plan.
"""

from __future__ import annotations

import numpy as np

from indiegen.compose.director import director
from indiegen.compose.planner import compose
from indiegen.config import load_preset
from indiegen.master.chain import master


def _plan():
    return director(compose(load_preset("motorik"), 1042, 5 * 44100))


def test_saturation_default_is_zero() -> None:
    plan = _plan()
    assert plan.saturation_drive_millibels == 0
    assert plan.saturation_mix_permille == 0


def test_saturation_mix_zero_is_bit_identical() -> None:
    plan = _plan()
    mix = np.zeros((1024, 2), dtype=np.float64)
    a = master(plan, mix, 8192)
    plan2 = plan.model_copy(update={"saturation_drive_millibels": 1200, "saturation_mix_permille": 0})
    b = master(plan2, mix, 8192)
    assert np.array_equal(a, b)


def test_saturation_mix_nonzero_runs_and_is_finite() -> None:
    plan = _plan()
    plan2 = plan.model_copy(update={"saturation_drive_millibels": 1200, "saturation_mix_permille": 500})
    mix = (np.random.default_rng(0).standard_normal((4096, 2)) * 0.3).astype(np.float64)
    out = master(plan2, mix, 8192)
    assert np.all(np.isfinite(out))
    assert not np.array_equal(out, master(plan, mix, 8192))
