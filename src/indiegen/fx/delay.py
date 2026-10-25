"""The dotted-eighth delay.

The station's signature: the KS guitar is always heard through it. The
length is resolved to an integer frame count at compose time, so the renderer
never sees the tempo.

It is a true delay, not a comb: the wet starts at frame D, and the guitar's
dry is never summed separately. The damping one-pole carries its state, so a
block-wise render is identical to a single-shot one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from indiegen.fx.line import delay_line, zero_wet
from indiegen.plan import DelaySend


@dataclass(frozen=True)
class DelayState:
    """The delay lines, as a value. One per channel."""

    states: tuple[tuple[np.ndarray, np.ndarray], ...]
    damping: tuple[np.ndarray, ...]


def delay_state(send: DelaySend) -> DelayState:
    """The zero state of the delay."""
    block = np.zeros(send.delay_frames, dtype=np.float64)
    return DelayState(
        states=tuple((block.copy(), block.copy()) for _ in range(2)),
        damping=tuple(np.zeros(1, dtype=np.float64) for _ in range(2)),
    )


def render_delay(block: np.ndarray, state: DelayState, send: DelaySend) -> tuple[np.ndarray, DelayState]:
    """Delay one block of the KS bus."""
    feedback = send.feedback.numerator / send.feedback.denominator
    damping = send.damping.numerator / send.damping.denominator
    wet = zero_wet(block)
    new_states: list[tuple[np.ndarray, np.ndarray]] = []
    new_damping: list[np.ndarray] = []
    for channel in range(block.shape[1]):
        signal = np.ascontiguousarray(block[:, channel], dtype=np.float64)
        filtered, carry = delay_line(signal, send.delay_frames, feedback, state.states[channel])
        if damping < 1.0:
            filtered, damp_carry = lfilter([1.0 - damping], [1.0, -damping], filtered, zi=state.damping[channel])
        else:
            damp_carry = state.damping[channel]
        wet[:, channel] = filtered
        new_states.append(carry)
        new_damping.append(damp_carry)
    return wet, DelayState(states=tuple(new_states), damping=tuple(new_damping))
