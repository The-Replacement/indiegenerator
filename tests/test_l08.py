"""L08 (graduated spike): grace/anticipation ornament events.

Spike evidence (/tmp/opencode/spike_l08.py): 11 grace events emitted,
gate 6 PASS, event budget OK, determinism stable. These tests pin the
landed mechanism: default no-op, plan-log exactness of the offset, and
deterministic re-composition.
"""

from __future__ import annotations

from indiegen.compose.director import director
from indiegen.compose.planner import _ornament_events, compose
from indiegen.config import load_preset
from indiegen.plan import PluckEvent


def _ambient():
    return director(compose(load_preset("motorik"), 1042, 60 * 44100))


def test_ornament_zero_is_no_op() -> None:
    plan = _ambient()
    assert _ornament_events(list(plan.events), plan.sections, 1042, 0, 500) == list(plan.events)


def _boundaries(plan):
    return [s.start_frame for s in plan.sections] + [plan.duration_frames]


def test_ornament_emits_grace_events_when_active() -> None:
    plan = _ambient()
    grace = 500
    b = _boundaries(plan)
    out = _ornament_events(list(plan.events), b, 1042, 200, grace)
    graces = out[len(plan.events) :]
    assert len(graces) >= 1
    hosts = {p.start_frame for p in plan.events if isinstance(p, PluckEvent)}
    for g in graces:
        assert g.duration_frames == grace
        assert g.start_frame >= 0
        assert g.start_frame + g.duration_frames in hosts


def test_ornament_is_deterministic() -> None:
    plan = _ambient()
    b = _boundaries(plan)
    a = _ornament_events(list(plan.events), b, 1042, 200, 500)
    bb = _ornament_events(list(plan.events), b, 1042, 200, 500)
    assert a == bb


def test_ornament_zero_default_keeps_golden() -> None:
    plan = _ambient()
    assert plan.ornament_permille == 0
    assert plan.grace_offset_frames == 0
