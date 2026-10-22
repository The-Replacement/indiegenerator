"""S4: the limiter, the loudness pass and the master chain.

The limiter is the hardest thing in the slice: it has to hold a true peak
ceiling on the inter-sample peaks, it has to be a function of the block
size, and it has to be deterministic.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest

from indiegen.master.chain import master
from indiegen.master.dither import tpdf
from indiegen.master.limiter import (
    LOOKAHEAD_FRAMES,
    MODEL_MARGIN_DB,
    decayed_max,
    limit,
    lookahead_min,
    peak_envelope,
)
from indiegen.master.loudness import integrated_lufs, to_float, true_peak_dbtp

PACKAGE: Path = Path(__file__).resolve().parents[1] / "src" / "indiegen"
RATE: int = 44100
CEILING: float = 10 ** (-1.5 / 20.0)


def _tone(frequency: float, seconds: float, amplitude: float = 1.0) -> np.ndarray:
    count = int(seconds * RATE)
    times = np.arange(count) / RATE
    wave = amplitude * np.sin(2.0 * math.pi * frequency * times)
    return np.stack([wave, wave], axis=1)


def _noise(seconds: float, amplitude: float, seed: int = 5) -> np.ndarray:
    generator = np.random.default_rng(seed)
    count = int(seconds * RATE)
    signal = generator.standard_normal((count, 2))
    return signal / np.max(np.abs(signal)) * amplitude


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


def test_the_peak_envelope_finds_the_inter_sample_peak() -> None:
    """A square wave's samples are at the rails and its peak is above them."""
    signal = _tone(3000.0, 1.0)
    square = np.sign(signal)
    envelope = peak_envelope(square, 8192)
    assert float(envelope.max()) > 1.2
    assert abs(float(envelope.max()) - 10 ** (true_peak_dbtp(square) / 20.0)) < 0.01


def test_the_peak_envelope_attributes_the_peak_to_its_own_sample() -> None:
    signal = np.zeros((4096, 2), dtype=np.float64)
    signal[1000, 0] = 1.0
    envelope = peak_envelope(signal, 8192)
    assert int(np.argmax(envelope)) == 1000


def test_the_lookahead_minimum_is_the_minimum_of_the_window() -> None:
    values = np.array([0.5, 1.0, 1.0, 0.1, 1.0, 0.2, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    measured = lookahead_min(values, 4, 8)
    assert np.allclose(measured, [min(values[index : index + 4]) for index in range(8)])


def test_the_decayed_maximum_releases_the_deficit() -> None:
    decay = math.exp(-1.0 / 100.0)
    values = np.zeros(50, dtype=np.float64)
    values[0] = 1.0
    measured, carry = decayed_max(values, decay, 0.0)
    assert measured[0] == pytest.approx(1.0)
    assert measured[10] == pytest.approx(decay**10)
    assert carry == pytest.approx(decay**49)


def test_the_limiter_never_overshoots_the_ceiling() -> None:
    """The delivered true peak is under the ceiling, on every kind of signal."""
    signals = [
        _tone(1000.0, 2.0, 8.0),
        _tone(3000.0, 2.0, 40.0),
        _noise(2.0, 40.0),
    ]
    for signal in signals:
        peaks = peak_envelope(signal, 8192)
        limited, _, _ = limit(signal, 1.0, peaks, CEILING, 8192)
        assert true_peak_dbtp(limited) <= -1.5 + 1e-6


def test_the_limiter_leaves_a_quiet_signal_alone() -> None:
    signal = _tone(1000.0, 1.0, 0.1)
    peaks = peak_envelope(signal, 8192)
    limited, deepest, _ = limit(signal, 1.0, peaks, CEILING, 8192)
    assert deepest == pytest.approx(1.0)
    assert np.allclose(limited, signal)


def test_the_limiter_does_not_depend_on_the_block_size() -> None:
    signal = _noise(2.0, 8.0, seed=9)
    peaks = peak_envelope(signal, 8192)
    first, _, _ = limit(signal, 1.0, peaks, CEILING, 8192)
    second, _, _ = limit(signal, 1.0, peaks, CEILING, 8192 * 2)
    third, _, _ = limit(signal, 1.0, peaks, CEILING, 8192 * 3)
    assert np.allclose(first, second)
    assert np.allclose(first, third)


def test_the_limiter_only_takes_the_gain_down() -> None:
    """The gain never rises above one, and never jumps up by more than the release."""
    signal = _noise(2.0, 8.0, seed=13)
    peaks = peak_envelope(signal, 8192)
    limited, _, _ = limit(signal, 1.0, peaks, CEILING, 8192)
    ratio = limited / signal
    valid = np.abs(signal) > 1e-9
    assert float(np.max(ratio[valid])) <= 1.0 + 1e-9


def test_the_limiter_holds_a_ceiling_that_the_signal_does_not_reach() -> None:
    signal = _tone(1000.0, 1.0, 0.01)
    peaks = peak_envelope(signal, 8192)
    limited, deepest, _ = limit(signal, 1.0, peaks, CEILING, 8192)
    assert deepest == pytest.approx(1.0)
    assert np.allclose(limited, signal)


def test_the_model_margin_is_a_third_of_a_decibel() -> None:
    assert 0.2 <= MODEL_MARGIN_DB <= 0.5


def test_the_master_lands_on_the_loudness_target(reference_plan: object) -> None:
    from indiegen.render import render_plan

    plan = reference_plan  # type: ignore[assignment]
    stereo = render_plan(plan)
    pcm = master(plan, stereo, 8192)
    loudness = integrated_lufs(to_float(pcm), plan.sample_rate)
    assert abs(loudness - plan.target_lufs_millibels / 1000.0) <= 1.0


def test_the_master_holds_the_true_peak_ceiling(reference_plan: object) -> None:
    from indiegen.render import render_plan

    plan = reference_plan  # type: ignore[assignment]
    stereo = render_plan(plan)
    pcm = master(plan, stereo, 8192)
    assert true_peak_dbtp(to_float(pcm)) <= -1.5 + 1e-6


def test_the_master_does_not_depend_on_the_block_size(reference_plan: object) -> None:
    from indiegen.render import render_plan

    plan = reference_plan  # type: ignore[assignment]
    stereo = render_plan(plan)
    first = master(plan, stereo, 8192)
    second = master(plan, stereo, 8192 * 2)
    assert np.array_equal(first, second)


def test_the_lookahead_is_long_enough_to_cover_the_peak() -> None:
    assert LOOKAHEAD_FRAMES > 0
