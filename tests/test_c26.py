"""c26: swing and 1/f onset jitter on the non-drum material.

Swing moves an odd-beat onset later by ``frames_per_beat * swing_permille //
6000`` frames (1000 = a sixth of a beat, the triplet feel) and is a no-op in
a lane with no pulse. The plucks then drift on a compose-side low-frequency
stream in ``[-melodic_jitter_frames, +melodic_jitter_frames]``. The knobs
are per lane and are stamped onto the Plan; a zero knob pair is a strict
no-op on the events themselves.
"""

from __future__ import annotations

from indiegen.compose import compose, director
from indiegen.compose.planner import _apply_groove, _on_odd_beat
from indiegen.compose.rng import groove_offsets
from indiegen.config import load_preset
from indiegen.plan import Plan, PluckEvent, Rational, RhythmEvent

SEED = 1042
SECONDS = 20
FIELDS_PER_BEAT = 1000
LONG = 10_000_000


def _plan(lane: str = "motorik") -> Plan:
    return director(compose(load_preset(lane), SEED, SECONDS * 44100))


def _pluck(start: int, duration: int = 5000) -> PluckEvent:
    return PluckEvent(
        kind="pluck",
        instrument="ks",
        start_frame=start,
        duration_frames=duration,
        midi=57,
        pan_permille=0,
        amplitude_millibels=-6000,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=997, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=320,
        detune_cents=0,
        excitation_seed=7,
    )


def _zeroed(preset: object) -> object:
    """The preset with the c26 knobs forced to zero."""
    lanes = []
    for entry in preset.lanes:  # type: ignore[attr-defined]
        parameters = entry.parameters.model_copy(update={"swing_permille": 0, "melodic_jitter_frames": 0})
        lanes.append(entry.model_copy(update={"parameters": parameters}))
    return preset.model_copy(update={"lanes": lanes})  # type: ignore[attr-defined]


def test_groove_offsets_zero_depth_is_zeros() -> None:
    assert groove_offsets(SEED, 8, 0) == [0] * 8
    assert groove_offsets(SEED, 0, 40) == []


def test_groove_offsets_bounded_and_deterministic() -> None:
    first = groove_offsets(SEED, 64, 40)
    second = groove_offsets(SEED, 64, 40)
    assert first == second
    assert len(first) == 64
    assert all(-40 <= value <= 40 for value in first)
    assert any(value != 0 for value in first)


def test_apply_groove_zero_is_a_noop() -> None:
    plan = _plan()
    events = list(plan.events)
    appearances = list(plan.motif_appearances)
    out, apps = _apply_groove(events, appearances, [0, LONG], FIELDS_PER_BEAT, "bars", 0, 0, SEED, LONG)
    assert out == events
    assert apps == appearances


def test_swing_moves_an_odd_beat_exactly() -> None:
    events = [_pluck(FIELDS_PER_BEAT)]
    out, _ = _apply_groove(list(events), [], [0, LONG], FIELDS_PER_BEAT, "bars", 1000, 0, SEED, LONG)
    # 1000 permille is a sixth of a beat.
    assert out[0].start_frame == FIELDS_PER_BEAT + FIELDS_PER_BEAT // 6


def test_swing_leaves_an_even_beat_alone() -> None:
    events = [_pluck(2 * FIELDS_PER_BEAT)]
    out, _ = _apply_groove(list(events), [], [0, LONG], FIELDS_PER_BEAT, "bars", 1000, 0, SEED, LONG)
    assert out[0].start_frame == 2 * FIELDS_PER_BEAT


def test_swing_is_a_noop_in_a_seconds_lane() -> None:
    events = [_pluck(FIELDS_PER_BEAT)]
    out, _ = _apply_groove(list(events), [], [0, LONG], FIELDS_PER_BEAT, "seconds", 1000, 0, SEED, LONG)
    assert out[0].start_frame == FIELDS_PER_BEAT


def test_jitter_is_bounded_and_deterministic() -> None:
    events = [_pluck(500_000)]
    first, _ = _apply_groove(list(events), [], [0, LONG], FIELDS_PER_BEAT, "bars", 0, 40, SEED, LONG)
    second, _ = _apply_groove(list(events), [], [0, LONG], FIELDS_PER_BEAT, "bars", 0, 40, SEED, LONG)
    assert first[0].start_frame == second[0].start_frame
    assert abs(first[0].start_frame - 500_000) <= 40


def test_hits_stay_sorted_after_swing() -> None:
    plan = _plan()
    out, _ = _apply_groove(
        list(plan.events),
        list(plan.motif_appearances),
        [section.start_frame for section in plan.sections] + [plan.duration_frames],
        plan.frames_per_beat,
        plan.pulse,
        1000,
        0,
        SEED,
        plan.duration_frames,
    )
    for event in out:
        if isinstance(event, RhythmEvent):
            frames = [hit.frame for hit in event.hits]
            assert frames == sorted(frames)


def test_every_event_stays_inside_the_track() -> None:
    plan = _plan()
    out, _ = _apply_groove(
        list(plan.events),
        list(plan.motif_appearances),
        [section.start_frame for section in plan.sections] + [plan.duration_frames],
        plan.frames_per_beat,
        plan.pulse,
        1000,
        40,
        SEED,
        plan.duration_frames,
    )
    for event in out:
        assert event.start_frame >= 0
        assert event.start_frame + event.duration_frames <= plan.duration_frames


def test_motif_appearances_track_their_plucks() -> None:
    plan = _plan()
    starts = {
        event.start_frame for event in plan.events if isinstance(event, PluckEvent) and event.instrument == "motif"
    }
    for appearance in plan.motif_appearances:
        assert appearance.start_frame in starts


def test_a_nonzero_preset_moves_the_onsets() -> None:
    warm = compose(load_preset("motorik"), SEED, SECONDS * 44100)
    cold = compose(_zeroed(load_preset("motorik")), SEED, SECONDS * 44100)  # type: ignore[arg-type]
    assert warm.swing_permille == 600
    assert warm.melodic_jitter_frames == 40
    assert cold.swing_permille == 0
    assert cold.melodic_jitter_frames == 0
    warm_starts = [event.start_frame for event in warm.events]
    cold_starts = [event.start_frame for event in cold.events]
    assert warm_starts != cold_starts
    # The groove pass draws from its own sub-stream: the main RNG's draws
    # (the title, the dither seed) must not move.
    assert warm.dither_seed == cold.dither_seed
    assert warm.title == cold.title


def test_on_odd_beat() -> None:
    assert not _on_odd_beat(0, 1000)
    assert _on_odd_beat(1000, 1000)
    assert not _on_odd_beat(2000, 1000)
    assert _on_odd_beat(3000, 1000)
    assert not _on_odd_beat(1000, 0)
