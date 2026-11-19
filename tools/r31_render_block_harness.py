"""Reproducible RENDER_BLOCK measurement harness (issue #31).

One file, two modes:

* controller (default): owns the cell matrix, spawns a FRESH process per cell,
  applies the pre-declared decision predicate and writes the artifacts.
* worker (``--worker``): injects ``indiegen.render.RENDER_BLOCK`` before any
  render call, renders one cell through ``indiegen.cli._render`` and emits one
  JSON line with wall time, peak RSS and the two hashes.

The METHOD string below is fixed and is emitted verbatim into every artifact.
No other measurement tool, conversion path or historical README column is
used as data.

Usage:
    .venv/bin/python tools/r31_render_block_harness.py --dry
    .venv/bin/python tools/r31_render_block_harness.py --selftest
    .venv/bin/python tools/r31_render_block_harness.py \
        --out-json docs/perf/r31-render-block.json \
        --out-md docs/perf/r31-render-block.md
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

METHOD = (
    "One method for all sizes: stdlib resource.getrusage (RUSAGE_SELF.ru_maxrss, with "
    "RUSAGE_CHILDREN.ru_maxrss as a fresh-process cross-check) + time.perf_counter. "
    "One fresh OS process per cell, because ru_maxrss is a high-water mark. "
    "peak_mb = ru_maxrss_kib / 1024 (Linux KiB). The worker sets "
    "indiegen.render.RENDER_BLOCK = N before calling indiegen.cli._render(preset, seed, "
    "None, seconds, out_dir, None, None) with the c29 values (ambient/1042/900 and "
    "motorik/1042/480). /usr/bin/time is not installed and is not substituted. "
    "Historical README columns measured with a different tool are never used as data."
)

SIZES: tuple[int, ...] = (131072, 32768, 16384)
CANDIDATES: tuple[int, ...] = (32768, 16384)
CELLS: tuple[tuple[str, int, int], ...] = (("ambient", 1042, 900), ("motorik", 1042, 480))
HARD_WALL_S = 180.0
HARD_PEAK_MB = 1500.0
SOFT_WALL_S = 171.0
SOFT_PEAK_MB = 1425.0
WIN_FRACTION = 0.95
MAX_ATTEMPTS = 3


def peak_mb(kib: int) -> float:
    """The one KiB -> MB conversion (Linux ru_maxrss is in KiB)."""
    return kib / 1024


@dataclass(frozen=True)
class CellResult:
    """One fresh-process measurement, or the reason it was discarded."""

    size: int
    preset: str
    seed: int
    seconds: int
    wall_s: float
    peak_kib: int
    plan_sha256: str
    pcm_sha256: str
    render_seconds: float
    exit_code: int
    error: str = ""
    controller_wall_s: float = 0.0
    children_high_water_kib: int = 0
    attempt: int = 1
    valid: bool = True
    reason: str = ""


@dataclass(frozen=True)
class Verdict:
    """The pure output of the decision gate."""

    choice: Literal["A", "B", "BISECT"]
    size: int | None = None
    midpoint: int | None = None
    survivors: tuple[int, ...] = ()
    breaches: tuple[int, ...] = ()
    note: str = ""


def worker(size: int, preset: str, seed: int, seconds: int, out_dir: Path) -> int:
    """Render one cell in THIS process and print exactly one JSON line."""
    exit_code = 0
    error = ""
    plan_sha256 = ""
    pcm_sha256 = ""
    render_seconds = -1.0
    wall_s = 0.0
    try:
        import indiegen.render as render_module

        render_module.RENDER_BLOCK = size
        import indiegen.cli as cli

        captured = io.StringIO()
        started = time.perf_counter()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            cli._render(preset, seed, None, seconds, out_dir, None, None)
        wall_s = time.perf_counter() - started
        for line in captured.getvalue().splitlines():
            if line.startswith("plan_sha256: "):
                plan_sha256 = line.split(": ", 1)[1]
            elif line.startswith("pcm_sha256: "):
                pcm_sha256 = line.split(": ", 1)[1]
            elif line.startswith("render_seconds: "):
                render_seconds = float(line.split(": ", 1)[1])
    except Exception as exc:  # typer.Exit(code=2) is an Exception; it carries exit_code
        exit_code = int(getattr(exc, "exit_code", 1) or 1)
        error = f"{type(exc).__name__}: {exc}"[:300]

    peak_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    record = {
        "size": size,
        "preset": preset,
        "seed": seed,
        "seconds": seconds,
        "wall_s": round(wall_s, 6),
        "peak_kib": peak_kib,
        "plan_sha256": plan_sha256,
        "pcm_sha256": pcm_sha256,
        "render_seconds": render_seconds,
        "exit_code": exit_code,
        "error": error,
    }
    print(json.dumps(record))
    return 0


def parse_worker_line(stdout: str) -> dict[str, object]:
    """The worker's JSON line is the last stdout line starting with '{'."""
    for line in reversed(stdout.splitlines()):
        if line.startswith("{"):
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                return loaded
    return {}


def run_cell(size: int, preset: str, seed: int, seconds: int, base: Path, attempt: int) -> CellResult:
    """Spawn one fresh process for one cell; never reuse a worker."""
    out_dir = base / f"s{size}-{preset}-{seconds}-a{attempt}"
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--size",
        str(size),
        "--preset",
        preset,
        "--seed",
        str(seed),
        "--seconds",
        str(seconds),
        "--out",
        str(out_dir),
    ]
    started = time.perf_counter()
    process = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    controller_wall = time.perf_counter() - started
    children_kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    data = parse_worker_line(process.stdout)

    plan_sha256 = str(data.get("plan_sha256", ""))
    pcm_sha256 = str(data.get("pcm_sha256", ""))
    wall_s = float(data.get("wall_s", 0.0))
    peak_kib = int(data.get("peak_kib", 0))
    reasons: list[str] = []
    if process.returncode != 0:
        reasons.append(f"worker_returncode={process.returncode}")
    if int(data.get("exit_code", 1)) != 0:
        reasons.append(f"render_exit={data.get('exit_code')}")
    if not plan_sha256:
        reasons.append("missing plan_sha256")
    if not pcm_sha256:
        reasons.append("missing pcm_sha256")
    if wall_s <= 0:
        reasons.append("missing wall_s")
    if peak_kib > children_kib:
        reasons.append("self peak exceeds RUSAGE_CHILDREN high-water")

    return CellResult(
        size=size,
        preset=preset,
        seed=seed,
        seconds=seconds,
        wall_s=wall_s,
        peak_kib=peak_kib,
        plan_sha256=plan_sha256,
        pcm_sha256=pcm_sha256,
        render_seconds=float(data.get("render_seconds", -1.0)),
        exit_code=int(data.get("exit_code", 1)),
        error=str(data.get("error", "")),
        controller_wall_s=round(controller_wall, 6),
        children_high_water_kib=children_kib,
        attempt=attempt,
        valid=not reasons,
        reason="; ".join(reasons),
    )


