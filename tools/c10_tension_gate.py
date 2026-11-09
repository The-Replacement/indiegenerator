"""c10 tension gate null harness (issue #10, T9: AC-3.1-3.5, AC-6.1).

Threshold harness only. Promotion code (T10) and Slice-2 DSP are NOT in this
file: the report records the verdict and the falsifier evidence, and no gate
constant is changed here.

Null (AC-3.1): per non-exempt track, ``P`` is the planned
``tension_permille`` list and ``M`` the measured tension walk (permille,
post-walk, same section order as ``validate.tension_correlation`` internals).
``M`` is permuted within the track, and
``validate.pearson(permuted_M, P)`` is evaluated for 1000 permutations per
track with a single ``np.random.default_rng(0)`` whose draws are consumed in
corpus order. ``null_mean`` pools all permutations over all non-exempt
tracks; ``measured_mean`` pools the per-track Pearsons over non-exempt
tracks. Exempt tracks (``len(sections) < 3``, empty PCM, planned mean
``<= 0``, or flat planned ``max - min <= 0.05 * mean``, mirroring
``validate.tension_correlation``) are excluded from BOTH means and consume
zero RNG draws.

Coupling: this harness imports five private helpers from
``indiegen.validate`` (``_tension_pitched_notes``,
``_pcm_section_millibels``, ``_pcm_section_onsets``,
``_carried_pitch_roughness``, ``_measured_walk``). ``tension_vectors``
replicates the ``tension_correlation`` internals step for step so ``M`` is
the measured walk the gate would correlate, in the same order. If
``tension_correlation`` changes its measurement, this file must change with
it; the duplication is deliberate because ``validate`` must not import
``compose`` and the tools script sits outside the shipped package.

Corpus (AC-3.2 as amended; see below): (a) the sweep15, 5 lanes x seeds
(1042, 2000, 4002) at 240 s, via ``director(compose(load_preset(lane), seed,
240*44100))`` as in ``tests/test_sweep.py:37-54``; (b) the recreated c39
cells, 90 cells = 5 lanes x seeds (1042, 2000, 3005) x durations
(45, 60, 90, 120, 240, 480) s, with seeds per
``docs/handoff/c39-tension-budget.md:54,128`` (the full 6-duration set,
the 424-section calibration basis); (c) the station draws, 30 tracks =
seeds 5000..5029 at 60 s via ``director(compose(load_preset('station'),
seed, 60*44100))`` (verified against ``tests/test_c35.py:21,36`` and
``docs/handoff/c39-tension-budget.md:54-56`` /
``docs/handoff/c41-planned-centroid.md:83``: 30 draws, 140 sections).
Corpus order is (a) in lane-then-seed order followed by (b) in
lane-then-seed-then-duration order followed by (c) in seed-ascending
order, with lanes in ``test_sweep.py:37`` order. Each cell renders
through the ``test_sweep`` in-memory path: ``render_plan`` + ``master(plan,
mix, BLOCK_SIZE)`` giving
the delivered int16 PCM ``tension_correlation`` expects. The
``batch.render_track`` file path is not used: it refuses tracks that fail
the live gates, so it would drop cells from the corpus and undercount it.

Amended AC-3.2 (user-approved 2026-11-07, spec amendment memory id
``3639f1ac-727d-5b6e-956d-0957c851cdc7`` / topic_key
``sdd-c10-tension-gate-spec-amendment``): (b) durations expanded from
(45, 60, 90, 120) to (45, 60, 90, 120, 240, 480); seeds, lanes, (a)
sweep15, and all other ACs (3.1 null, 3.3 promotion, 3.4 Slice 2 vacuous,
3.5 falsifier, 5.5) are unchanged; the target stays ``>=500`` sections.
This run supersedes the v1 351-section run (75 tracks, 73+278 sections,
verdict AC-3.2 NOT MET); this expanded re-run's verdict governs T10.

Spec amendment #2 (memory id ``94f500a6...`` / topic_key
``sdd-c10-tension-gate-spec-amendment2``, 2026-11-07; supersedes the
amendment-1 expanded 497-section run 37a9117f, verdict AC-3.2 NOT MET):
corpus (c) added — 30 station tracks seeds 5000..5029 @60s (~140
sections) appended AFTER (a) then (b) in corpus order (single rng0 draws
consumed (a)→(b)→(c)). Union is now (a) sweep15 (73 sections) + (b) 90
cells (424 sections) + (c) station 30 (~140 sections) = ~637 sections,
target >=500. This re-run re-renders every (a)/(b) cell in full: the
prior JSON holds per-track Pearsons but not PCM, and re-rendering is
required for the M vectors (null draws for (a)/(b) are prefix-identical
because (c) is appended after, but no Pearson is reused as a substitute).

Promotion (AC-3.3 as amended): promote iff ``measured_mean - null_mean > 0.15``
pooled AND in each corpus (a)/(b)/(c) separately. ``T = null_mean + 0.15``
is reported with at least 6 decimals. Slice 2 (AC-3.4) is not attempted
in T9, so the report states that it is vacuous and the promotion follows
AC-3.3 alone when the corpus and promotion conditions are met. Falsifier
(AC-3.5): a pooled or per-corpus difference ``<= 0.15``, or a corpus
below 500 sections, yields NO-PROMOTE / KILL / AC-3.2 NOT MET with the
evidence recorded; no code promotion is performed by this harness.

Determinism (AC-6.1): the only RNG in this file is the null
``np.random.default_rng(0)``. The predictor (``compose``/``director``) rolls
no dice here; its determinism is already verified (gate 10).

Run: ``python tools/c10_tension_gate.py`` (default: full corpus, writes
``docs/handoff/c10-tension-gate.md`` and ``docs/handoff/c10-tension-gate.json``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# The script lives outside the wheel (pyproject packages = ["src/indiegen"]),
# so allow running as a bare script without an editable install.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from indiegen.compose import compose, director  # noqa: E402
from indiegen.config import load_preset  # noqa: E402
from indiegen.master.chain import master  # noqa: E402
from indiegen.plan import Plan  # noqa: E402
from indiegen.render import BLOCK_SIZE, render_plan  # noqa: E402
from indiegen.validate import (  # noqa: E402
    STATIC_CENTROID_TOLERANCE,
    _carried_pitch_roughness,
    _measured_walk,
    _pcm_section_millibels,
    _pcm_section_onsets,
    _tension_pitched_notes,
    pearson,
)

LANES: tuple[str, ...] = ("motorik", "kosmische", "dub-electronic", "indie-noise", "ambient")
"""Lane order of ``tests/test_sweep.py:37``; consumed first in corpus order."""

SEEDS_A: tuple[int, ...] = (1042, 2000, 4002)
"""Sweep-15 seeds of ``tests/test_sweep.py:38``."""

SEEDS_B: tuple[int, ...] = (1042, 2000, 3005)
"""Recreated-c39 seeds (``docs/handoff/c39-tension-budget.md:54,128``)."""

DURATIONS_B: tuple[int, ...] = (45, 60, 90, 120, 240, 480)
"""Recreated-c39 durations in seconds (amended AC-3.2: full 6-duration set)."""

SECONDS_A: int = 240
"""Sweep-15 render length in seconds (``tests/test_sweep.py:39``)."""

SEEDS_C: tuple[int, ...] = tuple(range(5000, 5030))
"""Station-draw seeds 5000..5029 (``docs/handoff/c41-planned-centroid.md:83``)."""

SECONDS_C: int = 60
"""Station-draw render length in seconds."""

STATION_PRESET: str = "station"
"""Station preset name; ``compose`` draws the lane from the seed."""

RATE: int = 44100
"""Sample rate of every cell."""

N_PERMS: int = 1000
"""Permutations per non-exempt track (AC-3.1)."""

NULL_SEED: int = 0
"""The single null seed (AC-6.1); ``np.random.default_rng(0)``."""

PROMOTION_MARGIN: float = 0.15
"""The AC-3.3 promotion margin."""

CORPUS_TARGET: int = 500
"""The AC-3.2 corpus-size target, in sections."""

DEFAULT_MD_PATH: Path = _REPO_ROOT / "docs" / "handoff" / "c10-tension-gate.md"
DEFAULT_JSON_PATH: Path = _REPO_ROOT / "docs" / "handoff" / "c10-tension-gate.json"


@dataclass(frozen=True)
class Cell:
    """One pinned corpus cell, in corpus order."""

    corpus: str
    lane: str
    seed: int
    seconds: int


@dataclass
class Track:
    """One rendered track's planned and measured tension vectors."""

    corpus: str
    lane: str
    seed: int
    seconds: int
    planned: list[int]
    measured: list[float]
    pcm_nonempty: bool = True
    pearson_measured: float | None = None
    null_values: list[float] = field(default_factory=list)

    @property
    def section_count(self) -> int:
        """Sections this track contributed."""
        return len(self.planned)

    @property
    def exempt_reason(self) -> str | None:
        """Why this track is exempt, or ``None`` when it is not."""
        return exemption_reason(self.planned, self.pcm_nonempty)


