"""Tintinnabuli second voice: the T-voice is a rule, not a draw.

The acceptance property is structural: every T-voice note is a member of the
section's tonic triad, and it is derived from the M-voice note and the
declared armature alone. The M-voice is the motif the lane already plans; the
card is an armature over it. These tests exercise the pure rule directly, the
derivation from synthetic M events, and the composed plan.
"""

from __future__ import annotations

import pytest

from indiegen.compose import compose, director
from indiegen.compose.context import TechniqueContext
from indiegen.compose.planner import CARD_SPECS
from indiegen.compose.techniques.t15_tintinnabuli import plan_tintinnabuli
from indiegen.config import TintinnabuliCard, load_preset
from indiegen.plan import DirectorMove, PluckEvent, Rational
from indiegen.theory.scales import (
    MODE_INTERVALS,
    tintinnabuli_t_voice,
    tonic_triad,
)

RATE: int = 44100
ROOT: int = 60

TRIAD_MODES: tuple[str, ...] = ("major", "minor", *tuple(MODE_INTERVALS))


def _triad_classes(root: int, mode: str) -> set[int]:
    return {(tone - root) % 12 for tone in tonic_triad(root, mode)}


@pytest.mark.parametrize("mode", TRIAD_MODES)
def test_every_t_voice_note_is_a_tonic_triad_member(mode: str) -> None:
    """The property the issue asks for: the rule only ever picks triad tones."""
    classes = _triad_classes(ROOT, mode)
    for m_midi in range(24, 97):
        for position in range(1, 6):
            for direction in (-1, 1, "inferior", "superior"):
                for process in ("constant", "alternating", "step"):
                    t_midi = tintinnabuli_t_voice(
                        m_midi,
                        ROOT,
                        mode,
                        position,
                        direction,
                        index=3,
                        process=process,
                    )
                    assert (t_midi - ROOT) % 12 in classes, (
                        f"mode={mode} m={m_midi} pos={position} dir={direction} process={process} -> t={t_midi}"
                    )


def test_position_one_inferior_is_the_nearest_triad_tone_below() -> None:
    """Pärt's position 1: the nearest triad tone below the M-voice."""
    mode = "major"
    members = sorted({ROOT + 12 * octave + interval for octave in range(-6, 7) for interval in (0, 4, 7)})
    for m_midi in range(30, 91):
        below = [tone for tone in members if tone < m_midi]
        assert below
        assert tintinnabuli_t_voice(m_midi, ROOT, mode, 1, "inferior") == max(below)


def test_position_one_superior_is_the_nearest_triad_tone_above() -> None:
    """The same rule mirrored: position 1 above is the nearest tone above."""
    mode = "major"
    members = sorted({ROOT + 12 * octave + interval for octave in range(-6, 7) for interval in (0, 4, 7)})
    for m_midi in range(30, 91):
        above = [tone for tone in members if tone > m_midi]
        assert above
        assert tintinnabuli_t_voice(m_midi, ROOT, mode, 1, "superior") == min(above)


def test_position_two_is_the_next_triad_tone_out() -> None:
    mode = "major"
    members = sorted({ROOT + 12 * octave + interval for octave in range(-6, 7) for interval in (0, 4, 7)})
    for m_midi in range(30, 91):
        below = sorted((tone for tone in members if tone < m_midi), reverse=True)
        assert tintinnabuli_t_voice(m_midi, ROOT, mode, 2, "inferior") == below[1]


def test_the_rule_is_pure_and_deterministic() -> None:
    first = tintinnabuli_t_voice(67, ROOT, "minor", 2, "inferior", index=1, process="alternating")
    for _ in range(5):
        assert tintinnabuli_t_voice(67, ROOT, "minor", 2, "inferior", index=1, process="alternating") == first


def test_the_card_is_registered_in_card_specs() -> None:
    assert "tintinnabuli" in CARD_SPECS


def _card(**overrides: object) -> TintinnabuliCard:
    values: dict[str, object] = {
        "kind": "tintinnabuli",
        "min_density": 0,
        "position": 1,
        "range_direction": "inferior",
        "process": "constant",
        "feedback_num_min": 900,
        "feedback_num_max": 990,
        "feedback_den": 1000,
        "brightness": Rational(numerator=1, denominator=2),
        "pluck_position_permille": 150,
        "detune_cents": 5,
        "amplitude_millibels": -6000,
        "tonic_triad_mode": "auto",
    }
    values.update(overrides)
    return TintinnabuliCard.model_validate(values)


def _ctx() -> TechniqueContext:
    return TechniqueContext(
        preset="tintinnabuli",
        seed=1042,
        lane="tintinnabuli",
        scale_midi=[60, 62, 64, 65, 67, 69, 71, 72],
        root_midi=ROOT,
        sample_rate=RATE,
        duration_frames=8 * RATE,
        frames_per_beat=RATE,
        frames_per_bar=4 * RATE,
        attack_frames=0,
        release_frames=0,
        section_boundaries=[0, 8 * RATE],
        section_densities=[80],
        section_scales=[[60, 62, 64, 65, 67, 69, 71, 72]],
        section_roots=[ROOT],
        section_functions=["plateau"],
    )


def _m_events(count: int = 4) -> list[PluckEvent]:
    return [
        PluckEvent(
            kind="pluck",
            instrument="motif",
            start_frame=index * RATE,
            duration_frames=RATE // 2,
            midi=ROOT + 12 + index,
            pan_permille=0,
            amplitude_millibels=-6000,
            attack_frames=0,
            release_frames=0,
            feedback=Rational(numerator=900, denominator=1000),
            brightness=Rational(numerator=1, denominator=2),
            pluck_position_permille=150,
            detune_cents=0,
            excitation_seed=1000 + index,
        )
        for index in range(count)
    ]