def cells_of(cells: list[CellResult], size: int) -> dict[int, CellResult]:
    """Index the (valid) cells of one size by duration."""
    return {cell.seconds: cell for cell in cells if cell.size == size and cell.valid}


def complete(cells: list[CellResult], size: int) -> bool:
    """A size is complete when its 900 s and 480 s cells are both valid."""
    found = cells_of(cells, size)
    return 900 in found and 480 in found


def budget_breach(cell: CellResult) -> bool:
    """A hard-budget breach.

    The 180 s wall budget belongs to the 480 s pulsed cell only; the 900 s
    longform's budget is RSS (c29 measured 268.9 s / 1263 MB for it). The
    1500 MB ceiling applies to both cells.
    """
    if peak_mb(cell.peak_kib) >= HARD_PEAK_MB:
        return True
    return cell.seconds == 480 and cell.wall_s >= HARD_WALL_S


def is_baseline_breach(cells: list[CellResult]) -> bool:
    """Baseline itself at or over a hard budget: no size can be safely lowered."""
    found = cells_of(cells, SIZES[0])
    if not complete(cells, SIZES[0]):
        return False
    return any(budget_breach(cell) for cell in found.values())


def survives(size: int, cells: list[CellResult]) -> bool:
    """The pre-declared 5%-headroom + no-breach + >=5%-win predicate."""
    if size == SIZES[0] or not complete(cells, size) or not complete(cells, SIZES[0]):
        return False
    found = cells_of(cells, size)
    base = cells_of(cells, SIZES[0])
    ambient = found[900]
    motorik = found[480]
    if any(budget_breach(cell) for cell in found.values()):
        return False
    if motorik.wall_s > SOFT_WALL_S or peak_mb(ambient.peak_kib) > SOFT_PEAK_MB:
        return False
    return motorik.wall_s <= WIN_FRACTION * base[480].wall_s or peak_mb(ambient.peak_kib) <= WIN_FRACTION * peak_mb(
        base[900].peak_kib
    )


