"""The sidechain: everything but the kick is ducked by the kick.

BRIEF T10: "sidechain everything ambient to kick". It is a dub instrument,
not a compressor: the gain drops at every kick hit and comes back over the
card's release frames.

The envelope is computed on the hit frames, not on the audio, so it is the
same in a block-wise render and in a whole-track one, and it costs one
exponential per second of audio rather than one per sample.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain


@dataclass(frozen=True)
class SidechainState:
    """Which hit is the next one to come."""

    next_hit: int


def sidechain_state() -> SidechainState:
    """The zero state of the envelope."""
    return SidechainState(next_hit=0)


def duck_level(depth_millibels: int) -> float:
    """The gain the envelope falls to at a hit."""
    return millibels_to_gain(depth_millibels)


def render_sidechain(
    block_start: int,
    count: int,
    hits: list[int],
    state: SidechainState,
    release_frames: int,
    depth_millibels: int,
) -> tuple[np.ndarray, SidechainState]:
    """The ducking gain over a block, and the state that follows it.

    The gain is the lowest of the envelopes of the hits that have already
    happened, and the most recent hit is always the lowest one, so the
    envelope is restarted at every hit and recovered exponentially.
    """
    gain = np.ones(count, dtype=np.float64)
    if not hits or release_frames <= 0:
        return gain, state
    index = state.next_hit
    while index < len(hits) and hits[index] < block_start:
        index += 1
    level = duck_level(depth_millibels)
    samples = np.arange(block_start, block_start + count, dtype=np.int64)
    if index > 0:
        age = np.maximum(samples - hits[index - 1], 0).astype(np.float64)
        gain = 1.0 - (1.0 - level) * np.exp(-age / release_frames)
    inside = 0
    for hit in hits[index:]:
        if hit >= block_start + count:
            break
        local = hit - block_start
        age = np.arange(count - local, dtype=np.float64)
        envelope = 1.0 - (1.0 - level) * np.exp(-age / release_frames)
        gain[local:] = np.minimum(gain[local:], envelope)
        inside += 1
    return gain, SidechainState(next_hit=index + inside)
