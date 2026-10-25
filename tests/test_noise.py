"""AC-25 to AC-28: the 1/f primitive.

A deterministic, counter-based signal: no RNG object, no random import, and
a slope that is neither white nor steeper than brown.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from indiegen.control import (
    CONTROL_RATE,
    pink_stream,
    stream_key,
    uniform_stream,
)
from indiegen.synth.noise import interpolate_to

RATE: int = 44100


def test_the_module_constructs_no_rng() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "indiegen" / "synth" / "noise.py"
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


def test_the_same_seed_reproduces_the_signal_bit_for_bit() -> None:
    assert np.array_equal(pink_stream(1234, 4096, RATE), pink_stream(1234, 4096, RATE))
    assert not np.array_equal(pink_stream(1234, 4096, RATE), pink_stream(1235, 4096, RATE))


def test_the_spectral_slope_is_between_ten_and_twenty_db_per_decade() -> None:
    signal = pink_stream(99, RATE * 8, RATE)
    windowed = signal * np.hanning(signal.size)
    spectrum = np.abs(np.fft.rfft(windowed)) ** 2
    frequencies = np.fft.rfftfreq(signal.size, 1.0 / RATE)
    band = (frequencies >= 10.0) & (frequencies <= 10000.0)
    slope = np.polyfit(np.log10(frequencies[band]), 10.0 * np.log10(spectrum[band]), 1)[0]
    assert -20.0 <= slope <= -10.0, f"slope {slope:.2f} dB/decade"


def test_the_stream_key_separates_the_partials_and_the_purposes() -> None:
    assert stream_key(7, 0, 0) == stream_key(7, 0, 0)
    assert stream_key(7, 0, 0) != stream_key(7, 1, 0)
    assert stream_key(7, 0, 0) != stream_key(7, 0, 1)
    assert stream_key(7, 0, 0) != stream_key(8, 0, 0)


def test_two_partials_streams_are_uncorrelated() -> None:
    first = uniform_stream(11, 0, 0, 20000)
    second = uniform_stream(11, 1, 0, 20000)
    correlation = float(np.corrcoef(first, second)[0, 1])
    assert abs(correlation) < 0.1


def test_the_interpolation_passes_through_the_control_points() -> None:
    count = 1000
    size = count * CONTROL_RATE // 44100 + 2
    control = np.linspace(-1.0, 1.0, size)
    audio = interpolate_to(control, count, 44100)
    for index, value in enumerate(control):
        position = index * 44100 // CONTROL_RATE
        if position >= count:
            break
        assert audio[position] == pytest.approx(value, abs=1e-9)