def breaches(size: int, cells: list[CellResult]) -> bool:
    """True if any valid cell of this size hits a hard budget."""
    return any(budget_breach(cell) for cell in cells_of(cells, size).values())


def decide(cells: list[CellResult]) -> Verdict:
    """Pure decision: B at the largest survivor, A otherwise, BISECT on a breach."""
    if is_baseline_breach(cells):
        return Verdict(
            choice="A",
            note="Baseline 131072 is at or over a hard budget (180 s / 1500 MB); no size can be safely lowered.",
        )
    survivors = tuple(size for size in CANDIDATES if survives(size, cells))
    if survivors:
        return Verdict(choice="B", size=max(survivors), survivors=survivors)
    breached = tuple(size for size in CANDIDATES if breaches(size, cells))
    if breached:
        passing = [size for size in (SIZES[0], *CANDIDATES) if complete(cells, size) and not breaches(size, cells)]
        last_passing = min(passing) if passing else SIZES[0]
        first_failing = min(breached)
        if first_failing < last_passing:
            midpoint = (last_passing + first_failing) // 2
            return Verdict(choice="BISECT", midpoint=midpoint, breaches=breached)
    return Verdict(
        choice="A",
        breaches=breached,
        note="No candidate both stays inside the 171 s / 1425 MB headroom and improves the baseline by >=5%.",
    )


def finalize(cells: list[CellResult], bisection: list[CellResult]) -> Verdict:
    """Resolve the one allowed bisection midpoint, then decide once more."""
    verdict = decide(cells)
    if verdict.choice != "BISECT" or not bisection:
        return verdict
    combined = [*cells, *bisection]
    midpoint_survives = survives(verdict.midpoint or 0, combined)
    if midpoint_survives:
        return Verdict(
            choice="B",
            size=verdict.midpoint,
            survivors=(verdict.midpoint,),
            note=f"Bisection midpoint {verdict.midpoint} passed the same predicate.",
        )
    return Verdict(
        choice="A",
        breaches=verdict.breaches,
        note=f"Bisection midpoint {verdict.midpoint} failed the same predicate; no size is lowered.",
    )


def record_dict(cell: CellResult) -> dict[str, object]:
    data = asdict(cell)
    data["peak_mb"] = round(peak_mb(cell.peak_kib), 3)
    return data


def build_artifact(cells: list[CellResult], bisection: list[CellResult], verdict: Verdict) -> dict[str, object]:
    return {
        "method": METHOD,
        "sizes": list(SIZES),
        "cells": [record_dict(cell) for cell in cells],
        "bisection": [record_dict(cell) for cell in bisection],
        "decision": {
            "choice": verdict.choice,
            "size": verdict.size,
            "midpoint": verdict.midpoint,
            "survivors": list(verdict.survivors),
            "breaches": list(verdict.breaches),
            "note": verdict.note,
        },
    }


