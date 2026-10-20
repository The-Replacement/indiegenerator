"""AC-38: the compose PRNG is project-local, integer only and reproducible."""

from __future__ import annotations

import ast
from pathlib import Path

from indiegen.compose.rng import SplitMix64, seed_from_bytes
from tests.conftest import GOLDEN_DIR


def test_golden_draw_sequence() -> None:
    rng = SplitMix64(1234567)
    draws = [rng.next_u64() for _ in range(32)]
    golden = (GOLDEN_DIR / "prng_draws.txt").read_text(encoding="utf-8").strip().splitlines()
    assert [str(draw) for draw in draws] == golden


def test_every_draw_is_an_int() -> None:
    rng = SplitMix64(99)
    assert isinstance(rng.next_u64(), int)
    assert isinstance(rng.next_int(), int)
    assert isinstance(rng.below(10), int)
    assert isinstance(rng.between(1, 5), int)
    assert isinstance(rng.choice([1, 2, 3]), int)


def test_below_stays_in_range() -> None:
    rng = SplitMix64(7)
    assert all(0 <= rng.below(5) < 5 for _ in range(500))


def test_between_is_inclusive() -> None:
    rng = SplitMix64(11)
    assert all(3 <= rng.between(3, 5) <= 5 for _ in range(500))


def test_seed_derivation_is_deterministic() -> None:
    assert seed_from_bytes(b"abc") == seed_from_bytes(b"abc")
    assert seed_from_bytes(b"abc") != seed_from_bytes(b"abd")


def test_module_has_no_random_source() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "indiegen" / "compose" / "rng.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "random"
                assert not alias.name.startswith("numpy.random")
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") != "random"
            assert not (node.module or "").startswith("numpy.random")
        if isinstance(node, ast.Attribute):
            assert not (isinstance(node.value, ast.Name) and node.value.id == "random")
