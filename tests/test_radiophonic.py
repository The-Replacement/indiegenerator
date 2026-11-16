"""T8 radiophonic: the ring-mod stack must not put DC on the bus (gate 2).

The default carrier ratio is 2:1, so the carrier lands on partial 2 and the
product is sin(2wt) * sin(2wt) = 0.5 - 0.5cos(4wt): a DC term of 0.5 before
the level. Every other voice finishes on the shared DC blocker, but the
radiophonic stack shipped without one (PR #46), so every indie-noise track
measured ~0.05 against gate 2's 0.001 limit and was refused - the lane could
not air at all.

These tests pin the blocker at the unit level, across the blockwise render
the engine actually runs, and through the real gates on the real lane.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from indiegen.batch import render_track
from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import SAMPLE_RATE, RadiophonicEvent, Rational
from indiegen.synth.radiophonic import radiophonic_state, render_radiophonic, render_radiophonic_block

# The gate allows 0.001; the blocker leaves ~3e-5, so pin well under both.
DC_UNIT_LIMIT: float = 1e-4


def _event(carrier: tuple[int, int] = (2, 1)) -> RadiophonicEvent:
    """A 30 s A3 test-tone stack at -12 dB, attack and release included."""
    return RadiophonicEvent(
        instrument="radiophonic",
        kind="radiophonic",
        start_frame=0,
        duration_frames=30 * SAMPLE_RATE,
        midi=57,
        pan_permille=0,
        amplitude_millibels=-12000,
        attack_frames=int(0.1 * SAMPLE_RATE),
        release_frames=int(SAMPLE_RATE),
        carrier_ratio=Rational(numerator=carrier[0], denominator=carrier[1]),
    )


@pytest.mark.parametrize("carrier", [(2, 1), (3, 1), (3, 2)])
def test_the_carrier_stack_carries_no_dc(carrier: tuple[int, int]) -> None:
    """Any carrier that lands on a partial must still leave no DC behind.

    2:1 collides with partial 2 and 3:1 with partial 3 - both produced a
    mean of 0.5 * gain before the blocker; 3:2 never collided and needs the
    blocker to change nothing measurable.
    """
    signal = render_radiophonic(_event(carrier), SAMPLE_RATE)
    assert abs(float(signal.mean())) < DC_UNIT_LIMIT


def test_the_blockwise_render_is_the_single_shot() -> None:
    """The blocker's state must carry across blocks.

    A per-block filter that resets to zero leaves a residual on every block,
    and this render runs in blocks - the equality is the whole contract of
    the blockwise skeleton.
    """
    event = _event()
    whole = render_radiophonic(event, SAMPLE_RATE)
    state = radiophonic_state(event)
    parts: list[np.ndarray] = []
    block = 4410
    for start in range(0, event.duration_frames, block):
        stop = min(start + block, event.duration_frames)
        chunk, state = render_radiophonic_block(event, SAMPLE_RATE, start, stop, state)
        parts.append(chunk)
    assert np.array_equal(np.concatenate(parts), whole)


def test_an_indie_noise_track_passes_the_real_gates(tmp_path: Path) -> None:
    """The regression as the station sees it: seed 12 was refused at gate 2.

    This is the level the bug shipped at - a plan-level pin would not have
    caught it, because the plan was always right; the audio was not.
    """
    preset = load_preset("indie-noise")
    plan = director(compose(preset, 12, 60 * SAMPLE_RATE))
    assert "radiophonic" in plan.techniques

    result = render_track(plan, tmp_path)
    assert result.failure is None, result.failure.failures if result.failure else None
    assert result.outcome is not None
