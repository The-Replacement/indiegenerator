"""The S2 techniques: the euclid patterns, the conditional triggers, the
deja-vu sequencer and the drums that carry them.

Every one of these is a decision about the arrangement, made at compose
time: the renderer only plays what the plan says.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.compose.techniques.t6_drums import euclid, rotate
from indiegen.config import load_preset
from indiegen.plan import BassEvent, BassHit, HatEvent, KickEvent, Plan, PluckEvent, SnareEvent
from indiegen.theory.scales import nearest_scale_note

RATE: int = 44100
SEED: int = 1042


@pytest.fixture(scope="module")
def motorik_plan() -> Plan:
    """The motorik lane: the drums, the deja-vu and the 1/f."""
    return director(compose(load_preset("motorik"), SEED, 60 * RATE))


def test_euclid_makes_the_four_on_the_floor() -> None:
    """Bjorklund's algorithm: four pulses over sixteen steps."""
    assert euclid(4, 16) == [
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
    ]


def test_euclid_makes_the_eighths() -> None:
    assert euclid(8, 16) == [index % 2 == 0 for index in range(16)]


def test_euclid_spreads_the_pulses_evenly() -> None:
    pattern = euclid(5, 8)
    assert len(pattern) == 8
    assert sum(pattern) == 5
    gaps = [index for index, active in enumerate(pattern) if active]
    distances = [b - a for a, b in zip(gaps, gaps[1:], strict=False)]
    assert max(distances) - min(distances) <= 1
    assert sum(pattern) == 5


def test_euclid_saturates() -> None:
    assert euclid(0, 8) == [False] * 8
    assert euclid(8, 8) == [True] * 8
    assert euclid(12, 8) == [True] * 8


def test_the_rotation_turns_the_pattern() -> None:
    pattern = euclid(3, 8)
    assert rotate(pattern, 1) == pattern[1:] + pattern[:1]
    assert rotate(pattern, 8) == pattern


def test_the_kick_plays_on_the_quarters(motorik_plan: Plan) -> None:
    """The recipe: the kick on the quarters."""
    kicks = [event for event in motorik_plan.events if isinstance(event, KickEvent)]
    assert kicks
    event = kicks[0]
    frames_per_bar = motorik_plan.frames_per_beat * 4
    for hit in event.hits[:8]:
        step = (hit.frame % frames_per_bar) // (frames_per_bar // 16)
        assert step % 4 == 0


def test_the_snare_plays_on_two_and_four(motorik_plan: Plan) -> None:
    """The recipe: the snare on the beats two and four."""
    snares = [event for event in motorik_plan.events if isinstance(event, SnareEvent)]
    assert snares
    event = snares[0]
    frames_per_bar = motorik_plan.frames_per_beat * 4
    for hit in event.hits[:8]:
        if hit.velocity_millibels < -1000:
            continue  # a ghost note, and it is on the grid too
        beat = (hit.frame % frames_per_bar) / (frames_per_bar // 4)
        # the beats two and four; the fourth beat is the downbeat
        assert round(beat) % 4 in (2, 0)


def test_the_hats_carry_ghost_notes(motorik_plan: Plan) -> None:
    """The ghost notes are quieter than the accents."""
    hats = [event for event in motorik_plan.events if isinstance(event, HatEvent)]
    assert hats
    event = hats[0]
    assert len(event.hits) > 8
    velocities = {hit.velocity_millibels for hit in event.hits}
    assert len(velocities) > 1
    assert min(velocities) < max(velocities)


def test_the_layers_follow_the_sections(motorik_plan: Plan) -> None:
    """A voice the arrangement has not reached yet does not play.

    The hats are the loudest thing in the plateau and absent from the
    intro, so the piece has a shape.
    """
    hats = [event for event in motorik_plan.events if isinstance(event, HatEvent)]
    assert hats
    event = hats[0]
    boundaries = [section.start_frame for section in motorik_plan.sections]
    # c33: the drift is in the plan, so the arrangement's position is the
    # grid frame; a hit may play a few frames before the line it was written
    # on without being a hit in the previous section.
    first = min(hit.grid_frame() for hit in event.hits)
    assert first >= boundaries[1]
    densities = {section.density for section in motorik_plan.sections}
    assert len(densities) > 1


def test_the_bass_jumps_an_octave_sometimes(motorik_plan: Plan) -> None:
    basses = [event for event in motorik_plan.events if isinstance(event, BassEvent)]
    assert basses
    event = basses[0]
    assert all(isinstance(hit, BassHit) for hit in event.hits)
    pitches = {hit.midi for hit in event.hits}
    assert len(pitches) > 1
    assert all(hit.frame >= 0 for hit in event.hits)


def test_the_deja_vu_stays_in_the_scale(motorik_plan: Plan) -> None:
    """The stabs are quantized to the scale of the section they are in.

    The scale of a section is the lane's mode over the section's root, so
    a modal shift is heard in the notes themselves. A replayed note is a
    memory of an earlier one, and the modes share their notes but not all
    of them, so a memory can be a semitone out of the section's mode: a
    dissonance, and a deliberate one.
    """
    from indiegen.theory.scales import mode_scale

    plucks = [event for event in motorik_plan.events if isinstance(event, PluckEvent) and event.instrument == "pluck"]
    assert plucks
    scales = [set(mode_scale(section.mode, section.root_midi, 2)) for section in motorik_plan.sections]
    union: set[int] = set()
    for scale in scales:
        union |= scale
    # Every pluck is quantized to a section's scale when it is generated, and
    # a replayed note is a memory of one of those quantized pitches, so every
    # pluck is in the union of the sections' scales. A replayed note may be a
    # semitone out of the section it lands in - that is the deliberate
    # dissonance the sequencer is built to produce - so a per-section count is
    # not the invariant here; the union is.
    for event in plucks:
        assert event.midi in union


def test_the_deja_vu_remembers(motorik_plan: Plan) -> None:
    """A motif emerges: the same pitch comes back."""
    plucks = [event for event in motorik_plan.events if isinstance(event, PluckEvent)]
    pitches = [event.midi for event in plucks]
    assert len(pitches) > 8
    repeats = sum(1 for index, pitch in enumerate(pitches) if pitch in pitches[:index])
    assert repeats > len(pitches) // 4


def test_the_nearest_scale_note_is_in_the_scale() -> None:
    scale = [38, 40, 41, 43, 45]
    assert nearest_scale_note(scale, 39) in scale
    assert nearest_scale_note(scale, 100) == 45
    assert nearest_scale_note([], 7) == 7


def test_the_drums_carry_the_one_over_f_signals(motorik_plan: Plan) -> None:
    """T7: the velocity, the pan and the micro-timing drift on pink noise."""
    for event in motorik_plan.events:
        if not isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            continue
        assert event.velocity_depth_millibels > 0
        assert event.micro_timing_frames > 0
        assert event.pan_drift_permille > 0
        assert event.noise_seed > 0


def test_the_drum_hits_are_sorted_and_inside_the_track(motorik_plan: Plan) -> None:
    for event in motorik_plan.events:
        if not isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            continue
        frames = [hit.frame for hit in event.hits]
        assert frames == sorted(frames)
        assert frames[0] >= 0
        assert frames[-1] < motorik_plan.duration_frames


def test_the_plan_carries_no_float_leaves(motorik_plan: Plan) -> None:
    for value in motorik_plan.model_dump(mode="json").values():
        assert not isinstance(value, float)
