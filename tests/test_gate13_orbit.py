"""c14: gate 13's transformed-appearance count must not move.

The orbit changes WHICH canonical element a statement wears, never WHETHER it
wears one. These counts were measured from the HEAD worktree (4937c5c) with a
PYTHONPATH override for the same five lanes at 45 s, seed 1042; the working
tree must reproduce them exactly and gate 13 must stay green.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.validate import MINIMUM_TRANSFORMED_APPEARANCES, check_gate_13

# (lane, transformed appearances) measured at HEAD for seed 1042 @ 45 s.
HEAD_TRANSFORMED: tuple[tuple[str, int], ...] = (
    ("motorik", 7),
    ("kosmische", 3),
    ("ambient", 3),
    ("dub-electronic", 5),
    ("indie-noise", 5),
)


@pytest.mark.parametrize(("lane", "head_count"), HEAD_TRANSFORMED)
def test_gate13_at_45s_all_lanes(lane: str, head_count: int) -> None:
    plan = director(compose(load_preset(lane), 1042, 45 * 44100))
    appearances = plan.motif_appearances
    transformed = sum(1 for app in appearances if app.transform != "identity")
    identities = sum(1 for app in appearances if app.transform == "identity")

    assert transformed >= MINIMUM_TRANSFORMED_APPEARANCES
    assert transformed == head_count, lane
    assert identities == 1, lane
    assert not [f for f in check_gate_13(plan) if f.check == "transformed motif appearances"], lane