def test_the_derivation_emits_one_triad_t_note_per_m_note() -> None:
    events = plan_tintinnabuli(_m_events(), _card(), _ctx(), ["major"])
    assert len(events) == 4
    classes = _triad_classes(ROOT, "major")
    for m_event, t_event in zip(_m_events(), events, strict=True):
        assert isinstance(t_event, PluckEvent)
        assert t_event.instrument == "tintinnabuli"
        assert t_event.start_frame == m_event.start_frame
        assert t_event.duration_frames == m_event.duration_frames
        assert (t_event.midi - ROOT) % 12 in classes


def test_the_derivation_uses_the_section_root_and_triad_mode() -> None:
    ctx = _ctx().model_copy(
        update={
            "section_roots": [50],
            "section_scales": [[50, 52, 53, 55, 57, 59, 60, 62]],
        }
    )
    events = plan_tintinnabuli(_m_events(), _card(tonic_triad_mode="minor"), ctx, ["dorian"])
    classes = _triad_classes(50, "minor")
    for event in events:
        assert (event.midi - 50) % 12 in classes


def test_the_derivation_follows_the_section_mode_when_auto() -> None:
    ctx = _ctx().model_copy(update={"section_roots": [50]})
    events = plan_tintinnabuli(_m_events(), _card(tonic_triad_mode="auto"), ctx, ["phrygian"])
    classes = _triad_classes(50, "phrygian")
    for event in events:
        assert (event.midi - 50) % 12 in classes


def test_the_derivation_respects_min_density() -> None:
    ctx = _ctx().model_copy(update={"section_densities": [10]})
    events = plan_tintinnabuli(_m_events(), _card(min_density=50), ctx, ["major"])
    assert events == []


def _preset_with_tintinnabuli(presets_dir, **overrides: object):
    preset = load_preset("ambient", presets_dir=presets_dir)
    entry = preset.lanes[0]
    lane = entry.parameters
    card = _card(**overrides)
    new_lane = lane.model_copy(update={"techniques": [card]})
    new_entry = entry.model_copy(update={"parameters": new_lane})
    return preset.model_copy(update={"lanes": [new_entry]})


def _section_for(plan, frame: int):
    return next(section for section in plan.sections if section.start_frame <= frame < section.end_frame)


def test_the_composed_plan_derives_t_from_the_motif(presets_dir) -> None:
    """The M-voice is the motif the lane already plans, not a pedal."""
    preset = _preset_with_tintinnabuli(presets_dir, position=1)
    plan = compose(preset, 1042, 30 * RATE)
    m_events = [event for event in plan.events if event.instrument == "motif"]
    t_events = [event for event in plan.events if event.instrument == "tintinnabuli"]
    assert m_events and t_events
    assert len(m_events) == len(t_events)
    for index, (m_event, t_event) in enumerate(zip(m_events, t_events, strict=True)):
        section = _section_for(plan, t_event.start_frame)
        classes = _triad_classes(section.root_midi, section.mode)
        assert (t_event.midi - section.root_midi) % 12 in classes
        assert m_event.midi != t_event.midi
        # AC6: the T-voice replays from the M-voice pitches and the plan's
        # armature alone - no hidden draw, no per-event state.
        assert t_event.midi == tintinnabuli_t_voice(
            m_event.midi,
            section.root_midi,
            section.mode,
            plan.tintinnabuli_position,
            plan.tintinnabuli_range_direction,
            index=index,
            process=plan.tintinnabuli_process,
        )


def test_the_armature_survives_the_director_round_trip(presets_dir) -> None:
    """exclude=True must not let director() reset the armature."""
    preset = _preset_with_tintinnabuli(presets_dir, range_direction="superior", position=2, process="alternating")
    plan = compose(preset, 1042, 30 * RATE)
    assert plan.tintinnabuli_position == 2
    assert plan.tintinnabuli_range_direction == 1
    assert plan.tintinnabuli_process == "alternating"
    assert plan.tintinnabuli_tonic_triad_mode == "auto"
    directed = director(plan)
    assert directed.tintinnabuli_position == 2
    assert directed.tintinnabuli_range_direction == 1
    assert directed.tintinnabuli_process == "alternating"
    assert directed.tintinnabuli_tonic_triad_mode == "auto"


def test_the_director_moves_the_t_voice_to_a_new_position(presets_dir) -> None:
    """The new _HANDLERS key really moves the T-voice."""
    preset = _preset_with_tintinnabuli(presets_dir, range_direction="inferior", position=1)
    plan = compose(preset, 1042, 30 * RATE)
    move = DirectorMove(
        sample=0,
        strategy="move_tintinnabuli_position",
        detail="test",
        parameter=2,
        crossfade_frames=0,
        applies_to=["tintinnabuli"],
    )
    moved = director(plan.model_copy(update={"strategy_deck": [move]}))
    before = [event.midi for event in plan.events if event.instrument == "tintinnabuli"]
    after = [event.midi for event in moved.events if event.instrument == "tintinnabuli"]
    assert before != after
    assert moved.director_log == [move]
    for event in moved.events:
        if event.instrument != "tintinnabuli":
            continue
        section = _section_for(moved, event.start_frame)
        classes = _triad_classes(section.root_midi, section.mode)
        assert (event.midi - section.root_midi) % 12 in classes
