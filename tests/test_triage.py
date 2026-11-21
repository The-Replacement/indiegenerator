"""Triage: the library-relative outlier flag (issue #16 reframe)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from indiegen.triage import FEATURES, TriageReport, _distances, triage


def _sidecar(
    name: str,
    lra: float,
    timbre: float,
    stereo: float,
    energy: float,
    n_sections: int,
    seed: int = 1,
) -> dict[str, object]:
    return {
        "schema": "indiegen/sidecar/1",
        "preset": "station",
        "seed": seed,
        "lane": "motorik",
        "plan_sha256": "0" * 64,
        "pcm_sha256": f"{seed:064d}",
        "plan": {
            "form": "full",
            "sections": [{"index": i} for i in range(n_sections)],
        },
        "measurements": {
            "duration_seconds": 20.0,
            "integrated_lufs": -16.0,
            "sample_peak_dbfs": -4.0,
            "true_peak_dbtp": -4.3,
            "loudness_range_lu": lra,
            "stereo_correlation": stereo,
            "energy_correlation": energy,
            "timbre_correlation": timbre,
        },
    }


def _write(tmp_path: Path, name: str, payload: dict[str, object]) -> None:
    (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")


def _normal_corpus(tmp_path: Path, n: int = 12) -> None:
    rng = np.random.default_rng(1042)
    for i in range(n):
        _write(
            tmp_path,
            f"t{i:02d}.json",
            _sidecar(
                f"t{i:02d}",
                lra=float(7.0 + rng.normal(0, 0.5)),
                timbre=float(0.6 + rng.normal(0, 0.1)),
                stereo=float(0.8 + rng.normal(0, 0.05)),
                energy=float(0.9 + rng.normal(0, 0.02)),
                n_sections=int(rng.choice([3, 4, 4, 5])),
                seed=1000 + i,
            ),
        )


def test_distances_orders_by_outlyingness() -> None:
    matrix = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.5], [10.0, 0.0]])
    distances, method = _distances(matrix)
    assert method == "mahalanobis"
    assert distances[5] == max(distances)


def test_distances_falls_back_when_singular() -> None:
    matrix = np.array([[1.0, 2.0], [1.0, 2.0], [1.0, 5.0]])
    distances, method = _distances(matrix)
    assert method == "standardized-euclidean"
    assert distances[2] > distances[0]


def test_empty_directory_reports_nothing(tmp_path: Path) -> None:
    report = triage(tmp_path)
    assert report.tracks == []
    assert isinstance(report, TriageReport)


def test_incomplete_sidecars_are_skipped_not_failed(tmp_path: Path) -> None:
    _write(tmp_path, "good.json", _sidecar("good", 7.0, 0.6, 0.8, 0.9, 4, seed=1))
    broken = _sidecar("broken", 7.0, 0.6, 0.8, 0.9, 4, seed=2)
    del broken["measurements"]
    _write(tmp_path, "broken.json", broken)
    report = triage(tmp_path)
    assert len(report.tracks) == 1
    assert len(report.skipped) == 1


def test_degenerate_track_ranks_first(tmp_path: Path) -> None:
    """Falsifier 1: an injected degenerate track must be the top outlier."""
    _normal_corpus(tmp_path)
    _write(tmp_path, "degenerate.json", _sidecar("degenerate", 0.5, 0.01, 0.0, 0.1, 1, seed=9999))
    report = triage(tmp_path)
    assert report.tracks[0].path.endswith("degenerate.flac")
    assert report.tracks[0].flagged


def test_ranking_is_deterministic(tmp_path: Path) -> None:
    """Falsifier 2: same catalog bytes -> same ranking."""
    _normal_corpus(tmp_path)
    first = [(t.path, t.distance, t.flagged) for t in triage(tmp_path).tracks]
    second = [(t.path, t.distance, t.flagged) for t in triage(tmp_path).tracks]
    assert first == second


def test_normal_corpus_flags_at_most_one_by_default(tmp_path: Path) -> None:
    """A normal-shaped corpus produces no flag storm.

    A flag is a human referral, not a failure verdict, so the honest bound
    is "at most one marginal flag", not zero: the chi-square cutoff is a
    1% tail by construction. What matters is the separation from a real
    degenerate (see test_degenerate_track_ranks_first: d2 in the thousands
    vs ~16 here).
    """
    _normal_corpus(tmp_path, n=20)
    report = triage(tmp_path)
    assert report.method == "mahalanobis"
    assert sum(1 for t in report.tracks if t.flagged) <= 1


def test_method_names_a_feature_per_track(tmp_path: Path) -> None:
    _normal_corpus(tmp_path, n=11)
    report = triage(tmp_path)
    assert set(report.tracks[0].features) == set(FEATURES)


def test_top_flag_forces_flag_without_threshold(tmp_path: Path) -> None:
    _normal_corpus(tmp_path, n=11)
    report = triage(tmp_path, threshold=10**9, top=2)
    assert sum(1 for t in report.tracks if t.flagged) == 2
