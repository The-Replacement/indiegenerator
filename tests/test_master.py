"""AC-37: the master chain consumes the Plan's dither seed and rolls nothing."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from indiegen.master.chain import master
from indiegen.master.dither import tpdf

PACKAGE: Path = Path(__file__).resolve().parents[1] / "src" / "indiegen"


def test_the_dither_is_deterministic_for_a_seed() -> None:
    assert np.array_equal(tpdf(1234, 64), tpdf(1234, 64))


def test_the_dither_differs_for_another_seed() -> None:
    assert not np.array_equal(tpdf(1234, 64), tpdf(1235, 64))


def test_the_dither_is_triangular_and_centred() -> None:
    values = tpdf(99, 200000)
    assert abs(float(np.mean(values))) < 0.01
    assert abs(float(np.max(np.abs(values)))) <= 1.0


def test_the_plan_carries_an_integer_dither_seed(reference_plan: object) -> None:
    seed = reference_plan.dither_seed
    assert isinstance(seed, int)
    assert seed >= 0


def test_the_master_module_constructs_no_rng() -> None:
    path = PACKAGE / "master" / "chain.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "random"
                assert not alias.name.startswith("numpy.random")
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") != "random"
        if isinstance(node, ast.Name):
            assert node.id not in {"default_rng", "RandomState", "Generator"}


def test_the_master_output_is_int16_and_finite(reference_plan: object) -> None:
    from indiegen.render import render_plan

    plan = reference_plan  # type: ignore[assignment]
    stereo = render_plan(plan)
    pcm = master(plan, stereo, 8192)
    assert pcm.dtype == np.int16
    assert bool(np.all(np.isfinite(pcm.astype(np.float64))))
    assert int(np.max(np.abs(pcm.astype(np.int32)))) <= 32768
