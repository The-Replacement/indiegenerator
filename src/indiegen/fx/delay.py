"""The dotted-eighth delay.

The station's signature: the KS guitar is always heard through it. The
length is resolved to an integer frame count at compose time, so the renderer
never sees the tempo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from indiegen.fx.line import comb_line
from indiegen.plan import DelaySend


@dataclass(frozen=True)
class DelayState:
    """The delay lines, as a value. One per channel."""

    states: tuple[np.ndarray, ...]


def delay_state(send: DelaySend) -> DelayState:
    """The zero state of the delay."""
    return DelayState(states=tuple(np.zeros(send.delay_frames, dtype=np.float64) for _ in range(2)))


def render_delay(block: np.ndarray, state: DelayState, send: DelaySend) -> tuple[np.ndarray, DelayState]:
    """Delay one block of the KS bus."""
    feedback = send.feedback.numerator / send.feedback.denominator
    damping = send.damping.numerator / send.damping.denominator
    wet = np.zeros(block.shape, dtype=np.float64)
    new_states: list[np.ndarray] = []
    for channel in range(block.shape[1]):
        signal = np.ascontiguousarray(block[:, channel], dtype=np.float64)
        filtered, carry = comb_line(signal, send.delay_frames, feedback, state.states[channel])
        if damping < 1.0:
            filtered = lfilter([1.0 - damping], [1.0, -damping], filtered)
        wet[:, channel] = filtered
        new_states.append(carry)
    return wet, DelayState(states=tuple(new_states))
