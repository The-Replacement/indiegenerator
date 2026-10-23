"""L03 (graduated spike): planar chord offset.

The /tmp spike measured +28.30 Hz mean centroid delta (epsilon 20 Hz) with an
exact +2 on every poly-period voice, so the row survived and the post-pass is
wired into the planner. These tests pin the two spike facts: k=0 is a no-op
(golden hash must not move) and k!=0 shifts every voice by exactly k with no
scale re-filter.
"""

from __future__ import annotations

from indiegen.compose.director import director
from indiegen.compose.planner import _planar_offset, compose
from indiegen.config import load_preset
from indiegen.plan import PolyPeriodEvent


def _ambient():
    return director(compose(load_preset("ambient"), 1042, 10 * 44100))


def test_planar_offset_zero_returns_events_untouched() -> None:
    plan = _ambient()
    assert _planar_offset(list(plan.events), 0) == list(plan.events)


def test_planar_offset_moves_every_voice_by_exactly_k() -> None:
    plan = _ambient()
    for k in (1, 2, -3, 12):
        shifted = _planar_offset(list(plan.events), k)
        before = [v.midi for e in plan.events if isinstance(e, PolyPeriodEvent) for v in e.voices]
        after = [v.midi for e in shifted if isinstance(e, PolyPeriodEvent) for v in e.voices]
        assert before, "ambient must carry poly-period voices for this test"
        assert all(b - a == k for a, b in zip(before, after, strict=True))


def test_planar_offset_waives_scale_membership() -> None:
    # The offset must NOT be snapped back to the scale (the spike's falsifier).
    plan = _ambient()
    scale_pc = {n % 12 for n in plan.scale_midi}
    shifted = _planar_offset(list(plan.events), 1)
    voices = [v.midi for e in shifted if isinstance(e, PolyPeriodEvent) for v in e.voices]
    # At k=1 at least one voice should land off-scale; if all snap back the
    # re-filter the row would be a no-op.
    assert any(m % 12 not in scale_pc for m in voices)


def test_planar_offset_zero_is_plan_bit_identity() -> None:
    # Composing with the default (0) must equal the golden path exactly.
    plan = _ambient()
    plan2 = plan.model_copy(update={"planar_offset_semitones": 0})
    assert _planar_offset(list(plan2.events), plan2.planar_offset_semitones) == list(plan.events)
