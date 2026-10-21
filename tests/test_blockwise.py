"""The block-wise render must be bit-identical to the single-shot one.

A voice, a bus, a master chain and a meter are all rendered a block at a
time so that a long track does not have to fit in memory. Rendering a block
is only safe if the block is exactly the same audio as the whole thing, so
every one of these tests renders the same material twice: once in one
block, once in blocks of an awkward size, and compares the samples.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import DroneEvent, PadEvent, PluckEvent, PolyPeriodEvent
from indiegen.synth import drone, ks, pad, poly_period

RATE: int = 44100
SEED: int = 1042


@pytest.fixture(scope="module")
def ambient_plan() -> object:
    """A short ambient plan: a poly-period loop, a drone and some plucks."""
    return director(compose(load_preset("ambient"), SEED, 20 * RATE))


@pytest.fixture(scope="module")
def station_plan() -> object:
    """A short station plan: the pad."""
    return director(compose(load_preset("station"), SEED, 20 * RATE))


def _blocks(count: int, size: int) -> list[tuple[int, int]]:
    """A list of blocks of ``size`` frames over ``count`` frames."""
    return [(start, min(count, start + size)) for start in range(0, count, size)]


def test_the_pad_is_the_same_in_blocks(station_plan: object) -> None:
    event = next(event for event in station_plan.events if isinstance(event, PadEvent))
    whole = pad.render_pad(event, RATE)
    pieces: list[np.ndarray] = []
    state = pad.pad_state(event)
    for start, stop in _blocks(event.duration_frames, 7919):
        block, state = pad.render_pad_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_poly_period_voice_is_the_same_in_blocks(ambient_plan: object) -> None:
    event = next(event for event in ambient_plan.events if isinstance(event, PolyPeriodEvent))
    whole = poly_period.render_poly_period(event, RATE)
    pieces: list[np.ndarray] = []
    state = poly_period.poly_period_state(event)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = poly_period.render_poly_period_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_drone_is_the_same_in_blocks(ambient_plan: object) -> None:
    event = next(event for event in ambient_plan.events if isinstance(event, DroneEvent))
    whole = drone.render_drone(event, RATE)
    pieces: list[np.ndarray] = []
    state = drone.drone_state(event)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = drone.render_drone_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_pluck_is_the_same_in_blocks(ambient_plan: object) -> None:
    event = next(event for event in ambient_plan.events if isinstance(event, PluckEvent))
    whole = ks.render_pluck(event, RATE)
    pieces: list[np.ndarray] = []
    state = ks.pluck_state(event, RATE)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = ks.render_pluck_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_voice_that_starts_inside_a_block_is_the_same(ambient_plan: object) -> None:
    """A block that starts in the middle of a voice is the same voice.

    The envelopes and the drift streams are cut at the block's own frames,
    so a block that starts in the middle of a note must still carry that
    note's history.
    """
    event = next(event for event in ambient_plan.events if isinstance(event, PolyPeriodEvent))
    whole = poly_period.render_poly_period(event, RATE)
    pieces: list[np.ndarray] = []
    state = poly_period.poly_period_state(event)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = poly_period.render_poly_period_block(event, RATE, start, stop, state)
        pieces.append(block)
    joined = np.concatenate(pieces)
    assert np.array_equal(joined, whole)
    # And the block that starts at zero alone is the head of the whole thing.
    head, _ = poly_period.render_poly_period_block(event, RATE, 0, 1234, poly_period.poly_period_state(event))
    assert np.array_equal(head, whole[:1234])
