"""c33: a drum hit's played frame is data in the Plan.

The drift used to be applied at render time, and an offset applied while the
track is cut into blocks is not block-invariant: a hit that drifts out of its
block was refused by both the block that had gone by and the block that held
it, so it was lost. It now moves into the plan, where the renderer cannot be
wrong about it.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.compose.microtiming import apply_micro_timing
from indiegen.config import PinkCard, Preset, load_preset
from indiegen.plan import DrumHit, HatEvent, Plan, RhythmEvent
from indiegen.synth.drums import render_hat

RATE: int = 44100
SEED: int = 1042
SECONDS: int = 20
DRUMS: frozenset[str] = frozenset({"kick", "snare", "hat", "bass"})


def _drum_events(plan: Plan) -> list[RhythmEvent]:
    return [event for event in plan.events if isinstance(event, RhythmEvent) and event.kind in DRUMS]


def _with_depth(preset: Preset, depth: int) -> Preset:
    """The preset, with the pink card's micro-timing depth replaced in every lane."""
    lanes = []
    for entry in preset.lanes:
        cards = [
            card.model_copy(update={"micro_timing_frames": depth}) if isinstance(card, PinkCard) else card
            for card in entry.parameters.techniques
        ]
        lanes.append(entry.model_copy(update={"parameters": entry.parameters.model_copy(update={"techniques": cards})}))
    return preset.model_copy(update={"lanes": lanes})


@pytest.fixture(scope="module")
def motorik_plan() -> Plan:
    return director(compose(load_preset("motorik"), SEED, SECONDS * RATE))


@pytest.fixture(scope="module")
def flat_plan() -> Plan:
    """The same lane and seed, with the drift switched off."""
    return director(compose(_with_depth(load_preset("motorik"), 0), SEED, SECONDS * RATE))


def test_the_drift_is_frozen_in_the_plan(motorik_plan: Plan) -> None:
    """Every hit carries its own offset, bounded by the lane's declared depth."""
    hits = [hit for event in _drum_events(motorik_plan) for hit in event.hits]
    assert hits, "the motorik fixture must have drum hits"
    drifted = [hit for hit in hits if hit.drift_frames]
    assert drifted, "the motorik lane declares a micro-timing depth of 12 frames"
    for hit in hits:
        assert abs(hit.drift_frames) <= 12
        assert hit.grid_frame() == hit.frame - hit.drift_frames
        assert hit.frame >= 0


def test_the_hits_stay_in_the_order_the_renderer_walks(motorik_plan: Plan) -> None:
    """``render_drum_block`` stops at the first hit past the block."""
    for event in _drum_events(motorik_plan):
        frames = [hit.frame for hit in event.hits]
        assert frames == sorted(frames)
        assert len(frames) == len(set(frames))


def test_the_drift_does_not_move_the_grid(motorik_plan: Plan, flat_plan: Plan) -> None:
    """The offset is additive: the frames the arrangement wrote are untouched."""
    drifted = [hit.grid_frame() for event in _drum_events(motorik_plan) for hit in event.hits]
    flat = [hit.frame for event in _drum_events(flat_plan) for hit in event.hits]
    assert drifted == flat
    for event in _drum_events(flat_plan):
        assert all(hit.drift_frames == 0 for hit in event.hits)


def test_the_drift_is_reproducible_and_seeded(motorik_plan: Plan) -> None:
    """Same seed, same frames; a new seed moves at least one of them."""
    again = director(compose(load_preset("motorik"), SEED, SECONDS * RATE))
    assert [hit.frame for event in _drum_events(again) for hit in event.hits] == [
        hit.frame for event in _drum_events(motorik_plan) for hit in event.hits
    ]
    other = director(compose(load_preset("motorik"), SEED + 1, SECONDS * RATE))
    assert [hit.frame for event in _drum_events(other) for hit in event.hits] != [
        hit.frame for event in _drum_events(motorik_plan) for hit in event.hits
    ]


def test_zero_depth_is_a_strict_no_op() -> None:
    """``micro_timing_frames = 0`` leaves the hit where the grid put it."""
    event = HatEvent(
        kind="hat",
        instrument="hat",
        start_frame=0,
        duration_frames=8000,
        midi=57,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        hits=[DrumHit(frame=100, velocity_millibels=0)],
        noise_seed=7,
        velocity_depth_millibels=0,
        micro_timing_frames=0,
        pan_drift_permille=0,
        cutoff_hz=7000,
        decay_frames=2600,
        lowpass_hz=0,
    )
    out = apply_micro_timing([event], 8000, RATE)
    assert out[0].hits[0].frame == 100
    assert out[0].hits[0].drift_frames == 0


def test_the_noise_is_keyed_on_the_grid(motorik_plan: Plan) -> None:
    """The voice's noise is keyed on the grid, so a drift is timing, not timbre.

    Moving a hit's frame and its drift by the same amount leaves the grid
    frame alone, and the voice must come out sample for sample identical. If
    the noise followed the played frame instead, every drift would re-draw
    the kit and c33 could not have been a representation-only change.
    """
    event = next(event for event in _drum_events(motorik_plan) if event.kind == "hat" and event.hits)
    hit = event.hits[0]
    shifted = hit.model_copy(update={"frame": hit.frame + 7, "drift_frames": hit.drift_frames + 7})
    assert shifted.grid_frame() == hit.grid_frame()
    assert np.array_equal(render_hat(event, hit, RATE, 1.0), render_hat(event, shifted, RATE, 1.0))
