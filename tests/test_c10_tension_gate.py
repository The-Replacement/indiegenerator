"""T9 (issue #10, AC-3.1-3.5, AC-6.1): synthetic tests for the null harness.

Fast and synthetic only: no full corpus renders. Every number here comes
from fixed hand-built vectors; the harness module is loaded from
``tools/c10_tension_gate.py`` without executing ``main()``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np

_HARNESS_PATH = Path(__file__).resolve().parents[1] / "tools" / "c10_tension_gate.py"
_spec = importlib.util.spec_from_file_location("c10_tension_gate", _HARNESS_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)  # type: ignore[union-attr]


def _track(
    corpus: str,
    lane: str,
    seed: int,
    seconds: int,
    planned: list[int],
    measured: list[float],
    pcm_nonempty: bool = True,
) -> Any:
    return gate.Track(
        corpus=corpus,
        lane=lane,
        seed=seed,
        seconds=seconds,
        planned=planned,
        measured=measured,
        pcm_nonempty=pcm_nonempty,
    )


def _mini_corpus() -> list[Any]:
    """Three corpora with one analysable track each, plus flat/empty exemptions."""
    return [
        _track("a", "motorik", 1042, 240, [100, 900, 300, 700], [200.0, 800.0, 400.0, 600.0]),
        _track("b", "kosmische", 1042, 45, [700, 200, 800, 300], [600.0, 300.0, 750.0, 250.0]),
        _track("c", "station", 5000, 60, [300, 700, 200, 800], [350.0, 650.0, 250.0, 750.0]),
        _track("a", "ambient", 2000, 240, [500, 500, 500, 500], [100.0, 900.0, 200.0, 800.0]),
        _track("b", "dub-electronic", 3005, 60, [100, 200], [50.0, 150.0]),
    ]


def test_permutation_preserves_the_multiset_of_measured() -> None:
    """Every null draw is a rearrangement of M, never a new set of values."""
    measured = np.array([100.0, 900.0, 300.0, 700.0, 500.0])
    planned = np.array([200.0, 800.0, 400.0, 600.0, 500.0])
    rng = np.random.default_rng(0)
    for _ in range(1000):
        drawn = rng.permutation(measured)
        assert sorted(drawn) == sorted(measured)
        assert np.array_equal(np.sort(drawn), np.sort(measured))
        assert drawn.size == planned.size


def test_rng0_reproducibility_on_fixed_vectors() -> None:
    """Two rng(0) runs give the identical null distribution."""
    measured = np.array([100.0, 900.0, 300.0, 700.0, 500.0])
    planned = np.array([200.0, 800.0, 400.0, 600.0, 500.0])
    first = gate.null_distribution(measured, planned, n_perms=1000, rng=np.random.default_rng(0))
    second = gate.null_distribution(measured, planned, n_perms=1000, rng=np.random.default_rng(0))
    assert np.array_equal(first, second)
    assert first.size == 1000
    # And a different seed is (almost surely) a different distribution.
    other = gate.null_distribution(measured, planned, n_perms=1000, rng=np.random.default_rng(1))
    assert not np.array_equal(first, other)


def test_summarize_is_reproducible_with_rng0() -> None:
    """The pooled means are bit-identical across two summarize() runs."""
    tracks = _mini_corpus()
    first = gate.summarize(tracks, n_perms=200)
    second = gate.summarize(_mini_corpus(), n_perms=200)
    assert first["pooled"] == second["pooled"]
    assert first["a"] == second["a"]
    assert first["b"] == second["b"]
    assert first["c"] == second["c"]


def test_exempt_tracks_are_excluded_from_both_means() -> None:
    """Flat and short tracks contribute neither Pearson nor null draws."""
    tracks = _mini_corpus()
    report = gate.summarize(tracks, n_perms=100)
    assert report["pooled"]["non_exempt_tracks"] == 3
    assert report["pooled"]["tracks"] == 5
    assert report["a"]["non_exempt_tracks"] == 1
    assert report["b"]["non_exempt_tracks"] == 1
    assert report["c"]["non_exempt_tracks"] == 1
    # Flat planned is exempt by the gate-6 0.05*mean rule.
    assert gate.exemption_reason([500, 500, 500, 500], True) is not None
    # Exactly at the 0.05 * mean spread is still flat (mirrors validate).
    assert gate.exemption_reason([488, 513, 500, 499], True) == "flat planned tension"
    # One permille wider is no longer flat.
    assert gate.exemption_reason([487, 513, 500, 499], True) is None
    # Two sections is exempt whatever the values.
    assert gate.exemption_reason([100, 900], True) == "fewer than 3 sections"
    # A non-positive mean is exempt.
    assert gate.exemption_reason([0, 0, 0, 0], True) == "planned mean <= 0"
    # Empty PCM is exempt.
    assert gate.exemption_reason([100, 900, 300], False) == "empty pcm"
    # The exempt tracks carry no measured Pearson in the report.
    by_lane = {entry["lane"]: entry for entry in report["per_track"]}
    assert by_lane["ambient"]["exempt"] is True
    assert by_lane["ambient"]["pearson"] is None
    assert by_lane["motorik"]["pearson"] is not None


def test_report_fields_are_present_on_a_synthetic_mini_corpus() -> None:
    """The JSON-shaped summary carries every field the handoff needs."""
    report = gate.summarize(_mini_corpus(), n_perms=100)
    for pool in ("pooled", "a", "b", "c"):
        for name in ("measured_mean", "null_mean", "diff", "T", "non_exempt_tracks", "tracks", "total_sections"):
            assert name in report[pool], f"{pool} missing {name}"
    # T is null_mean + 0.15 by definition.
    for pool in ("pooled", "a", "b", "c"):
        assert report[pool]["T"] == report[pool]["null_mean"] + 0.15
        assert report[pool]["diff"] == report[pool]["measured_mean"] - report[pool]["null_mean"]
    assert len(report["per_track"]) == 5
    assert report["verdict"]["slice2_attempted"] is False
    assert "vacuous" in report["verdict"]["slice2_note"]
    assert report["verdict"]["total_sections"] == sum(len(t.planned) for t in _mini_corpus())
    assert report["corpus_cells"][0]["corpus"] == "a"
    assert any(cell["corpus"] == "c" for cell in report["corpus_cells"])


def test_verdict_requires_all_four_pools_above_the_margin() -> None:
    """Pooled-only success is not promotion; each corpus must clear 0.15."""
    # All four clear, corpus met: promote-eligible.
    ok = gate.decide_verdict(total_sections=500, pooled_diff=0.99, a_diff=0.20, b_diff=0.20, c_diff=0.20)
    assert ok["verdict"] == "PROMOTE-ELIGIBLE"
    assert ok["pooled_pass"] and ok["a_pass"] and ok["b_pass"] and ok["c_pass"]
    # Pooled clears but corpus (b) does not: no-promote.
    bad_b = gate.decide_verdict(total_sections=600, pooled_diff=0.99, a_diff=0.20, b_diff=0.10, c_diff=0.20)
    assert bad_b["verdict"] == "NO-PROMOTE/KILL"
    assert bad_b["pooled_pass"] and bad_b["a_pass"] and bad_b["c_pass"] and not bad_b["b_pass"]
    assert any("corpus (b)" in reason for reason in bad_b["reasons"])
    # Pooled clears but corpus (c) does not: no-promote.
    bad_c = gate.decide_verdict(total_sections=637, pooled_diff=0.99, a_diff=0.20, b_diff=0.20, c_diff=0.10)
    assert bad_c["verdict"] == "NO-PROMOTE/KILL"
    assert bad_c["pooled_pass"] and bad_c["a_pass"] and bad_c["b_pass"] and not bad_c["c_pass"]
    assert any("corpus (c)" in reason for reason in bad_c["reasons"])
    # Pooled does not clear: no-promote.
    bad_pooled = gate.decide_verdict(total_sections=600, pooled_diff=0.05, a_diff=0.30, b_diff=0.30, c_diff=0.30)
    assert bad_pooled["verdict"] == "NO-PROMOTE/KILL"
    assert not bad_pooled["pooled_pass"]
    # Exactly 0.15 is not above 0.15 (strictly greater).
    edge = gate.decide_verdict(total_sections=600, pooled_diff=0.15, a_diff=0.15, b_diff=0.15, c_diff=0.15)
    assert edge["verdict"] == "NO-PROMOTE/KILL"
    # Corpus below target: AC-3.2 NOT MET wins even when the diffs clear.
    small = gate.decide_verdict(total_sections=499, pooled_diff=0.99, a_diff=0.99, b_diff=0.99, c_diff=0.99)
    assert small["verdict"] == "AC-3.2 NOT MET"
    assert not small["corpus_met"]


def test_the_corpus_cells_are_pinned_in_draw_order() -> None:
    """135 cells: (a) 15, (b) 90, (c) 30 station in seed order."""
    cells = gate.corpus_cells()
    assert len(cells) == 135
    a_cells = cells[:15]
    b_cells = cells[15:105]
    c_cells = cells[105:]
    assert len(a_cells) == 15
    assert len(b_cells) == 90
    assert len(c_cells) == 30
    assert [(c.lane, c.seed, c.seconds) for c in a_cells[:3]] == [
        ("motorik", 1042, 240),
        ("motorik", 2000, 240),
        ("motorik", 4002, 240),
    ]
    assert [(c.lane, c.seed, c.seconds) for c in b_cells[:6]] == [
        ("motorik", 1042, 45),
        ("motorik", 1042, 60),
        ("motorik", 1042, 90),
        ("motorik", 1042, 120),
        ("motorik", 1042, 240),
        ("motorik", 1042, 480),
    ]
    assert cells[-1].lane == "station"
    assert cells[-1].seed == 5029
    assert cells[-1].seconds == 60
    assert {c.seed for c in b_cells} == {1042, 2000, 3005}
    assert {c.seed for c in a_cells} == {1042, 2000, 4002}
    assert {c.seconds for c in b_cells} == {45, 60, 90, 120, 240, 480}
    assert list(gate.DURATIONS_B) == [45, 60, 90, 120, 240, 480]
    assert list(gate.LANES) == ["motorik", "kosmische", "dub-electronic", "indie-noise", "ambient"]
    assert [c.seed for c in c_cells] == list(range(5000, 5030))
    assert all(c.corpus == "c" and c.lane == "station" and c.seconds == 60 for c in c_cells)
    assert list(gate.SEEDS_C) == list(range(5000, 5030))
    assert gate.SECONDS_C == 60
    assert gate.STATION_PRESET == "station"
