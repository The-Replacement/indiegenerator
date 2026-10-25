"""c23 smoke tests: arrangement_mutes validator and bass offset default."""

from __future__ import annotations

import pytest

from indiegen.compose import compose
from indiegen.config import BassCard, load_preset
from indiegen.errors import PlanError
from indiegen.plan import ArrangementMute, BassEvent

RATE = 44100


def test_arrangement_mutes_validator_rejects_non_poles() -> None:
    with pytest.raises(PlanError):
        ArrangementMute(kind="pad", section_index=0, mute=500)


def test_arrangement_mutes_validator_accepts_poles() -> None:
    for v in (0, 1000):
        m = ArrangementMute(kind="pad", section_index=0, mute=v)
        assert m.mute == v


def test_bass_midi_offset_default_is_minus_12() -> None:
    f = BassCard.model_fields["midi_offset_semitones"]
    assert f.default == -12


def _bass_hits(offset: int) -> list[int]:
    """Motorik's bass line with the card's offset set to ``offset``."""
    preset = load_preset("motorik")
    entry = preset.lanes[0]
    lane = entry.parameters
    techniques = [
        card.model_copy(update={"midi_offset_semitones": offset}) if isinstance(card, BassCard) else card
        for card in lane.techniques
    ]
    lane = lane.model_copy(update={"techniques": techniques})
    preset = preset.model_copy(update={"lanes": [entry.model_copy(update={"parameters": lane})]})
    plan = compose(preset, 1042, 60 * RATE)
    return [hit.midi for event in plan.events if isinstance(event, BassEvent) for hit in event.hits]


def test_bass_midi_offset_moves_the_bass_line() -> None:
    """Y7: the field is a consumed knob, not a default nothing reads.

    The plan's bass voice-leading smooths a later leap, so the first hit is
    the one that carries the offset whole: it has no previous note.
    """
    default = _bass_hits(-12)
    octave_up = _bass_hits(0)
    assert default
    assert len(default) == len(octave_up)
    assert octave_up[0] == default[0] + 12
    assert octave_up != default
