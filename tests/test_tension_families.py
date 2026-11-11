"""Offline tests for tension-selected layer families (issue #39 evidence slice)."""

from __future__ import annotations

from indiegen.compose.context import (
    HIGH_TENSION_INSTRUMENTS,
    LOW_TENSION_INSTRUMENTS,
)
from indiegen.compose.planner import _admission_mode


def test_high_mode_resolves() -> None:
    assert _admission_mode(800, rule="highlow") == "high"
    assert _admission_mode(200, rule="highlow") == "low"
    assert _admission_mode(500, rule="highlow") == "density"


def test_current_rule_preserves_behavior() -> None:
    assert _admission_mode(300) == "all"
    assert _admission_mode(500) == "density"


def test_families_disjoint() -> None:
    assert not (HIGH_TENSION_INSTRUMENTS & LOW_TENSION_INSTRUMENTS)


def test_spice_mapped() -> None:
    # spice is mapped onto an existing instrument kind
    assert "pluck" in HIGH_TENSION_INSTRUMENTS or "lead" in HIGH_TENSION_INSTRUMENTS
