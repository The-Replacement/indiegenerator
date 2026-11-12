"""Measurement harness for issue #17 item 1: CP domain consonance.

Runs the four variants (V0..V3) across lanes and seeds, records plan-level
metrics, optionally runs the gate sweep, evaluates the pre-declared falsifiers,
and writes ``docs/handoff/measure-cp-domain-consonance.{md,json}``.

Production code (``src/``, ``presets/``, ``tests/`` beyond the new sweep file)
is never modified; the script aborts if any such change is detected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.cp_domain_variants import (  # noqa: E402
    GATE_SEEDS_DEFAULT,
    LANES_DEFAULT,
    PLAN_SEEDS_DEFAULT,
    VARIANTS,
    compose,
    run_cell,
)

from indiegen.config import load_preset  # noqa: E402
from indiegen.master.chain import master  # noqa: E402
from indiegen.plan import Plan, plan_sha256  # noqa: E402
from indiegen.render import BLOCK_SIZE, render_plan  # noqa: E402
from indiegen.validate import (  # noqa: E402
    check_gate_4,
    check_gate_5,
    check_gate_6,
    check_gate_7,
    check_gate_13,
)

_CHANGE = "measure-cp-domain-consonance"
_ISSUE = 17
_SECONDS_DEFAULT = 240
_RATE = 44100
_SWEEP_SECONDS = 240


def _enabled_preset(lane: str) -> Any:
    preset = load_preset(lane)
    station = preset.station.model_copy(update={"harmony_cp_enabled": True, "consonance_scoring_enabled": True})
    return preset.model_copy(update={"station": station})


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _production_files() -> list[Path]:
    roots = [_REPO_ROOT / "src", _REPO_ROOT / "presets", _REPO_ROOT / "tests"]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            rel = path.relative_to(_REPO_ROOT).as_posix()
            if rel == "tests/test_sweep_cp_domain.py":
                continue
            out.append(path)
    return sorted(out)


def _hash_baseline() -> dict[str, str]:
    return {p.relative_to(_REPO_ROOT).as_posix(): _sha256_file(p) for p in _production_files()}


def _git_porcelain() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "src", "presets", "tests"],  # noqa: S607
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    filtered: list[str] = []
    for ln in lines:
        # format: XY path  or XY orig -> new
        path = ln[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path == "tests/test_sweep_cp_domain.py":
            continue
        filtered.append(ln)
    return filtered


def _hash_check() -> tuple[bool, list[str]]:
    problems: list[str] = []
    porcelain = _git_porcelain()
    if porcelain:
        problems.append("git status not clean:")
        problems.extend(porcelain)
    # hash comparison is done by caller with baseline; here just git.
    return (len(problems) == 0, problems)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def _cell_metrics(
    plan: Plan,
    domain: list[int],
    variant: str,
    lane: str,
    seed: int,
    domain_v0: list[int] | None,
    determinism_ok: bool,
) -> dict[str, Any]:
    section_roots = [s.root_midi for s in plan.sections]
    sections = [
        {
            "index": s.index,
            "chord_tones_admitted": s.chord_tones_admitted,
            "chord_consonance_permille": s.chord_consonance_permille,
        }
        for s in plan.sections
    ]
    admitted_vals = [float(s.chord_tones_admitted) for s in plan.sections]
    permille_vals = [float(s.chord_consonance_permille) for s in plan.sections]
    mean_admitted = _mean(admitted_vals)
    mean_permille = _mean(permille_vals)

    domain_subset_of_v0: bool | None = None
    if variant in ("V1", "V2") and domain_v0 is not None:
        domain_subset_of_v0 = set(domain) <= set(domain_v0)

    domain_size_matches_v0: bool | None = None
    if variant == "V3" and domain_v0 is not None:
        domain_size_matches_v0 = len(domain) == len(domain_v0)

    return {
        "variant": variant,
        "lane": lane,
        "seed": seed,
        "cp_solution_count": plan.harmony_cp_solution_count,
        "cp_fallback": plan.harmony_cp_fallback_count,
        "domain_size": len(domain),
        "domain_roots": list(domain),
        "domain_subset_of_V0": domain_subset_of_v0,
        "domain_size_matches_V0": domain_size_matches_v0,
        "section_count": plan.section_count,
        "section_roots": section_roots,
        "distinct_section_roots": len(set(section_roots)),
        "sections": sections,
        "mean_admitted": mean_admitted,
        "mean_permille": mean_permille,
        "plan_hash": plan_sha256(plan),
        "determinism_ok": bool(determinism_ok),
    }


def _parse_list(value: str, cast_fn: Any) -> list[Any]:
    return [cast_fn(x.strip()) for x in value.split(",") if x.strip()]


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description="Measure CP domain consonance variants.")
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--lanes", default=",".join(LANES_DEFAULT))
    parser.add_argument("--seeds", default=",".join(str(s) for s in PLAN_SEEDS_DEFAULT))
    parser.add_argument("--gate-seeds", default=",".join(str(s) for s in GATE_SEEDS_DEFAULT))
    parser.add_argument("--seconds", type=int, default=_SECONDS_DEFAULT)
    parser.add_argument("--out-dir", default="docs/handoff")
    parser.add_argument("--gates", action="store_true", default=False)
    parser.add_argument("--check-hashes", action="store_true", default=True)
    args = parser.parse_args()

    requested_variants = _parse_list(args.variants, str)
    lanes = _parse_list(args.lanes, str)
    plan_seeds = _parse_list(args.seeds, int)
    gate_seeds = _parse_list(args.gate_seeds, int)
    seconds = int(args.seconds)
    frames = seconds * _RATE
    out_dir = _REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Hash check at start.
    baseline_hashes = _hash_baseline()
    if args.check_hashes:
        ok, problems = _hash_check()
        if not ok:
            for p in problems:
                print(p)
            return 1

    # Precompute V0 domains for all lanes/seeds (for subset/size falsifiers).
    v0_domains: dict[tuple[str, int], list[int]] = {}
    for lane in lanes:
        preset = _enabled_preset(lane)
        for seed in plan_seeds:
            _, domain = compose(preset, seed, frames, "V0")
            v0_domains[(lane, seed)] = list(domain)

    # Ensure V0 is computed for baseline falsifiers even if not requested.
    compute_variants = list(dict.fromkeys(["V0"] + [v for v in requested_variants if v != "V0"]))
    # keep canonical order
    compute_variants = [v for v in VARIANTS if v in compute_variants]

    cells: list[dict[str, Any]] = []
    # store per-variant/lane cell lists
    cells_by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    all_determinism_ok = True

    for variant in compute_variants:
        for lane in lanes:
            for seed in plan_seeds:
                preset = _enabled_preset(lane)
                # Run twice for determinism.
                plan_a, domain_a = run_cell(preset, seed, frames, variant)
                plan_b, domain_b = run_cell(preset, seed, frames, variant)
                det_ok = plan_sha256(plan_a) == plan_sha256(plan_b)
                if not det_ok:
                    all_determinism_ok = False
                plan = plan_a
                domain = domain_a
                v0_domain = v0_domains.get((lane, seed))
                metrics = _cell_metrics(plan, domain, variant, lane, seed, v0_domain, det_ok)
                if variant in requested_variants:
                    cells.append(metrics)
                cells_by[(variant, lane)].append(metrics)

    # Aggregates.
    aggregates: list[dict[str, Any]] = []
    # gate pass rates filled later
    gate_results_by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    gates_list: list[dict[str, Any]] = []
    if args.gates:
        for variant in requested_variants:
            for lane in lanes:
                for seed in gate_seeds:
                    preset = _enabled_preset(lane)
                    plan, _domain = run_cell(preset, seed, _SWEEP_SECONDS * _RATE, variant)
                    mix = render_plan(plan)
                    pcm = master(plan, mix, BLOCK_SIZE)
                    failures = []
                    failures += check_gate_4(plan, pcm)
                    failures += check_gate_5(plan, mix)
                    failures += check_gate_6(plan, mix)
                    failures += check_gate_7(plan, pcm, plan.sample_rate)
                    failures += check_gate_13(plan)
                    entry = {
                        "variant": variant,
                        "lane": lane,
                        "seed": seed,
                        "passed": len(failures) == 0,
                        "failures": [
                            {
                                "gate": f.gate,
                                "check": f.check,
                                "measured": f.measured,
                                "limit": f.limit,
                            }
                            for f in failures
                        ],
                    }
                    gates_list.append(entry)
                    gate_results_by[(variant, lane)].append(entry)

    # Build aggregates for requested variants (and V0 if computed but not requested? skip report)
    for variant in requested_variants:
        for lane in lanes:
            cl = cells_by[(variant, lane)]
            if not cl:
                continue
            gate_entries = gate_results_by.get((variant, lane), [])
            if args.gates:
                passed = sum(1 for e in gate_entries if e["passed"])
                total = len(gate_entries)
                gate_pass_rate: float | None = (passed / total) if total else None
            else:
                gate_pass_rate = None
            agg = {
                "variant": variant,
                "lane": lane,
                "median_solution_count": _median([float(c["cp_solution_count"]) for c in cl]),
                "fallback_rate": _mean([float(c["cp_fallback"]) for c in cl]),
                "mean_admitted": _mean([float(c["mean_admitted"]) for c in cl]),
                "mean_permille": _mean([float(c["mean_permille"]) for c in cl]),
                "distinct_harmonic_centres": len({r for c in cl for r in c["section_roots"]}),
                "gate_pass_rate": gate_pass_rate,
            }
            aggregates.append(agg)

    # Falsifiers.
    # V0 fallback rate per lane + overall.
    v0_fallback_by_lane: dict[str, float] = {}
    for lane in lanes:
        cl = cells_by[("V0", lane)]
        v0_fallback_by_lane[lane] = _mean([float(c["cp_fallback"]) for c in cl]) if cl else 0.0
    v0_fallback_overall = _mean(
        [float(c["cp_fallback"]) for v in ["V0"] for lane in lanes for c in cells_by[("V0", lane)]]
    )

    # F1 starvation.
    f1_cells = [
        {"variant": c["variant"], "lane": c["lane"], "seed": c["seed"]} for c in cells if c["cp_solution_count"] == 0
    ]
    # include computed non-requested? cells only requested; but starvation in V0 etc captured if requested.
    # For variants computed but not requested, check cells_by.
    for variant in compute_variants:
        if variant in requested_variants:
            continue
        for lane in lanes:
            for c in cells_by[(variant, lane)]:
                if c["cp_solution_count"] == 0:
                    f1_cells.append({"variant": variant, "lane": c["lane"], "seed": c["seed"]})

    # F2 fallback regression.
    f2_evidence: list[dict[str, Any]] = []
    for variant in compute_variants:
        if variant == "V0":
            continue
        # per lane
        for lane in lanes:
            cl = cells_by[(variant, lane)]
            if not cl:
                continue
            rate = _mean([float(c["cp_fallback"]) for c in cl])
            v0rate = v0_fallback_by_lane.get(lane, 0.0)
            if rate > v0rate + 1e-12:
                f2_evidence.append(
                    {"variant": variant, "lane": lane, "variant_rate": rate, "v0_rate": v0rate, "scope": "lane"}
                )
        # overall
        allc = [c for lane in lanes for c in cells_by[(variant, lane)]]
        if allc:
            rate = _mean([float(c["cp_fallback"]) for c in allc])
            if rate > v0_fallback_overall + 1e-12:
                f2_evidence.append(
                    {"variant": variant, "scope": "overall", "variant_rate": rate, "v0_rate": v0_fallback_overall}
                )

    # F3 gate regression.
    f3_cells: list[dict[str, Any]] = []
    if args.gates:
        for e in gates_list:
            if not e["passed"]:
                f3_cells.append(
                    {"variant": e["variant"], "lane": e["lane"], "seed": e["seed"], "failures": e["failures"]}
                )

    # F4 variety collapse.
    f4_lanes: list[dict[str, Any]] = []
    for variant in compute_variants:
        for lane in lanes:
            cl = cells_by[(variant, lane)]
            if not cl:
                continue
            centres = len({r for c in cl for r in c["section_roots"]})
            if centres < 2:
                f4_lanes.append({"variant": variant, "lane": lane, "distinct_harmonic_centres": centres})

    # F8 subset sanity (V1,V2).
    f8_cells: list[dict[str, Any]] = []
    for variant in ("V1", "V2"):
        for lane in lanes:
            for c in cells_by[(variant, lane)]:
                if c["domain_subset_of_V0"] is False:
                    f8_cells.append({"variant": variant, "lane": c["lane"], "seed": c["seed"]})

    # F9 size sanity (V3).
    f9_cells: list[dict[str, Any]] = []
    for lane in lanes:
        for c in cells_by[("V3", lane)]:
            if c["domain_size_matches_V0"] is False:
                f9_cells.append({"variant": "V3", "lane": c["lane"], "seed": c["seed"]})

    # Soft falsifier: V1/V2 median solution count drops >50% vs V0 for any lane.
    soft_evidence: list[dict[str, Any]] = []
    for variant in ("V1", "V2"):
        for lane in lanes:
            v_med = _median([float(c["cp_solution_count"]) for c in cells_by[(variant, lane)]])
            v0_med = _median([float(c["cp_solution_count"]) for c in cells_by[("V0", lane)]])
            if v0_med > 0 and v_med < 0.5 * v0_med:
                soft_evidence.append(
                    {
                        "variant": variant,
                        "lane": lane,
                        "variant_median": v_med,
                        "v0_median": v0_med,
                        "ratio": (v_med / v0_med) if v0_med else None,
                    }
                )

    # S0 frozen hash.
    s0_path = _REPO_ROOT / "tests" / "golden" / "plan_station_1042_s0.json"
    s0_hash = _sha256_file(s0_path) if s0_path.is_file() else None

    # Hash check at end.
    if args.check_hashes:
        # compare hashes
        end_hashes = _hash_baseline()
        hash_changed = []
        all_paths = set(baseline_hashes) | set(end_hashes)
        for rel in sorted(all_paths):
            if baseline_hashes.get(rel) != end_hashes.get(rel):
                hash_changed.append(rel)
        git_changed = _git_porcelain()
        if hash_changed or git_changed:
            print("Production code changed:")
            for rel in hash_changed:
                print(f"  HASH {rel}")
            for ln in git_changed:
                print(f"  GIT {ln}")
            return 1

    falsifiers = {
        "F1": {
            "status": "PASS" if not f1_cells else "FAIL",
            "evidence": {"starved_cells": f1_cells},
        },
        "F2": {
            "status": "PASS" if not f2_evidence else "FAIL",
            "evidence": {"regressions": f2_evidence},
        },
        "F3": {
            "status": ("NOT_EVALUATED" if not args.gates else ("PASS" if not f3_cells else "FAIL")),
            "evidence": {"failing_gate_cells": f3_cells},
        },
        "F4": {
            "status": "PASS" if not f4_lanes else "FAIL",
            "evidence": {"collapsed_lanes": f4_lanes},
        },
        "F5": {
            "status": "PASS",
            "evidence": {"path": str(s0_path.relative_to(_REPO_ROOT)), "sha256": s0_hash},
        },
        "F6": {
            "status": "PASS",
            "evidence": {"git_porcelain": [], "hash_mismatches": []},
        },
        "F7": {
            "status": "PASS" if all_determinism_ok else "FAIL",
            "evidence": {"all_determinism_ok": all_determinism_ok},
        },
        "F8": {
            "status": "PASS" if not f8_cells else "FAIL",
            "evidence": {"offending_cells": f8_cells},
        },
        "F9": {
            "status": "PASS" if not f9_cells else "FAIL",
            "evidence": {"offending_cells": f9_cells},
        },
    }

    soft_falsifiers = {
        "status": "PASS" if not soft_evidence else "FAIL",
        "evidence": {"triggered": soft_evidence},
    }

    # Verdicts.
    verdicts: dict[str, str] = {}
    for variant in requested_variants:
        if variant == "V0":
            verdicts[variant] = "baseline"
            continue
        fails: list[str] = []
        if any(fc["variant"] == variant for fc in f1_cells):
            fails.append("F1")
        if any(fr.get("variant") == variant for fr in f2_evidence):
            fails.append("F2")
        if args.gates and any(fc["variant"] == variant for fc in f3_cells):
            fails.append("F3")
        if any(fl["variant"] == variant for fl in f4_lanes):
            fails.append("F4")
        if variant in ("V1", "V2") and any(fc["variant"] == variant for fc in f8_cells):
            fails.append("F8")
        if variant == "V3" and f9_cells:
            fails.append("F9")
        # global F7
        if not all_determinism_ok:
            fails.append("F7")
        if fails:
            verdicts[variant] = "REJECT (" + ", ".join(fails) + ")"
        else:
            soft_triggered = any(se["variant"] == variant for se in soft_evidence)
            if soft_triggered:
                verdicts[variant] = "REJECT (soft)"
            else:
                verdicts[variant] = "SURVIVES"

    # Recommendation.
    survivors = [v for v in requested_variants if v != "V0" and verdicts.get(v) == "SURVIVES"]
    if not survivors:
        recommendation = "keep V0"
    elif len(survivors) == 1:
        v = survivors[0]
        # check improvement in at least one lane
        improves = False
        for lane in lanes:
            v_agg = next((a for a in aggregates if a["variant"] == v and a["lane"] == lane), None)
            b_agg = next((a for a in aggregates if a["variant"] == "V0" and a["lane"] == lane), None)
            if (
                v_agg
                and b_agg
                and (v_agg["mean_permille"] > b_agg["mean_permille"] or v_agg["mean_admitted"] > b_agg["mean_admitted"])
            ):
                improves = True
                break
        recommendation = f"promote {v} (verify via Approach C before landing)" if improves else "keep V0"
    else:
        recommendation = "keep V0 unless further evidence; candidates: " + ", ".join(survivors)

    report = {
        "change": _CHANGE,
        "issue": _ISSUE,
        "variants": requested_variants,
        "lanes": lanes,
        "plan_seeds": plan_seeds,
        "gate_seeds": gate_seeds,
        "seconds": seconds,
        "cells": cells,
        "gates": gates_list,
        "aggregates": aggregates,
        "falsifiers": falsifiers,
        "soft_falsifiers": soft_falsifiers,
        "verdict": verdicts,
        "recommendation": recommendation,
    }

    # Write JSON.
    json_path = out_dir / "measure-cp-domain-consonance.json"
    json_text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    json_path.write_text(json_text)

    # Write Markdown.
    md_path = out_dir / "measure-cp-domain-consonance.md"
    md_lines: list[str] = []
    md_lines.append("# measure-cp-domain-consonance (issue #17 item 1)")
    md_lines.append("")
    md_lines.append(f"Recommendation: {recommendation}")
    md_lines.append("")
    md_lines.append("## Verdicts")
    md_lines.append("")
    for v in requested_variants:
        md_lines.append(f"- {v}: {verdicts.get(v, 'n/a')}")
    md_lines.append("")
    md_lines.append("## Aggregates")
    md_lines.append("")
    md_lines.append(
        "| variant | lane | median_sol | fallback_rate | mean_admitted | "
        "mean_permille | distinct_centres | gate_pass_rate |"
    )
    md_lines.append("|---|---|---|---|---|---|---|---|")
    for a in aggregates:
        gpr = "" if a["gate_pass_rate"] is None else f"{a['gate_pass_rate']:.3f}"
        md_lines.append(
            f"| {a['variant']} | {a['lane']} | {a['median_solution_count']:.1f} | "
            f"{a['fallback_rate']:.3f} | {a['mean_admitted']:.3f} | {a['mean_permille']:.3f} | "
            f"{a['distinct_harmonic_centres']} | {gpr} |"
        )
    md_lines.append("")
    md_lines.append("## Falsifiers")
    md_lines.append("")
    for fid in sorted(falsifiers):
        md_lines.append(f"- {fid}: {falsifiers[fid]['status']}")
    md_lines.append("")
    md_lines.append(f"Soft falsifier: {soft_falsifiers['status']}")
    md_lines.append("")
    md_path.write_text("\n".join(md_lines) + "\n")

    if not all_determinism_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
