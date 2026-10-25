"""L16 (graduated spike): micro-offset doubling.

Spike evidence (/tmp/opencode/spike_l16.py): null at ~441 Hz with -43 dB
depth inside 40-800 Hz (offset 50 frames) - row survives. These tests pin
the landed mechanism: default no-op, comb-null property, and the event-count
budget.
"""

from __future__ import annotations

from indiegen.compose.director import director
from indiegen.compose.planner import _double_events, compose
from indiegen.config import load_preset
from indiegen.plan import Plan


def _ambient() -> Plan:
    return director(compose(load_preset("ambient"), 1042, 10 * 44100))


def test_double_zero_is_no_op() -> None:
    plan = _ambient()
    assert _double_events(list(plan.events), 0, 5, plan.duration_frames) == list(plan.events)


def test_double_clones_events_shifted_by_offset() -> None:
    plan = _ambient()
    copies = 2
    offset = 7
    out = _double_events(list(plan.events), copies, offset, plan.duration_frames)
    assert len(out) == len(plan.events) * (copies + 1)
    # each clone's start is exactly a multiple of offset past an original
    originals = {e.start_frame for e in plan.events}
    for e in out[len(plan.events) :]:
        assert (e.start_frame - offset) in originals or (e.start_frame - 2 * offset) in originals


def test_double_drops_clones_past_track_end() -> None:
    plan = _ambient()
    out = _double_events(list(plan.events), 1, plan.duration_frames - 1, plan.duration_frames)
    # only events starting at 0 (or very early) can be cloned without exceeding
    assert len(out) <= len(plan.events) + sum(1 for e in plan.events if e.start_frame == 0)


def test_double_consistency_validator() -> None:
    plan = _ambient()
    import pytest

    from indiegen.errors import PlanError

    with pytest.raises(PlanError):
        plan.model_validate({**plan.model_dump(), "double_copies": 2, "double_offset_frames": 0})
    with pytest.raises(PlanError):
        plan.model_validate({**plan.model_dump(), "double_copies": 0, "double_offset_frames": 5})


def test_default_presets_declare_no_doubling() -> None:
    plan = _ambient()
    assert plan.double_copies == 0
    assert plan.double_offset_frames == 0
