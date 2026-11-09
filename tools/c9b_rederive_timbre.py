"""c9b timbre re-derive harness (issue #9b, Commit1 T1-T3).

Fit ONLY from sweep15 (tests/test_sweep.py:37-40): 5 lanes x seeds
(1042, 2000, 4002) at 240 s. The full corpus is 18 cells: sweep15 (15)
plus falsifier dub-electronic 1042 45 s and kosmische 1042 45 s plus
authority kosmische 1042 60 s (AC1.1). Falsifier/authority are hold-outs:
they never enter the fit.

Per-section centroid is gate 6's measurement verbatim
(src/indiegen/validate.py:476-497 per_second_centroid,
:804-818 _section_means, :821-841 timbre_measurement): per_second_centroid
on the render_plan pre-master mix with start_frame=plan.fade_in_frames,
then _section_means with start=_first_second(plan). Per-function value is
the duration-weighted mean over sweep15 sections with that function, the
weight being last-first per-second samples (:814-815), int round,
clamp >= 1 (AC1.2). section.function maps to the timbre key, but only
keys already in the lane's preset timbre map are written: motorik has 7
keys and no peak, so a motorik peak section is excluded, never invented
(planner.py:705-718 fallback). A function with zero sections keeps its
old value and is reported. Ambient is excluded from the fit entirely
(flat 560, presets/ambient.yaml:26-45, AC1.3/AC1.6); ambient.yaml is
never written.

YAML patch: only the ``timbre: {...}`` line changes, key order/shape
preserved (motorik 7 keys, the others 8). Run:

    python tools/c9b_rederive_timbre.py --mode fit          # sweep15, writes YAML + report
    python tools/c9b_rederive_timbre.py --mode falsifier    # hold-outs, no YAML, updates report
    python tools/c9b_rederive_timbre.py --mode full         # all 18, no YAML write

Outputs: docs/handoff/c9b-rederive.md and .json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from indiegen.compose import compose, director  # noqa: E402
from indiegen.config import load_preset  # noqa: E402
from indiegen.plan import Plan  # noqa: E402
from indiegen.render import render_plan  # noqa: E402
from indiegen.validate import (  # noqa: E402
    _first_second,
    _section_means,
    energy_correlation,
    per_second_centroid,
    timbre_measurement,
)

LANES: tuple[str, ...] = ("motorik", "kosmische", "dub-electronic", "indie-noise", "ambient")
"""Lane order of tests/test_sweep.py:37."""

SEEDS: tuple[int, ...] = (1042, 2000, 4002)
"""Sweep seeds of tests/test_sweep.py:38."""

SWEEP_SECONDS: int = 240
"""Sweep render length (tests/test_sweep.py:39)."""

RATE: int = 44100
"""Sample rate of every cell."""

FIT_LANES: tuple[str, ...] = ("motorik", "kosmische", "dub-electronic", "indie-noise")
"""Lanes whose timbre maps are fit. Ambient (flat 560) is excluded."""

EXCLUDED_LANES: tuple[str, ...] = ("ambient",)
"""Lanes rendered in the corpus but never fit."""

FALSIFIER_CELLS: tuple[tuple[str, int, int], ...] = (
    ("dub-electronic", 1042, 45),
    ("kosmische", 1042, 45),
)
"""Falsifier hold-outs (lane, seed, seconds), AC1.4."""

AUTHORITY_CELL: tuple[str, int, int] = ("kosmische", 1042, 60)
"""Authority hold-out (lane, seed, seconds), AC1.1."""

GATE5_FLOOR: float = 0.8858
"""Commit1 floor for dub 45 s gate 5 (baseline 0.90584 - 0.02)."""

GATE6_FLOOR: float = 0.6840
"""Commit1 floor for kosmische 45 s gate 6 (baseline 0.70398 - 0.02)."""

GATE5_BASELINE: float = 0.90584
"""Parent-verified pre-Commit1 baseline, dub 45 s gate 5."""

GATE6_BASELINE: float = 0.70398
"""Parent-verified pre-Commit1 baseline, kosmische 45 s gate 6."""

DEFAULT_MD_PATH: Path = _REPO_ROOT / "docs" / "handoff" / "c9b-rederive.md"
DEFAULT_JSON_PATH: Path = _REPO_ROOT / "docs" / "handoff" / "c9b-rederive.json"
PRESETS_DIR: Path = _REPO_ROOT / "presets"

_TIMBRE_RE = re.compile(r"^timbre: \{([^}]*)\}[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Cell:
    """One pinned corpus cell."""

    lane: str
    seed: int
    seconds: int
    role: str  # "fit" | "falsifier" | "authority"


@dataclass(frozen=True)
class Observation:
    """One section's measured centroid, its function and its weight."""

    lane: str
    seed: int
    seconds: int
    function: str
    centroid_hz: float
    weight: int  # per-second samples contributing (last-first)


