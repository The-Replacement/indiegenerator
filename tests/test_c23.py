"""c23 smoke tests: arrangement_mutes validator and bass offset default."""

from __future__ import annotations

import pytest

from indiegen.errors import PlanError
from indiegen.plan import ArrangementMute


def test_arrangement_mutes_validator_rejects_non_poles() -> None:
    with pytest.raises(PlanError):
        ArrangementMute(kind="pad", section_index=0, mute=500)


def test_arrangement_mutes_validator_accepts_poles() -> None:
    for v in (0, 1000):
        m = ArrangementMute(kind="pad", section_index=0, mute=v)
        assert m.mute == v


def test_bass_midi_offset_default_is_minus_12() -> None:
    from indiegen.config import BassCard

    f = BassCard.model_fields["midi_offset_semitones"]
    assert f.default == -12
