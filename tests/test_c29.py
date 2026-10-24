"""c29: the streamed master and the stem are bit-identical to the array path.

The master reads the mix twice through a memmap and never holds the
whole-track peak envelope or the whole limited signal. The claim is that
the numbers do not move: the same plan mastered from a memmap and from an
in-memory array is the same int16 buffer, and the stem the batch leaves
behind is gone.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from indiegen.cli import app
from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.master.chain import master
from indiegen.render import BLOCK_SIZE, render_plan, write_mix_stem

RATE = 44100


def _plan():
    return director(compose(load_preset("motorik"), 1042, 8 * RATE))


def test_master_over_a_memmap_equals_master_over_an_array(tmp_path: Path) -> None:
    plan = _plan()
    array = render_plan(plan)
    stem = tmp_path / "mix.mix"
    shape = write_mix_stem(plan, stem)
    mapping = np.memmap(stem, dtype=np.float64, mode="r", shape=shape)

    from_array = master(plan, array, BLOCK_SIZE)
    from_memmap = master(plan, mapping, BLOCK_SIZE)

    assert from_array.shape == from_memmap.shape
    assert np.array_equal(from_array, from_memmap)
    del mapping
    stem.unlink()


def test_the_stem_is_bit_equal_to_the_rendered_array(tmp_path: Path) -> None:
    plan = _plan()
    array = render_plan(plan)
    stem = tmp_path / "mix.mix"
    shape = write_mix_stem(plan, stem)
    mapping = np.memmap(stem, dtype=np.float64, mode="r", shape=shape)
    assert np.array_equal(np.asarray(mapping), array)
    del mapping
    stem.unlink()


@pytest.mark.slow
def test_a_render_leaves_no_stem_behind(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "render",
            "--preset",
            "motorik",
            "--seed",
            "1042",
            "--seconds",
            "60",
            "--out",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    leftovers = list((tmp_path / ".tmp").glob("*.mix"))
    assert leftovers == []