def fit_cells() -> list[Cell]:
    """The 15 sweep cells that may enter the fit (test_sweep:37-40)."""
    return [Cell(lane=lane, seed=seed, seconds=SWEEP_SECONDS, role="fit") for lane in LANES for seed in SEEDS]


def holdout_cells() -> list[Cell]:
    """The 3 hold-out cells: 2 falsifiers + 1 authority."""
    cells = [Cell(lane=lane, seed=seed, seconds=seconds, role="falsifier") for lane, seed, seconds in FALSIFIER_CELLS]
    lane, seed, seconds = AUTHORITY_CELL
    cells.append(Cell(lane=lane, seed=seed, seconds=seconds, role="authority"))
    return cells


def corpus_cells() -> list[Cell]:
    """All 18 cells in corpus order: sweep15 then hold-outs (AC1.1)."""
    return fit_cells() + holdout_cells()


def section_weights(plan: Plan, measured_size: int) -> list[int]:
    """Duration weight (last-first) per section, as validate._section_means.

    Mirrors src/indiegen/validate.py:814-815 exactly: first/last are
    per-second indices of the section window relative to _first_second.
    """
    start_frame = _first_second(plan)
    rate = plan.sample_rate
    weights: list[int] = []
    for section in plan.sections:
        first = max(0, (section.start_frame - start_frame) // rate)
        last = min(measured_size, (section.end_frame - start_frame) // rate)
        weights.append(max(0, last - first))
    return weights


def measure_sections(plan: Plan, mix: np.ndarray) -> list[Observation]:
    """Per-section centroids via gate 6's measurement, with weights.

    The mix is the render_plan pre-master mix, exactly what
    timbre_measurement consumes (validate.py:821-841).
    """
    measured = per_second_centroid(mix, plan.sample_rate, plan.fade_in_frames)
    start = _first_second(plan)
    per_section = _section_means(plan, measured, start)
    weights = section_weights(plan, int(measured.size))
    # _section_means indexes by section.index; sections are in order.
    ordered = sorted(plan.sections, key=lambda s: s.index)
    out: list[Observation] = []
    for section, weight in zip(ordered, weights, strict=True):
        if weight <= 0:
            continue  # no per-second samples: cannot contribute (synthetic guard)
        out.append(
            Observation(
                lane=plan.lane,
                seed=plan.seed,
                seconds=plan.duration_frames // plan.sample_rate,
                function=section.function,
                centroid_hz=float(per_section[section.index]),
                weight=int(weight),
            )
        )
    return out


def aggregate_lane(
    observations: list[Observation],
    old_timbre: dict[str, int],
) -> dict[str, Any]:
    """Duration-weighted per-function fit for one lane (pure).

    Only keys in old_timbre are fitted/updated, in old order. Observed
    functions outside old_timbre (e.g. motorik peak) are excluded and
    reported, never invented. A key with zero total weight keeps its old
    value and is reported as kept_old. Values are int(round(mean)),
    clamp >= 1.
    """
    by_function: dict[str, list[Observation]] = {}
    excluded: dict[str, int] = {}
    for obs in observations:
        if obs.weight <= 0:
            continue
        if obs.function not in old_timbre:
            excluded[obs.function] = excluded.get(obs.function, 0) + 1
            continue
        by_function.setdefault(obs.function, []).append(obs)

    new_timbre: dict[str, int] = {}
    counts: dict[str, dict[str, int]] = {}
    kept_old: list[str] = []
    for key in old_timbre:
        obs_list = by_function.get(key, [])
        total_weight = sum(obs.weight for obs in obs_list)
        counts[key] = {"sections": len(obs_list), "weight": int(total_weight)}
        if not obs_list or total_weight <= 0:
            new_timbre[key] = int(old_timbre[key])
            kept_old.append(key)
            continue
        weighted = sum(obs.centroid_hz * obs.weight for obs in obs_list) / total_weight
        new_timbre[key] = max(1, int(round(float(weighted))))
    return {
        "old": dict(old_timbre),
        "new": new_timbre,
        "counts": counts,
        "kept_old": kept_old,
        "excluded_functions": excluded,
        "excluded_observations": sum(excluded.values()),
        "total_sections": sum(c["sections"] for c in counts.values()),
        "total_weight": sum(c["weight"] for c in counts.values()),
    }


def old_timbre_for(lane: str) -> dict[str, int]:
    """The lane's current preset timbre map, in file order."""
    preset = load_preset(lane)
    return dict(preset.lanes[0].parameters.timbre)


def fit_from_observations(
    observations: list[Observation],
) -> dict[str, dict[str, Any]]:
    """Fit every FIT_LANE from pooled observations; ambient never fit."""
    result: dict[str, dict[str, Any]] = {}
    for lane in FIT_LANES:
        lane_obs = [obs for obs in observations if obs.lane == lane]
        result[lane] = aggregate_lane(lane_obs, old_timbre_for(lane))
    return result


def parse_timbre_line(text: str) -> tuple[list[str], dict[str, int]]:
    """Keys in file order and values from the inline timbre map."""
    match = _TIMBRE_RE.search(text)
    if match is None:
        raise ValueError("no inline timbre: {...} line found")
    inner = match.group(1).strip()
    keys: list[str] = []
    values: dict[str, int] = {}
    if inner:
        for part in inner.split(","):
            item = part.strip()
            if not item:
                continue
            key, _, raw = item.partition(":")
            name = key.strip()
            keys.append(name)
            values[name] = int(raw.strip())
    return keys, values


def patch_preset_text(text: str, new_timbre: dict[str, int]) -> str:
    """Replace only the timbre line, preserving key order/shape.

    new_timbre must carry exactly the old keys in the old order; any
    other line (and any reordering) is a ValueError, so a caller cannot
    silently invent e.g. a motorik peak key.
    """
    keys, _old = parse_timbre_line(text)
    if list(new_timbre.keys()) != keys:
        raise ValueError(f"timbre keys/order mismatch: old {keys} vs new {list(new_timbre.keys())}")

    def _repl(match: re.Match[str]) -> str:
        inner = ", ".join(f"{key}: {int(new_timbre[key])}" for key in keys)
        return f"timbre: {{{inner}}}"

    patched, count = _TIMBRE_RE.subn(_repl, text, count=1)
    if count != 1:
        raise ValueError("expected exactly one timbre line")
    return patched


def patch_preset_file(path: Path, new_timbre: dict[str, int]) -> None:
    """Write the patched preset, timbre line only."""
    text = path.read_text(encoding="utf-8")
    path.write_text(patch_preset_text(text, new_timbre), encoding="utf-8")


def render_cell(cell: Cell) -> list[Observation]:
    """Render one cell through the in-memory test_sweep path (mix only)."""
    plan = director(compose(load_preset(cell.lane), cell.seed, cell.seconds * RATE))
    mix = render_plan(plan)
    return measure_sections(plan, mix)


def measure_falsifier(cell: Cell) -> dict[str, Any]:
    """Render one hold-out cell and measure its gate correlation.

    dub: energy_correlation(plan, mix) (2-arg, gate 5).
    kosmische: timbre_measurement(plan, mix)[0] (gate 6, first elem;
    a static plan returns variance as first elem - the caller must not
    read a static return as a correlation, but these lanes are not
    static so the first elem is the correlation).
    """
    plan = director(compose(load_preset(cell.lane), cell.seed, cell.seconds * RATE))
    mix = render_plan(plan)
    if cell.lane == "dub-electronic" and cell.role == "falsifier":
        value = float(energy_correlation(plan, mix))
        return {
            "lane": cell.lane,
            "seed": cell.seed,
            "seconds": cell.seconds,
            "role": cell.role,
            "gate": 5,
            "measured": value,
            "floor": GATE5_FLOOR,
            "baseline": GATE5_BASELINE,
            "pass": bool(value >= GATE5_FLOOR),
        }
    if cell.lane == "kosmische" and cell.role == "falsifier":
        correlation, static = timbre_measurement(plan, mix)
        value = float(correlation)
        return {
            "lane": cell.lane,
            "seed": cell.seed,
            "seconds": cell.seconds,
            "role": cell.role,
            "gate": 6,
            "measured": value,
            "floor": GATE6_FLOOR,
            "baseline": GATE6_BASELINE,
            "static": bool(static),
            "pass": bool((not static) and value >= GATE6_FLOOR),
        }
    # Authority (and any other) cell: report both correlations, no gate verdict.
    energy = float(energy_correlation(plan, mix))
    correlation, static = timbre_measurement(plan, mix)
    return {
        "lane": cell.lane,
        "seed": cell.seed,
        "seconds": cell.seconds,
        "role": cell.role,
        "gate5_energy": energy,
        "gate6_timbre": float(correlation),
        "gate6_static": bool(static),
    }


def decide_k1(falsifier: list[dict[str, Any]]) -> dict[str, Any]:
    """K1 verdict from falsifier dicts (pure): pass iff both floors pass."""
    by_gate = {entry.get("gate"): entry for entry in falsifier if "measured" in entry}
    gate5 = by_gate.get(5)
    gate6 = by_gate.get(6)
    passed = bool(gate5 and gate6 and gate5.get("pass") and gate6.get("pass"))
    return {
        "k1": "PASS" if passed else "FAIL",
        "gate5_measured": gate5.get("measured") if gate5 else None,
        "gate5_floor": GATE5_FLOOR,
        "gate5_pass": bool(gate5.get("pass")) if gate5 else False,
        "gate6_measured": gate6.get("measured") if gate6 else None,
        "gate6_floor": GATE6_FLOOR,
        "gate6_pass": bool(gate6.get("pass")) if gate6 else False,
    }


def _fmt_table(fit: dict[str, dict[str, Any]]) -> list[str]:
    lines = ["| lane | function | old | new | sections | weight (sec) |", "|---|---|---|---|---|---|"]
    for lane in FIT_LANES:
        block = fit[lane]
        for key in block["old"]:
            lines.append(
                f"| {lane} | {key} | {block['old'][key]} | {block['new'][key]} "
                f"| {block['counts'][key]['sections']} | {block['counts'][key]['weight']} |"
            )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    """The human-readable handoff document (fit, plus falsifier if present)."""
    lines: list[str] = []
    lines.append("# c9b timbre re-derive (issue #9b, Commit1)")
    lines.append("")
    lines.append("Fit ONLY from sweep15 (tests/test_sweep.py:37-40): 5 lanes x seeds (1042, 2000, 4002) x 240 s.")
    lines.append("Corpus is 18 cells: sweep15 (15) + falsifier dub-electronic 1042 45 s + kosmische 1042 45 s")
    lines.append("+ authority kosmische 1042 60 s (AC1.1). Falsifier/authority are hold-outs, never fit.")
    lines.append("")
    lines.append("Method (AC1.2): gate 6 measurement verbatim - validate.per_second_centroid on the")
    lines.append("render_plan pre-master mix (validate.py:476-497), validate._section_means (:804-818) with")
    lines.append("start=_first_second, per-function duration-weighted mean (weight = last-first :814-815),")
    lines.append("int round, clamp >= 1. section.function -> timbre key; only preset keys are written")
    lines.append("(motorik 7 keys, peak excluded, never invented). Zero-section functions keep old + report.")
    lines.append("Ambient excluded from fit (flat 560); ambient.yaml byte-identical (AC1.3/AC1.6).")
    lines.append("")
    if "fit_wall_seconds" in report:
        lines.append(f"- Fit wall time: {report['fit_wall_seconds']:.1f} s")
    lines.append(f"- Fit cells rendered: {report.get('fit_cells_rendered', '?')} (sweep15)")
    lines.append("- Corpus cells defined: 18 = sweep15 (15) + falsifier (2) + authority (1)")
    lines.append("")
    lines.append("## Old -> new timbre (fit lanes)")
    lines.append("")
    lines.extend(_fmt_table(report["fit"]))
    lines.append("")
    lines.append("## Section counts and kept-old / excluded")
    lines.append("")
    for lane in FIT_LANES:
        block = report["fit"][lane]
        lines.append(
            f"- {lane}: {block['total_sections']} sections, weight {block['total_weight']} s, "
            f"kept_old={block['kept_old']}, excluded_functions={block['excluded_functions']} "
            f"({block['excluded_observations']} observations)"
        )
    lines.append("- ambient: excluded from fit (flat 560), yaml untouched")
    lines.append("")
    if "falsifier" in report:
        lines.append("## Falsifier (hold-outs, post-patch preset)")
        lines.append("")
        lines.append("| lane | seed | seconds | gate | measured | floor | baseline | pass |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for entry in report["falsifier"]:
            if "measured" in entry:
                lines.append(
                    f"| {entry['lane']} | {entry['seed']} | {entry['seconds']} | {entry['gate']} "
                    f"| {entry['measured']:.5f} | {entry['floor']:.4f} | {entry['baseline']:.5f} | {entry['pass']} |"
                )
            else:
                lines.append(
                    f"| {entry['lane']} | {entry['seed']} | {entry['seconds']} | authority "
                    f"| gate5={entry.get('gate5_energy', float('nan')):.5f} "
                    f"gate6={entry.get('gate6_timbre', float('nan')):.5f} "
                    f"static={entry.get('gate6_static')} | - | - | - |"
                )
        lines.append("")
        k1 = report.get("k1", {})
        if k1:
            lines.append(
                f"**K1: {k1.get('k1')}** - gate5 {k1.get('gate5_measured')} vs floor {k1.get('gate5_floor')}, "
                f"gate6 {k1.get('gate6_measured')} vs floor {k1.get('gate6_floor')}."
            )
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Render the fit corpus, patch YAML (fit mode) and write both artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fit", "falsifier", "full"), default="fit")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD_PATH)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--no-write-yaml", action="store_true", help="fit/full: do not patch presets")
    args = parser.parse_args(argv)

    if args.mode == "falsifier":
        started = time.perf_counter()
        falsifier = [measure_falsifier(cell) for cell in holdout_cells()]
        verdict = decide_k1(falsifier)
        report: dict[str, Any] = {}
        if args.json.is_file():
            report = json.loads(args.json.read_text(encoding="utf-8"))
        report["falsifier"] = falsifier
        report["k1"] = verdict
        report["falsifier_wall_seconds"] = time.perf_counter() - started
        report["harness"] = "tools/c9b_rederive_timbre.py"
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        args.md.write_text(
            render_markdown(report) if "fit" in report else json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"falsifier: {falsifier}", flush=True)
        print(f"K1: {verdict['k1']}", flush=True)
        return 0

    cells = fit_cells() if args.mode == "fit" else corpus_cells()
    started = time.perf_counter()
    observations: list[Observation] = []
    fit_observations: list[Observation] = []
    rendered = 0
    for index, cell in enumerate(cells):
        obs = render_cell(cell)
        observations.extend(obs)
        if cell.role == "fit":
            fit_observations.extend(obs)
        rendered += 1
        print(
            f"[{index + 1:>2}/{len(cells)}] ({cell.role}) {cell.lane} {cell.seed} {cell.seconds}s "
            f"-> {len(obs)} sections",
            flush=True,
        )
    fit_wall = time.perf_counter() - started
    fit = fit_from_observations(fit_observations)
    if args.mode == "fit" and not args.no_write_yaml:
        for lane in FIT_LANES:
            patch_preset_file(PRESETS_DIR / f"{lane}.yaml", fit[lane]["new"])
            print(f"patched presets/{lane}.yaml", flush=True)
    report = {
        "fit": fit,
        "fit_cells_rendered": sum(1 for cell in cells if cell.role == "fit"),
        "corpus_cells_rendered": rendered,
        "corpus_cells_defined": len(corpus_cells()),
        "fit_wall_seconds": fit_wall,
        "mode": args.mode,
        "harness": "tools/c9b_rederive_timbre.py",
        "lanes": list(LANES),
        "fit_lanes": list(FIT_LANES),
        "seeds": list(SEEDS),
        "sweep_seconds": SWEEP_SECONDS,
        "gate5_floor": GATE5_FLOOR,
        "gate6_floor": GATE6_FLOOR,
        # per-section ledger for the audit trail (lane/seed/function/value/weight)
        "observations": [
            {
                "lane": o.lane,
                "seed": o.seed,
                "seconds": o.seconds,
                "function": o.function,
                "centroid_hz": o.centroid_hz,
                "weight": o.weight,
            }
            for o in observations
        ],
    }
    if args.mode == "full":
        falsifier = [measure_falsifier(cell) for cell in holdout_cells()]
        report["falsifier"] = falsifier
        report["k1"] = decide_k1(falsifier)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.md} and {args.json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
