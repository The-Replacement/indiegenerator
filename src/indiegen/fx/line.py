"""Recursive delay lines, processed a block at a time.

``scipy.signal.lfilter`` is O(samples x taps), which for a comb of fifteen
hundred taps over four million samples is sixty billion operations - the
reverb alone took three minutes. A feedback delay line has a block structure
instead: with a delay of N, the samples of a block depend only on the
corresponding samples of the previous block, so the recursion becomes one
vectorised update per block and the whole line costs O(samples).
"""

from __future__ import annotations

import numpy as np


def comb_line(
    signal: np.ndarray,
    delay: int,
    feedback: float,
    state: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """A feedback delay line: ``v[n] = x[n] + g * v[n-N]``.

    The padding at the end of the last block is discarded, and the state that
    is carried forward is taken from the end of the *real* signal, so a
    block-wise render is identical to a single-shot one.
    """
    count = signal.size
    padding = (-count) % delay
    padded = np.concatenate([signal, np.zeros(padding, dtype=np.float64)])
    blocks = padded.reshape(-1, delay)
    out = np.empty_like(blocks)
    carry = state
    for index in range(blocks.shape[0]):
        out[index] = blocks[index] + feedback * carry
        carry = out[index]
    flat = out.reshape(-1)
    if count >= delay:
        new_state = flat[count - delay : count]
    else:
        keep = delay - count
        new_state = np.concatenate([state[len(state) - keep :], flat[:count]])
    return flat[:count], new_state


def allpass_line(
    signal: np.ndarray,
    delay: int,
    feedback: float,
    state: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """A Schroeder allpass: ``v[n] = x[n] + g*v[n-N]``, ``y[n] = v[n-N] - x[n]``."""
    count = signal.size
    padding = (-count) % delay
    padded = np.concatenate([signal, np.zeros(padding, dtype=np.float64)])
    blocks = padded.reshape(-1, delay)
    buffer = np.empty_like(blocks)
    carry = state
    for index in range(blocks.shape[0]):
        buffer[index] = blocks[index] + feedback * carry
        carry = buffer[index]
    flat = buffer.reshape(-1)
    if count >= delay:
        previous = np.concatenate([state, flat[: len(padded) - delay]])
        new_state = flat[count - delay : count]
    else:
        previous = state[::-1][:count]
        keep = delay - count
        new_state = np.concatenate([state[len(state) - keep :], flat[:count]])
    return (previous - padded)[:count], new_state