def corpus_cells() -> list[Cell]:
    """The literal corpus in draw-consumption order: (a) then (b) then (c)."""
    cells: list[Cell] = []
    for lane in LANES:
        for seed in SEEDS_A:
            cells.append(Cell(corpus="a", lane=lane, seed=seed, seconds=SECONDS_A))
    for lane in LANES:
        for seed in SEEDS_B:
            for seconds in DURATIONS_B:
                cells.append(Cell(corpus="b", lane=lane, seed=seed, seconds=seconds))
    for seed in SEEDS_C:
        cells.append(Cell(corpus="c", lane=STATION_PRESET, seed=seed, seconds=SECONDS_C))
    return cells


def exemption_reason(planned: list[int] | np.ndarray, pcm_nonempty: bool) -> str | None:
    """Mirror of the ``tension_correlation`` exemptions, or ``None``."""
    values = [int(item) for item in list(planned)]
    if not pcm_nonempty:
        return "empty pcm"
    if len(values) < 3:
        return "fewer than 3 sections"
    mean = float(np.mean(np.array(values, dtype=np.float64)))
    if mean <= 0.0:
        return "planned mean <= 0"
    if max(values) - min(values) <= STATIC_CENTROID_TOLERANCE * mean:
        return "flat planned tension"
    return None


