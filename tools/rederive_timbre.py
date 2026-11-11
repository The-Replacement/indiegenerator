"""Measurement harness for re-deriving per-function timbre targets (issue #39).

Renders a single lane/seed/duration under the CURRENT admission rule and
prints, per section, the function, the planned centroid (gate 6's target) and
the declared centroid, so a timbre re-derive can be evidenced before any
admission or layer-selection change.

Usage:
    python tools/rederive_timbre.py --lane motorik --seed 1042 --seconds 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from indiegen.compose import compose, director  # noqa: E402
from indiegen.config import load_preset  # noqa: E402
from indiegen.plan import SAMPLE_RATE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--seed", type=int, default=1042)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--rule", choices=("current", "highlow"), default="current")
    args = parser.parse_args()

    from indiegen.compose import planner as _planner  # noqa: E402

    _planner.ADMISSION_RULE = args.rule

    preset = load_preset(args.lane)
    plan = director(compose(preset, args.seed, args.seconds * SAMPLE_RATE))

    print(f"lane={args.lane} seed={args.seed} seconds={args.seconds} sections={len(plan.sections)}")
    print(f"{'idx':>3} {'function':<10} {'centroid_hz':>11} {'declared_millihz':>18} {'tension':>7} {'level_mb':>9}")
    for section in plan.sections:
        print(
            f"{section.index:>3} {section.function:<10} {section.centroid_hz:>11} "
            f"{section.declared_centroid_millihz:>18} {section.tension_permille:>7} {section.level_millibels:>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
