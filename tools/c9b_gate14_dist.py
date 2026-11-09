"""c9b gate-14 distribution over sweep15 (issue #9b, Commit2 T10).

Reports the gate-14 tension correlation (min/p25/median/max) across the
15 sweep cells (5 lanes x seeds 1042/2000/4002 at 240 s) WITHOUT asserting
anything: T10 records the distribution, it does not gate it (AC2.8).
The production check_gate_14 still enforces TENSION_CORRELATION_LIMIT.

Run:

    python tools/c9b_gate14_dist.py

Outputs the table to stdout. No file is written.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from indiegen.compose import compose, director  # noqa: E402
from indiegen.config import load_preset  # noqa: E402
from indiegen.master.chain import master  # noqa: E402
from indiegen.render import BLOCK_SIZE, render_plan  # noqa: E402
from indiegen.validate import TENSION_CORRELATION_LIMIT, tension_correlation  # noqa: E402

LANES: tuple[str, ...] = ("motorik", "kosmische", "dub-electronic", "indie-noise", "ambient")
SEEDS: tuple[int, ...] = (1042, 2000, 4002)
SWEEP_SECONDS: int = 240
RATE: int = 44100


def main() -> int:
    values: list[float] = []
    rows: list[tuple[str, int, float]] = []
    started = time.monotonic()
    for lane in LANES:
        for seed in SEEDS:
            plan = director(compose(load_preset(lane), seed, SWEEP_SECONDS * RATE))
            mix = render_plan(plan)
            pcm = master(plan, mix, BLOCK_SIZE)
            corr = tension_correlation(plan, pcm)
            values.append(corr)
            rows.append((lane, seed, corr))
            print(f"{lane:14s} {seed:5d}  gate14 {corr:+.6f}", flush=True)

    arr = np.array(values, dtype=np.float64)
    print()
    print(f"cells        : {len(arr)}")
    print(f"min          : {float(arr.min()):+.6f}")
    print(f"p25          : {float(np.percentile(arr, 25)):+.6f}")
    print(f"median       : {float(np.percentile(arr, 50)):+.6f}")
    print(f"max          : {float(arr.max()):+.6f}")
    print(f"limit (T)    : {TENSION_CORRELATION_LIMIT:+.6f}  (NOT asserted here)")
    below = [r for r in rows if not np.isfinite(r[2]) or r[2] < TENSION_CORRELATION_LIMIT]
    print(f"below limit  : {len(below)}")
    for lane, seed, corr in below:
        print(f"  {lane} {seed} {corr:+.6f}")
    print(f"wall         : {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