def tension_vectors(plan: Plan, pcm: np.ndarray) -> tuple[list[int], list[float]]:
    """Planned ``P`` and measured ``M`` in ``tension_correlation`` order.

    The body is the ``tension_correlation`` measurement step for step: PCM
    loudness and onset per section, carried pitch and roughness from the
    planned events, and the float64 walk from 500.
    """
    sections = list(plan.sections)
    planned = [int(section.tension_permille) for section in sections]
    pitched = _tension_pitched_notes(plan.events)
    loudness = [_pcm_section_millibels(pcm, section.start_frame, section.end_frame) for section in sections]
    onsets = _pcm_section_onsets(pcm, plan.sample_rate, sections)
    carried = [
        _carried_pitch_roughness(plan.events, section.start_frame, section.end_frame, pitched) for section in sections
    ]
    features: list[dict[str, float]] = [
        {
            "loudness": loudness[index],
            "onset": float(onsets[index]),
            "pitch": carried[index][0],
            "roughness": carried[index][1],
        }
        for index in range(len(sections))
    ]
    measured = _measured_walk(features)
    return planned, [float(value) for value in measured]


def null_distribution(
    measured: np.ndarray,
    planned: np.ndarray,
    *,
    n_perms: int = N_PERMS,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """``pearson(permuted_M, P)`` over ``n_perms`` within-track permutations."""
    if rng is None:
        rng = np.random.default_rng(NULL_SEED)
    measured = np.asarray(measured, dtype=np.float64)
    planned = np.asarray(planned, dtype=np.float64)
    values = np.zeros(n_perms, dtype=np.float64)
    for index in range(n_perms):
        values[index] = pearson(rng.permutation(measured), planned)
    return values


def _mean(values: list[float]) -> float:
    """Mean of a non-empty list, else ``nan`` (an empty pool cannot pass)."""
    if not values:
        return float("nan")
    return float(np.mean(np.array(values, dtype=np.float64)))


def _pool(tracks: list[Track], n_perms: int, rng: np.random.Generator) -> tuple[float, float, int, int, int]:
    """Fill measured/null pools for one track subset, consuming ``rng``."""
    measured: list[float] = []
    nulls: list[float] = []
    sections = 0
    analysable_sections = 0
    for track in tracks:
        sections += track.section_count
        reason = track.exempt_reason
        if reason is not None:
            track.pearson_measured = None
            track.null_values = []
            continue
        planned = np.array(track.planned, dtype=np.float64)
        measured_values = np.array(track.measured, dtype=np.float64)
        measured_pearson = pearson(measured_values, planned)
        if not np.isfinite(measured_pearson):
            measured_pearson = 0.0
        track.pearson_measured = float(measured_pearson)
        draws = null_distribution(measured_values, planned, n_perms=n_perms, rng=rng)
        track.null_values = [float(value) for value in draws]
        measured.append(float(measured_pearson))
        nulls.extend(track.null_values)
        analysable_sections += track.section_count
    measured_mean = _mean(measured)
    null_mean = _mean(nulls)
    return measured_mean, null_mean, len(measured), sections, analysable_sections


def decide_verdict(
    *,
    total_sections: int,
    pooled_diff: float,
    a_diff: float,
    b_diff: float,
    c_diff: float,
    corpus_target: int = CORPUS_TARGET,
    margin: float = PROMOTION_MARGIN,
) -> dict[str, Any]:
    """AC-3.3/AC-3.5 verdict from already-pooled differences (pure)."""
    corpus_met = total_sections >= corpus_target
    diffs = {"pooled": pooled_diff, "a": a_diff, "b": b_diff, "c": c_diff}
    passes = {key: bool(np.isfinite(diff) and diff > margin) for key, diff in diffs.items()}
    reasons: list[str] = []
    if not corpus_met:
        reasons.append(f"AC-3.2 NOT MET: total sections {total_sections} < {corpus_target}")
    pools: list[tuple[str, str, float]] = [
        ("pooled", "pooled", pooled_diff),
        ("a", "corpus (a)", a_diff),
        ("b", "corpus (b)", b_diff),
        ("c", "corpus (c)", c_diff),
    ]
    for key, label, diff in pools:
        if not passes[key]:
            if np.isfinite(diff):
                reasons.append(f"{label} measured-null {diff:.6f} <= {margin:.2f}")
            else:
                reasons.append(f"{label} pool is empty (no non-exempt tracks)")
    if not corpus_met:
        verdict = "AC-3.2 NOT MET"
    elif all(passes.values()):
        verdict = "PROMOTE-ELIGIBLE"
    else:
        verdict = "NO-PROMOTE/KILL"
    return {
        "verdict": verdict,
        "corpus_met": corpus_met,
        "total_sections": total_sections,
        "corpus_target": corpus_target,
        "pooled_pass": passes["pooled"],
        "a_pass": passes["a"],
        "b_pass": passes["b"],
        "c_pass": passes["c"],
        "margin": margin,
        "reasons": reasons,
        "slice2_attempted": False,
        "slice2_note": "Slice 2 DSP not attempted in T9: vacuous per spec, promotion follows AC-3.3 alone.",
    }


def summarize(tracks: list[Track], *, n_perms: int = N_PERMS, null_seed: int = NULL_SEED) -> dict[str, Any]:
    """Pool measured/null Pearsons over the union and per corpus (pure)."""
    rng = np.random.default_rng(null_seed)
    a_tracks = [track for track in tracks if track.corpus == "a"]
    b_tracks = [track for track in tracks if track.corpus == "b"]
    c_tracks = [track for track in tracks if track.corpus == "c"]

    def _block(subset: list[Track], sub_rng: np.random.Generator) -> dict[str, Any]:
        measured_mean, null_mean, count, sections, analysable = _pool(subset, n_perms, sub_rng)
        diff = measured_mean - null_mean if np.isfinite(measured_mean) and np.isfinite(null_mean) else float("nan")
        return {
            "measured_mean": measured_mean,
            "null_mean": null_mean,
            "diff": diff,
            "T": null_mean + PROMOTION_MARGIN if np.isfinite(null_mean) else float("nan"),
            "non_exempt_tracks": count,
            "tracks": len(subset),
            "total_sections": sections,
            "non_exempt_sections": analysable,
        }

    # Single rng, consumed in corpus order: (a) tracks, (b) tracks, (c) tracks.
    block_a = _block(a_tracks, rng)
    block_b = _block(b_tracks, rng)
    block_c = _block(c_tracks, rng)
    # Pooled over the union shares the same sequential draws: recompute it in
    # full corpus order with a fresh rng so the pooled null is not a
    # concatenation of the per-corpus rng states. The order matches corpus
    # order because tracks arrive in corpus order.
    pooled_rng = np.random.default_rng(null_seed)
    measured_mean, null_mean, count, sections, analysable = _pool(list(tracks), n_perms, pooled_rng)
    pooled_diff = measured_mean - null_mean if np.isfinite(measured_mean) and np.isfinite(null_mean) else float("nan")
    pooled = {
        "measured_mean": measured_mean,
        "null_mean": null_mean,
        "diff": pooled_diff,
        "T": null_mean + PROMOTION_MARGIN if np.isfinite(null_mean) else float("nan"),
        "non_exempt_tracks": count,
        "tracks": len(tracks),
        "total_sections": sections,
        "non_exempt_sections": analysable,
    }
    verdict = decide_verdict(
        total_sections=sections,
        pooled_diff=pooled_diff,
        a_diff=float(block_a["diff"]),
        b_diff=float(block_b["diff"]),
        c_diff=float(block_c["diff"]),
    )
    per_track = [
        {
            "corpus": track.corpus,
            "lane": track.lane,
            "seed": track.seed,
            "seconds": track.seconds,
            "section_count": track.section_count,
            "exempt": track.exempt_reason is not None,
            "exempt_reason": track.exempt_reason,
            "pearson": track.pearson_measured,
            "planned": list(track.planned),
            "measured": list(track.measured),
        }
        for track in tracks
    ]
    return {
        "pooled": pooled,
        "a": block_a,
        "b": block_b,
        "c": block_c,
        "verdict": verdict,
        "per_track": per_track,
        "n_perms": n_perms,
        "null_seed": null_seed,
        "margin": PROMOTION_MARGIN,
        "corpus_target": CORPUS_TARGET,
        "corpus_cells": [
            {"corpus": track.corpus, "lane": track.lane, "seed": track.seed, "seconds": track.seconds}
            for track in tracks
        ],
        "lanes": list(LANES),
        "seeds_a": list(SEEDS_A),
        "seeds_b": list(SEEDS_B),
        "seeds_c": list(SEEDS_C),
        "durations_b": list(DURATIONS_B),
        "seconds_a": SECONDS_A,
        "seconds_c": SECONDS_C,
        "station_preset": STATION_PRESET,
    }


def render_cell(cell: Cell) -> Track:
    """Render one cell through the in-memory ``test_sweep`` path."""
    plan = director(compose(load_preset(cell.lane), cell.seed, cell.seconds * RATE))
    mix = render_plan(plan)
    pcm = master(plan, mix, BLOCK_SIZE)
    planned, measured = tension_vectors(plan, pcm)
    nonempty = bool(pcm.size)
    del mix
    return Track(
        corpus=cell.corpus,
        lane=cell.lane,
        seed=cell.seed,
        seconds=cell.seconds,
        planned=planned,
        measured=measured,
        pcm_nonempty=nonempty,
    )


def worst_tracks(per_track: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """The lowest measured Pearsons among non-exempt tracks."""
    scored = [entry for entry in per_track if not entry["exempt"] and entry["pearson"] is not None]
    scored.sort(key=lambda entry: float(entry["pearson"]))
    return scored[:limit]


def _fmt(value: float) -> str:
    """Six-decimal formatting for the markdown tables (T needs 6dp)."""
    return f"{value:.6f}"


def render_markdown(report: dict[str, Any], *, wall_seconds: float) -> str:
    """The human-readable handoff document."""
    pooled = report["pooled"]
    block_a = report["a"]
    block_b = report["b"]
    block_c = report["c"]
    verdict = report["verdict"]
    lines: list[str] = []
    lines.append("# c10 tension gate null harness (issue #10, T9)")
    lines.append("")
    lines.append("**Status: threshold harness only (T9).** No gate constant is changed here;")
    lines.append("Slice 2 DSP is not attempted, so it is vacuous per spec and promotion")
    lines.append("follows AC-3.3 alone when the corpus and promotion conditions are met.")
    lines.append("")
    lines.append(
        "**Amended AC-3.2 (user-approved 2026-11-07, amendment memory id"
        " 3639f1ac-727d-5b6e-956d-0957c851cdc7 / topic_key"
        " sdd-c10-tension-gate-spec-amendment):** corpus (b) expanded to 90 cells on"
        " durations [45, 60, 90, 120, 240, 480] (the full 6-duration / 424-section c39"
        " calibration basis); seeds, lanes, corpus (a) sweep15, and all other ACs"
        " unchanged; target stays >=500 sections. This expanded re-run supersedes the"
        " v1 351-section run (75 tracks: 73 + 278 sections, verdict AC-3.2 NOT MET);"
        " the verdict below governs T10."
    )
    lines.append(
        "**Spec amendment #2 (memory id 94f500a6... / topic_key"
        " sdd-c10-tension-gate-spec-amendment2, 2026-11-07):** corpus (c) station"
        " draws added — 30 tracks seeds 5000..5029 at 60 s via"
        " director(compose(load_preset('station'), seed, 60*44100)) (verified"
        " against tests/test_c35.py:21,36 and docs/handoff/c39-tension-budget.md"
        ":54-56 / docs/handoff/c41-planned-centroid.md:83: 140 sections); appended"
        " AFTER (a) then (b) in corpus order (single rng0 draws consumed"
        " (a)->(b)->(c)). Union = (a) sweep15 (73 sections) + (b) 90 cells"
        " (424 sections) + (c) station 30 (~140 sections) = ~637 sections,"
        " target >=500. This re-run supersedes the amendment-1 expanded 497-"
        "section run 37a9117f (verdict AC-3.2 NOT MET) and fully re-renders"
        " every cell: the prior JSON holds Pearsons but not PCM, and the M"
        " vectors must be re-measured (no cached Pearson is reused as a null"
        " substitute)."
    )
    lines.append("")
    lines.append("## Corpus (AC-3.2, as amended)")
    lines.append("")
    lines.append(f"- Lanes (test_sweep.py:37 order): {', '.join(report['lanes'])}")
    lines.append(
        f"- (a) sweep15: seeds {report['seeds_a']} at {report['seconds_a']} s"
        " via director(compose(load_preset(lane), seed, 240*44100)),"
        " rendered through the in-memory test_sweep path (render_plan + master)"
    )
    lines.append(
        f"- (b) recreated c39: seeds {report['seeds_b']} x durations {report['durations_b']} s"
        " (90 cells, docs/handoff/c39-tension-budget.md:54,128; amended AC-3.2, memory"
        " 3639f1ac-727d-5b6e-956d-0957c851cdc7)"
    )
    lines.append(
        f"- (c) station draws: preset {report.get('station_preset', 'station')!r} via"
        f" director(compose(load_preset('station'), seed, 60*44100)), seeds"
        f" {report['seeds_c'][0]}..{report['seeds_c'][-1]} at {report['seconds_c']} s"
        " (30 tracks; tests/test_c35.py:21,36;"
        " docs/handoff/c39-tension-budget.md:54-56; docs/handoff/c41-planned-"
        "centroid.md:83)"
    )
    lines.append("- Corpus order: (a) lane-then-seed, then (b) lane-then-seed-then-duration, then (c) seed ascending;")
    lines.append("  the null rng draws are consumed in that order.")
    lines.append(f"- Null: {report['n_perms']} within-track permutations of M,")
    lines.append(f"  ``validate.pearson(permuted_M, P)``, single rng ``np.random.default_rng({report['null_seed']})``.")
    lines.append(f"- Wall time: {wall_seconds:.1f} s")
    lines.append("")
    lines.append("## Section counts")
    lines.append("")
    lines.append("| corpus | tracks | total sections | non-exempt sections | non-exempt tracks |")
    lines.append("|---|---|---|---|---|")
    section_rows = (
        ("(a) sweep15", block_a),
        ("(b) recreated c39", block_b),
        ("(c) station draws", block_c),
        ("pooled union", pooled),
    )
    for label, block in section_rows:
        lines.append(
            f"| {label} | {block['tracks']} | {block['total_sections']} |"
            f" {block['non_exempt_sections']} | {block['non_exempt_tracks']} |"
        )
    lines.append("")
    lines.append(f"Corpus target: {verdict['corpus_target']} sections (total).")
    if not verdict["corpus_met"]:
        lines.append(
            f"**AC-3.2 NOT MET:** the literal corpus yields {verdict['total_sections']} total sections;"
            " the corpus was not expanded and thresholds were not relaxed."
        )
    lines.append("")
    lines.append("## Results (AC-3.1 / AC-3.3)")
    lines.append("")
    lines.append("| pool | measured_mean | null_mean | diff (measured-null) | T = null_mean + 0.15 |")
    lines.append("|---|---|---|---|---|")
    result_rows = (
        ("pooled", pooled),
        ("(a) sweep15", block_a),
        ("(b) recreated c39", block_b),
        ("(c) station draws", block_c),
    )
    for label, block in result_rows:
        lines.append(
            f"| {label} | {_fmt(block['measured_mean'])} | {_fmt(block['null_mean'])}"
            f" | {_fmt(block['diff'])} | {_fmt(block['T'])} |"
        )
    lines.append("")
    lines.append("Promotion requires diff > 0.15 pooled AND in each corpus (a)/(b)/(c) (AC-3.3).")
    lines.append("")
    lines.append("## Per-track Pearsons (measured, non-exempt in corpus order)")
    lines.append("")
    lines.append("| corpus | lane | seed | seconds | sections | exempt | pearson |")
    lines.append("|---|---|---|---|---|---|---|")
    for entry in report["per_track"]:
        pearson_text = "-" if entry["pearson"] is None else _fmt(float(entry["pearson"]))
        exempt_text = entry["exempt_reason"] if entry["exempt"] else "-"
        lines.append(
            f"| {entry['corpus']} | {entry['lane']} | {entry['seed']} | {entry['seconds']}"
            f" | {entry['section_count']} | {exempt_text} | {pearson_text} |"
        )
    lines.append("")
    lines.append("Worst measured Pearsons (non-exempt, ascending):")
    lines.append("")
    for entry in worst_tracks(report["per_track"]):
        lines.append(
            f"- ({entry['corpus']}) {entry['lane']} seed {entry['seed']} {entry['seconds']} s:"
            f" {_fmt(float(entry['pearson']))} ({entry['section_count']} sections)"
        )
    lines.append("")
    lines.append("## Verdict (AC-3.3 / AC-3.5)")
    lines.append("")
    lines.append(f"**{verdict['verdict']}**")
    lines.append("")
    lines.append(f"- Slice 2 attempted: {verdict['slice2_attempted']} ({verdict['slice2_note']})")
    for reason in verdict["reasons"]:
        lines.append(f"- {reason}")
    if verdict["verdict"] == "PROMOTE-ELIGIBLE":
        lines.append("- All four pools exceed the 0.15 margin; T10 may promote on this evidence.")
    lines.append("")
    lines.append("## Coupling and determinism")
    lines.append("")
    lines.append(
        "- `M` is the `tension_correlation` measured walk via validate private"
        " helpers (`_tension_pitched_notes`, `_pcm_section_millibels`,"
        " `_pcm_section_onsets`, `_carried_pitch_roughness`, `_measured_walk`)."
    )
    lines.append("- The only RNG in the harness is `np.random.default_rng(0)` (null only).")
    lines.append("- Outputs: `docs/handoff/c10-tension-gate.md` (this file) +")
    lines.append("  `docs/handoff/c10-tension-gate.json` (machine artifact).")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Render the full corpus, pool the null, and write both artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md", type=Path, default=DEFAULT_MD_PATH, help="markdown report path")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="JSON artifact path")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    cells = corpus_cells()
    tracks: list[Track] = []
    for index, cell in enumerate(cells):
        tracks.append(render_cell(cell))
        print(f"[{index + 1:>2}/{len(cells)}] ({cell.corpus}) {cell.lane} {cell.seed} {cell.seconds}s", flush=True)
    render_wall = time.perf_counter() - started
    report = summarize(tracks)
    wall_seconds = time.perf_counter() - started
    report["wall_seconds"] = wall_seconds
    report["render_wall_seconds"] = render_wall
    report["harness"] = "tools/c10_tension_gate.py"

    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.md.write_text(render_markdown(report, wall_seconds=wall_seconds), encoding="utf-8")
    print(f"wrote {args.md} and {args.json}", flush=True)
    print(f"verdict: {report['verdict']['verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
