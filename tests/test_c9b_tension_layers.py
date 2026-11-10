"""c9b tension layers (issue #9b Commit2 T6-T8, T12-T13): admission units.

Fast, compose-only tests: admission vectors, RNG snapshot, preset parse,
bed invariant and the bool-flip consumption proof. No renders.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.compose.context import TechniqueContext
from indiegen.compose.planner import CARD_SPECS, _admission_mode
from indiegen.compose.rng import SplitMix64
from indiegen.config import load_preset
from indiegen.errors import PlanError
from indiegen.plan import SAMPLE_RATE, canonical_json


def _ctx(
    enabled: bool = True,
    modes: list[str] | None = None,
    bed: list[str] | None = None,
    densities: list[int] | None = None,
) -> TechniqueContext:
    densities = [20, 55, 80, 25, 95] if densities is None else densities
    modes = ["density"] * len(densities) if modes is None else list(modes)
    return TechniqueContext(
        preset="motorik",
        seed=1042,
        lane="motorik",
        scale_midi=[60, 62, 64],
        root_midi=60,
        sample_rate=SAMPLE_RATE,
        duration_frames=4 * SAMPLE_RATE,
        frames_per_beat=SAMPLE_RATE,
        frames_per_bar=4 * SAMPLE_RATE,
        attack_frames=0,
        release_frames=0,
        section_boundaries=[i * SAMPLE_RATE for i in range(len(densities) + 1)],
        section_densities=densities,
        section_scales=[[60, 62, 64] for _ in densities],
        section_roots=[60] * len(densities),
        section_functions=["intro", "build", "plateau", "outro", "peak"][: len(densities)],
        tension_admission_enabled=enabled,
        section_admission_modes=modes,
        bed_instruments=["pad"] if bed is None else list(bed),
    )


@pytest.mark.parametrize(
    ("tension", "mode"),
    [
        (420, "all"),
        (421, "all"),
        (422, "density"),
        (449, "density"),
        (450, "density"),
        (451, "density"),
        (549, "density"),
        (550, "density"),
        (551, "density"),
        (500, "density"),
        (0, "all"),
        (1000, "density"),
    ],
)
def test_admission_mode_vectors(tension: int, mode: str) -> None:
    """Sparse (low tension/fullness, #38) admits all; others defer to density."""
    assert _admission_mode(tension) == mode


def test_first_section_500_is_density() -> None:
    assert _admission_mode(500) == "density"


def test_admits_off_falls_back_to_density() -> None:
    ctx = _ctx(enabled=False, modes=["all", "all", "all", "all", "all"], bed=["pad"])
    assert ctx.admits(0, "hat", density=20, min_density=70) is False
    assert ctx.admits(0, "hat", density=80, min_density=70) is True


def test_admits_no_modes_falls_back_to_density() -> None:
    ctx = _ctx(enabled=True, modes=[], bed=["pad"])
    assert ctx.admits(0, "hat", density=20, min_density=70) is False
    assert ctx.admits(0, "hat", density=80, min_density=70) is True


def test_admits_all_ignores_density() -> None:
    ctx = _ctx(modes=["all"])
    assert ctx.admits(0, "hat", density=20, min_density=70) is True


def test_admits_density_uses_density() -> None:
    ctx = _ctx(modes=["density"])
    assert ctx.admits(0, "hat", density=20, min_density=70) is False
    assert ctx.admits(0, "hat", density=80, min_density=70) is True


def test_admits_bed_keeps_bed_strips_others() -> None:
    ctx = _ctx(modes=["bed"], bed=["pad"])
    assert ctx.admits(0, "pad", density=20, min_density=0) is True
    assert ctx.admits(0, "kick", density=20, min_density=0) is False
    assert ctx.admits(0, "snare", density=80, min_density=40) is False


def test_admits_empty_bed_falls_back_to_density() -> None:
    ctx = _ctx(modes=["bed"], bed=[])
    assert ctx.admits(0, "hat", density=80, min_density=70) is True
    assert ctx.admits(0, "hat", density=20, min_density=70) is False


def test_admits_unknown_mode_raises() -> None:
    ctx = _ctx(modes=["bogus"])
    with pytest.raises(PlanError):
        ctx.admits(0, "pad", density=80, min_density=0)


def test_snapshot_restore_draw_identity() -> None:
    rng = SplitMix64(12345)
    _ = [rng.next_u64() for _ in range(5)]
    snap = rng.snapshot()
    first = [rng.next_u64() for _ in range(10)]
    rng.restore(snap)
    second = [rng.next_u64() for _ in range(10)]
    assert first == second
    assert isinstance(snap, int)


def test_parse_admission_flag_enabled_on_pitched_lanes() -> None:
    """Admission is active on the four pitched lanes; ambient stays off."""
    for lane in ("motorik", "kosmische", "dub-electronic", "indie-noise"):
        assert load_preset(lane).lanes[0].parameters.tension_admission_enabled is True
    assert load_preset("ambient").lanes[0].parameters.tension_admission_enabled is False


def test_bed_is_pad_and_drone_only() -> None:
    bed_kinds = {kind for kind, spec in CARD_SPECS.items() if spec.bed}
    assert bed_kinds == {"pad", "drone"}
    bed_instruments = {spec.instrument for spec in CARD_SPECS.values() if spec.bed}
    assert bed_instruments == {"pad", "drone"}


def test_bool_flip_changes_plan_where_threshold_hits() -> None:
    """Admission consumes the bool and changes the plan where a section is sparse.

    kosmische 60 s 1042 outro has pass1 T=420 (<=421, #38 fullness-shaped) so it
    admits all layers when enabled. The lane preset keeps admission off by
    default; the mechanism is exercised by forcing the flag on.
    """
    base = load_preset("kosmische")
    entry = base.lanes[0]

    def _with_flag(flag: bool) -> object:
        return base.model_copy(
            update={
                "lanes": [
                    type(entry)(
                        lane=entry.lane,
                        weight=entry.weight,
                        parameters=entry.parameters.model_copy(update={"tension_admission_enabled": flag}),
                    )
                ]
            }
        )

    plan_on = director(compose(_with_flag(True), 1042, 60 * SAMPLE_RATE))
    plan_off = director(compose(_with_flag(False), 1042, 60 * SAMPLE_RATE))
    assert canonical_json(plan_on) != canonical_json(plan_off)
    outro_on = next(section for section in plan_on.sections if section.function == "outro")
    outro_off = next(section for section in plan_off.sections if section.function == "outro")
    assert "lead" not in outro_off.instrumentation
    assert "lead" in outro_on.instrumentation
    assert (
        outro_on.tension_permille != outro_off.tension_permille or outro_on.instrumentation != outro_off.instrumentation
    )


def test_lead_entry_is_retained_under_all() -> None:
    """Lead never appears before its entry section, even under all-admission."""
    plan = director(compose(load_preset("kosmische"), 1042, 60 * SAMPLE_RATE))
    for section in plan.sections:
        if section.index < 3:
            assert "lead" not in section.instrumentation
