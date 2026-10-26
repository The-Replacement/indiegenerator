"""c35: a batch covers every lane the station declares.

The lane is drawn from the seed, so a fixed seed window can miss a lane: a
batch of twelve misses indie-noise 32 % of the time and dub 14 %
(docs/RESEARCH-2026-10-25-what-would-make-it-greater.md, F3). The batch looks
forward for the first window that covers them all. What must NOT change is
that a seed still names a track: the window moves, the draw does not.
"""

from __future__ import annotations

from collections import Counter

import pytest

from indiegen.batch import covering_seed_base, lane_for, station_lanes
from indiegen.compose import compose
from indiegen.config import load_preset
from indiegen.errors import PlanError

STATION = load_preset("station")
LANES = station_lanes(STATION)


def test_the_batch_must_cover_the_stations_lanes() -> None:
    assert LANES == ["motorik", "kosmische", "ambient", "dub-electronic", "indie-noise"]


def test_the_lane_mirror_agrees_with_the_composer() -> None:
    """The batch reads the lane without composing, so the mirror has to hold.

    If compose ever draws something before pick_lane, this fails loudly
    instead of the coverage search quietly checking a different number.
    """
    for seed in range(5000, 5040):
        plan = compose(STATION, seed, 60 * 44_100)
        assert lane_for(STATION, seed) == plan.lane, f"seed {seed}"


def test_a_window_that_already_covers_the_lanes_is_used_as_asked() -> None:
    """The search must not move a window that is already good."""
    covered = covering_seed_base(STATION, 12, 5000)
    assert covering_seed_base(STATION, 12, covered) == covered


def test_the_requested_windows_that_missed_would_have_missed() -> None:
    """The 2026-10-25 batch is the case this exists for.

    Seeds 5000..5011 drew no indie-noise, which is the 31.7 % outcome the
    research measured, so the search moves the window instead of shipping a
    release with four of the station's five colours.
    """
    requested = {lane_for(STATION, 5000 + index) for index in range(12)}
    assert requested < set(LANES)
    base = covering_seed_base(STATION, 12, 5000)
    assert base != 5000
    assert {lane_for(STATION, base + index) for index in range(12)} >= set(LANES)


@pytest.mark.parametrize("count", [12, 16, 20])
def test_every_window_the_search_returns_covers_every_lane(count: int) -> None:
    for requested in range(5000, 5060):
        base = covering_seed_base(STATION, count, requested)
        drawn = {lane_for(STATION, base + index) for index in range(count)}
        assert drawn >= set(LANES), f"requested {requested} gave base {base} with {sorted(drawn)}"


def test_the_search_never_goes_backwards() -> None:
    for requested in range(5000, 5060):
        assert covering_seed_base(STATION, 12, requested) >= requested


def test_coverage_is_the_only_reason_a_window_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    """The search takes no library set: refusal stays a refusal.

    test_batch.py pins that a seed already in the library is refused. If the
    coverage search were handed the library it could step over that refusal and
    start the batch somewhere the caller did not ask for, so the signature has
    no such parameter and the guard runs on the window the search chose.
    """
    from indiegen import batch as batch_module

    assert "known" not in batch_module.covering_seed_base.__code__.co_varnames
    monkeypatch.setattr(batch_module, "lane_for", lambda preset, seed: "motorik")
    with pytest.raises(PlanError):
        batch_module.covering_seed_base(STATION, 12, 5000)


def test_a_batch_smaller_than_the_lane_count_is_left_where_it_was_asked_for() -> None:
    """Three tracks cannot cover five lanes, so the search must not pretend."""
    assert covering_seed_base(STATION, 3, 5000) == 5000
    assert covering_seed_base(STATION, len(LANES) - 1, 7777) == 7777


def test_a_single_lane_preset_needs_no_search() -> None:
    lane = load_preset("ambient")
    assert station_lanes(lane) == ["ambient"]
    assert covering_seed_base(lane, 4, 5000) == 5000


def test_the_lane_draw_still_follows_the_weights() -> None:
    """Coverage is a policy on top of the draw, not a replacement for it.

    Conditioning on coverage must not turn the mix into an even spread: over
    many windows the shares have to stay near the station's weights.
    """
    weights = {entry.lane: entry.weight for entry in STATION.lanes if entry.weight > 0}
    total = sum(weights.values())
    counts: Counter[str] = Counter()
    windows = 120
    bases = [covering_seed_base(STATION, 12, 5000 + 20 * index) for index in range(windows)]
    for base in bases:
        for index in range(12):
            counts[lane_for(STATION, base + index)] += 1
    drawn = sum(counts.values())
    for lane, weight in weights.items():
        share = 100 * counts[lane] / drawn
        expected = 100 * weight / total
        assert abs(share - expected) <= 4.0, f"{lane}: {share:.1f}% drawn, {expected:.1f}% declared"