def from_record(item: dict[str, object]) -> CellResult:
    """Rebuild a cell from its JSON record, dropping the derived peak_mb key."""
    values = {key: value for key, value in item.items() if key != "peak_mb"}
    return CellResult(**values)  # type: ignore[arg-type]


def render_markdown(artifact: dict[str, object]) -> str:
    """Render the human table from the JSON records only."""
    cells = [from_record(item) for item in artifact["cells"]]  # type: ignore[arg-type]
    bisection = [from_record(item) for item in artifact["bisection"]]  # type: ignore[arg-type]
    verdict_dict = artifact["decision"]  # type: ignore[assignment]
    lines = [
        "# RENDER_BLOCK measurement (issue #31)",
        "",
        "## Method",
        "",
        f"{METHOD}",
        "",
        "One fresh OS process per cell; baseline first (131072, 32768, 16384).",
        "",
        "## Measured cells",
        "",
        "| size | ambient 900 wall_s | ambient 900 peak_mb | motorik 480 wall_s | motorik 480 peak_mb | survives |",
        "|---:|---:|---:|---:|---:|:---|",
    ]
    for size in list(SIZES) + sorted({cell.size for cell in bisection}):
        found = cells_of([*cells, *bisection], size)
        if 900 not in found or 480 not in found:
            continue
        lines.append(
            f"| {size} | {found[900].wall_s:.3f} | {peak_mb(found[900].peak_kib):.1f} | "
            f"{found[480].wall_s:.3f} | {peak_mb(found[480].peak_kib):.1f} | "
            f"{'yes' if survives(size, [*cells, *bisection]) else 'no'} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        f"- choice: {verdict_dict['choice']}",
        f"- adopted size: {verdict_dict['size']}",
        f"- survivors: {verdict_dict['survivors']}",
        f"- breaches: {verdict_dict['breaches']}",
        f"- note: {verdict_dict['note']}",
        "",
    ]
    return "\n".join(lines)


def print_matrix() -> None:
    print(f"METHOD: {METHOD}")
    for size in SIZES:
        for preset, seed, seconds in CELLS:
            print(f"size={size} preset={preset} seed={seed} seconds={seconds}")


def synth(size: int, seconds: int, wall_s: float, peak_megabytes: float) -> CellResult:
    """Synthetic cell for the pure-predicate selftest; no render is performed."""
    return CellResult(
        size=size,
        preset="ambient" if seconds == 900 else "motorik",
        seed=1042,
        seconds=seconds,
        wall_s=wall_s,
        peak_kib=int(peak_megabytes * 1024),
        plan_sha256="synthetic-plan",
        pcm_sha256="synthetic-pcm",
        render_seconds=wall_s,
        exit_code=0,
    )


def synth_matrix(
    base: tuple[float, float, float, float],
    small: tuple[float, float, float, float],
    smaller: tuple[float, float, float, float],
) -> list[CellResult]:
    """Each tuple is (ambient wall, ambient peak_mb, motorik wall, motorik peak_mb)."""
    result: list[CellResult] = []
    for size, values in ((SIZES[0], base), (SIZES[1], small), (SIZES[2], smaller)):
        amb_wall, amb_peak, mot_wall, mot_peak = values
        result.append(synth(size, 900, amb_wall, amb_peak))
        result.append(synth(size, 480, mot_wall, mot_peak))
    return result


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def selftest() -> int:
    """Five synthetic cases for the decision gate; no subprocess, no render."""
    check(peak_mb(1536) == 1.5, "peak_mb conversion is wrong")

    both = decide(synth_matrix((200, 1200, 160, 1100), (190, 1100, 150, 1050), (180, 1000, 140, 1000)))
    check(both.choice == "B" and both.size == 32768, f"both-survive case: {both}")

    only_small = decide(synth_matrix((200, 1200, 160, 1100), (198, 1190, 159, 1090), (190, 1100, 140, 1000)))
    check(only_small.choice == "B" and only_small.size == 16384, f"only-16384 case: {only_small}")

    neither = decide(synth_matrix((200, 1200, 160, 1100), (199, 1195, 159, 1095), (198, 1190, 158, 1090)))
    check(neither.choice == "A", f"neither case: {neither}")

    breached = decide(synth_matrix((200, 1200, 160, 1100), (199, 1195, 159, 1095), (181, 1501, 181, 1501)))
    check(breached.choice == "BISECT" and breached.midpoint == 24576, f"breach case: {breached}")

    base_breach = decide(synth_matrix((200, 1600, 160, 1100), (190, 1100, 150, 1050), (180, 1000, 140, 1000)))
    check(base_breach.choice == "A" and bool(base_breach.note), f"baseline-breach case: {base_breach}")

    print("selftest: 5/5 cases PASS")
    return 0


