"""The recursive delay lines, at every block size.

``render_plan`` happens to use one large block, but the primitives advertise
that a block-wise render is identical to a single-shot one, and that promise
has to hold for a block shorter than the delay too.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.fx.line import allpass_line, comb_line, delay_line


def _comb_reference(signal: np.ndarray, delay: int, feedback: float) -> np.ndarray:
    state = np.zeros(delay, dtype=np.float64)
    out = np.empty_like(signal)
    for index, value in enumerate(signal):
        slot = index % delay
        out[index] = value + feedback * state[slot]
        state[slot] = out[index]
    return out


def _delay_reference(signal: np.ndarray, delay: int, feedback: float) -> np.ndarray:
    out = np.zeros_like(signal)
    for index in range(delay, signal.size):
        out[index] = signal[index - delay] + feedback * out[index - delay]
    return out


def _allpass_reference(signal: np.ndarray, delay: int, feedback: float) -> np.ndarray:
    v = np.zeros(signal.size + delay, dtype=np.float64)
    out = np.empty_like(signal)
    for index, value in enumerate(signal):
        v[index + delay] = value + feedback * v[index]
        out[index] = v[index] - value
    return out


BLOCK_SIZES: tuple[int, ...] = (1, 3, 10, 64, 500, 4099)


@pytest.mark.parametrize("block_size", BLOCK_SIZES)
def test_the_comb_line_is_the_same_in_blocks(block_size: int) -> None:
    signal = np.random.default_rng(0).standard_normal(1200)
    expected = _comb_reference(signal, 50, 0.5)
    state = np.zeros(50, dtype=np.float64)
    pieces: list[np.ndarray] = []
    for start in range(0, signal.size, block_size):
        piece, state = comb_line(signal[start : start + block_size], 50, 0.5, state)
        pieces.append(piece)
    assert np.array_equal(np.concatenate(pieces), expected)


@pytest.mark.parametrize("block_size", BLOCK_SIZES)
def test_the_delay_line_is_the_same_in_blocks(block_size: int) -> None:
    signal = np.random.default_rng(1).standard_normal(1200)
    expected = _delay_reference(signal, 50, 0.5)
    state = (np.zeros(50, dtype=np.float64), np.zeros(50, dtype=np.float64))
    pieces: list[np.ndarray] = []
    for start in range(0, signal.size, block_size):
        piece, state = delay_line(signal[start : start + block_size], 50, 0.5, state)
        pieces.append(piece)
    assert np.array_equal(np.concatenate(pieces), expected)


@pytest.mark.parametrize("block_size", BLOCK_SIZES)
def test_the_allpass_line_is_the_same_in_blocks(block_size: int) -> None:
    signal = np.random.default_rng(2).standard_normal(1200)
    expected = _allpass_reference(signal, 50, 0.5)
    state = np.zeros(50, dtype=np.float64)
    pieces: list[np.ndarray] = []
    for start in range(0, signal.size, block_size):
        piece, state = allpass_line(signal[start : start + block_size], 50, 0.5, state)
        pieces.append(piece)
    assert np.array_equal(np.concatenate(pieces), expected)
