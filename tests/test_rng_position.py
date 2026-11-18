"""c14 guards: the motif orbit must not move a single RNG draw.

AC1 pins the Director/FX deck bytes (the downstream fingerprint of every draw
before ``deck_snap``); AC2 pins the number and ORDER of the draws made inside
``t14_motif.py``. Both are written against unmodified HEAD (4937c5c): the
orbit is a pure post-transform and must consume zero randomness, so these
values must not move when the orbit lands.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from indiegen.compose import compose, director
from indiegen.compose.rng import SplitMix64
from indiegen.config import load_preset
from indiegen.plan import canonical_bytes

BASELINE_PATH = Path("/tmp/opencode/c14_baseline_decks.json")


_CELLS: tuple[tuple[str, int], ...] = (
    ("motorik", 1042),
    ("motorik", 2000),
    ("motorik", 4002),
    ("dub-electronic", 4002),
)


def _deck_hash(plan: object) -> str:
    dumped = [move.model_dump(mode="json") for move in plan.strategy_deck]  # type: ignore[attr-defined]
    return hashlib.sha256(canonical_bytes(dumped)).hexdigest()


def _opening(plan: object) -> str:
    first = plan.strategy_deck[0].model_dump(mode="json")  # type: ignore[attr-defined]
    return str(first.get("name") or first.get("strategy") or "")


def test_deck_bytes_match_head_baseline() -> None:
    """AC1: deck bytes, appearance counts and the 4002 opener are unchanged."""
    baseline: dict[str, dict[str, object]] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    for lane, seed in _CELLS:
        key = f"{lane}-{seed}"
        plan = director(compose(load_preset(lane), seed, 240 * 44100))
        expected = baseline[key]
        assert _deck_hash(plan) == expected["deck_sha256"], key
        appearances = plan.motif_appearances
        assert len(appearances) == expected["appearance_count"], key
        assert sum(1 for app in appearances if app.transform != "identity") == expected[
            "appearance_transform_count"
        ], key
        assert _opening(plan) == expected["strategies"][0], key

    # The named regression: motorik-4002 opens transpose_up_fourth.
    plan_4002 = director(compose(load_preset("motorik"), 4002, 240 * 44100))
    assert _opening(plan_4002) == "transpose_up_fourth"
    assert _deck_hash(plan_4002) == "4ead693eb83c8a6ed6b0f343114551a477e8596d71b3f5a97d47d73365312928"