def run_matrix(base: Path, sizes: tuple[int, ...], label: str) -> list[CellResult] | None:
    """Run every cell of the given sizes, retrying invalid cells in fresh processes."""
    results: list[CellResult] = []
    for size in sizes:
        for preset, seed, seconds in CELLS:
            cell = run_cell(size, preset, seed, seconds, base, 1)
            for attempt in range(2, MAX_ATTEMPTS + 1):
                if cell.valid:
                    break
                print(f"discard {label} cell size={size} {preset}/{seconds}: {cell.reason}", file=sys.stderr)
                cell = run_cell(size, preset, seed, seconds, base, attempt)
            if not cell.valid:
                print(
                    f"FATAL: {label} cell size={size} {preset}/{seconds} invalid after "
                    f"{MAX_ATTEMPTS} attempts: {cell.reason} {cell.error}",
                    file=sys.stderr,
                )
                return None
            results.append(cell)
            print(
                f"{label} size={size} {preset}/{seconds} wall={cell.wall_s:.3f}s "
                f"peak={peak_mb(cell.peak_kib):.1f}MB attempt={cell.attempt}"
            )
    return results


def controller(out_json: Path | None, out_md: Path | None) -> int:
    base = Path(tempfile.mkdtemp(prefix="r31-", dir="/tmp/opencode"))
    try:
        cells = run_matrix(base, SIZES, "measured")
        if cells is None:
            return 2
        verdict = decide(cells)
        bisection: list[CellResult] = []
        if verdict.choice == "BISECT" and verdict.midpoint is not None:
            bisection = run_matrix(base, (verdict.midpoint,), "bisection") or []
            if not bisection:
                return 2
            verdict = finalize(cells, bisection)

        artifact = build_artifact(cells, bisection, verdict)
        if out_json is not None:
            out_json.parent.mkdir(parents=True, exist_ok=True)
            out_json.write_text(json.dumps(artifact, indent=2) + "\n")
        if out_md is not None:
            out_md.parent.mkdir(parents=True, exist_ok=True)
            out_md.write_text(render_markdown(artifact))
        print(f"decision: {verdict.choice} size={verdict.size} note={verdict.note}")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Cell matrix (baseline first): {[(s, p, sec) for s in SIZES for p, _, sec in CELLS]}",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--dry", action="store_true", help="print the cell matrix without rendering")
    mode.add_argument("--selftest", action="store_true", help="run the five synthetic decision cases")
    parser.add_argument("--size", type=int)
    parser.add_argument("--preset", choices=[cell[0] for cell in CELLS])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-json", type=Path, help="write the raw JSON artifact here")
    parser.add_argument("--out-md", type=Path, help="write the markdown table here")
    args = parser.parse_args()

    if args.dry:
        print_matrix()
        return 0
    if args.selftest:
        return selftest()
    if args.worker:
        if None in (args.size, args.preset, args.seed, args.seconds, args.out):
            parser.error("--worker needs --size --preset --seed --seconds --out")
        return worker(args.size, args.preset, args.seed, args.seconds, args.out)  # type: ignore[arg-type]
    return controller(args.out_json, args.out_md)


if __name__ == "__main__":
    raise SystemExit(main())
