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
from indiegen.master.chain import master
from indiegen.plan import DroneEvent, PadEvent, Plan, PluckEvent, PolyPeriodEvent
from indiegen.render import render_plan
from indiegen.synth import drone, ks, pad, poly_period

RATE: int = 44100
SEED: int = 1042


@pytest.fixture(scope="module")
def ambient_plan() -> Plan:
    """A short ambient plan: a poly-period loop, a drone and some plucks."""
    return director(compose(load_preset("ambient"), SEED, 20 * RATE))


@pytest.fixture(scope="module")
def station_plan() -> Plan:
    """A short station plan: the pad."""
    return director(compose(load_preset("motorik"), SEED, 20 * RATE))


@pytest.fixture(scope="module")
def motorik_plan() -> Plan:
    """A short motorik plan: the drums, the pad and the deja-vu."""
    return director(compose(load_preset("motorik"), SEED, 20 * RATE))


@pytest.fixture(scope="module")
def mix(ambient_plan: Plan) -> np.ndarray:
    """The ambient plan, rendered once."""
    return render_plan(ambient_plan)


@pytest.fixture(scope="module")
def pcm(ambient_plan: Plan, mix: np.ndarray) -> np.ndarray:
    """The ambient plan, mastered once."""
    return master(ambient_plan, mix, 8192)


def _blocks(count: int, size: int) -> list[tuple[int, int]]:
    """A list of blocks of ``size`` frames over ``count`` frames."""
    return [(start, min(count, start + size)) for start in range(0, count, size)]


def test_the_pad_is_the_same_in_blocks(station_plan: Plan) -> None:
    event = next(event for event in station_plan.events if isinstance(event, PadEvent))
    whole = pad.render_pad(event, RATE)
    pieces: list[np.ndarray] = []
    state = pad.pad_state(event)
    for start, stop in _blocks(event.duration_frames, 7919):
        block, state = pad.render_pad_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_poly_period_voice_is_the_same_in_blocks(ambient_plan: Plan) -> None:
    event = next(event for event in ambient_plan.events if isinstance(event, PolyPeriodEvent))
    whole = poly_period.render_poly_period(event, RATE)
    pieces: list[np.ndarray] = []
    state = poly_period.poly_period_state(event)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = poly_period.render_poly_period_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_drone_is_the_same_in_blocks(ambient_plan: Plan) -> None:
    event = next(event for event in ambient_plan.events if isinstance(event, DroneEvent))
    whole = drone.render_drone(event, RATE)
    pieces: list[np.ndarray] = []
    state = drone.drone_state(event)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = drone.render_drone_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_pluck_is_the_same_in_blocks(ambient_plan: Plan) -> None:
    event = next(event for event in ambient_plan.events if isinstance(event, PluckEvent))
    whole = ks.render_pluck(event, RATE)
    pieces: list[np.ndarray] = []
    state = ks.pluck_state(event, RATE)
    for start, stop in _blocks(event.duration_frames, 7001):
        block, state = ks.render_pluck_block(event, RATE, start, stop, state)
        pieces.append(block)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_render_is_the_same_in_blocks(ambient_plan: Plan, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bus graph does not care how the track is cut up.

    The voices, the delay, the filter, the reverb and the gains all carry
    their state, so a block of the bus graph is the same audio whatever the
    block size is.
    """
    from indiegen import render as render_module

    whole = render_module.render_plan(ambient_plan)
    monkeypatch.setattr(render_module, "RENDER_BLOCK", 4099)
    pieces = render_module.render_plan(ambient_plan)
    assert np.array_equal(pieces, whole)


def test_a_drum_hit_that_crosses_a_block_boundary_keeps_its_tail(
    motorik_plan: Plan, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hit whose voice runs past the end of a block is not cut.

    A kick lasts a third of a second and a block is three seconds, so a
    hit near the end of a block has its tail in the next one. The tails are
    carried in the state, and the render is the same whatever the block
    size is - which is what the carried tails are for.
    """
    from indiegen import render as render_module

    whole = render_module.render_plan(motorik_plan)
    monkeypatch.setattr(render_module, "RENDER_BLOCK", 65536)
    pieces = render_module.render_plan(motorik_plan)
    assert np.array_equal(pieces, whole)


def test_the_master_is_the_same_in_blocks(ambient_plan: Plan, mix: np.ndarray) -> None:
    """The master chain does not care how the mix is cut up.

    The limiter's gain is the smallest over the blocks, so it is the block
    size that decides it - and that is the committed behaviour. As long as
    the limiter does not engage, which is the normal case, the output is the
    same.
    """
    from indiegen.master.chain import master

    reference = master(ambient_plan, mix, 8192)
    for size in (1024, 4096, 65536):
        assert np.array_equal(master(ambient_plan, mix, size), reference)


def test_the_meter_is_the_same_in_blocks(ambient_plan: Plan, pcm: np.ndarray) -> None:
    """The loudness meter does not care how the track is cut up."""
    from indiegen.master.loudness import LoudnessMeter, measure, to_float

    reference = measure(pcm, 44100)
    for size in (1024, 40960, 65536):
        meter = LoudnessMeter(44100)
        for start in range(0, pcm.shape[0], size):
            stop = min(pcm.shape[0], start + size)
            meter.feed(to_float(pcm[start:stop]))
        assert meter.integrated_lufs() == reference["integrated_lufs"]
        assert meter.sample_peak_dbfs() == reference["sample_peak_dbfs"]
        assert meter.true_peak_dbtp() == reference["true_peak_dbtp"]


def test_the_voice_that_starts_inside_a_block_is_the_same(ambient_plan: Plan) -> None:
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
