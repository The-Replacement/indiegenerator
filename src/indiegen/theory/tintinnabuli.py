"""Tintinnabuli theory: the tonic triad and Pärt's T-voice position rule.

This module is a stable import surface for the rule that lives with the
other scale helpers in :mod:`indiegen.theory.scales`. The T-voice is a pure
function of the M-voice note and the declared armature (position and range
direction); every result is a tonic-triad member.
"""

from __future__ import annotations

from indiegen.theory.scales import (
    derive_second_voice as derive_second_voice,
)
from indiegen.theory.scales import (
    derive_t_voice_midi as derive_t_voice_midi,
)
from indiegen.theory.scales import (
    derive_tintinnabuli_tone as derive_tintinnabuli_tone,
)
from indiegen.theory.scales import (
    position_rule as position_rule,
)
from indiegen.theory.scales import (
    second_voice as second_voice,
)
from indiegen.theory.scales import (
    t_voice as t_voice,
)
from indiegen.theory.scales import (
    t_voice_midi as t_voice_midi,
)
from indiegen.theory.scales import (
    tintinnabuli as tintinnabuli,
)
from indiegen.theory.scales import (
    tintinnabuli_t_voice as tintinnabuli_t_voice,
)
from indiegen.theory.scales import (
    tintinnabuli_voice as tintinnabuli_voice,
)
from indiegen.theory.scales import (
    tonic_triad as tonic_triad,
)

__all__ = (
    "derive_second_voice",
    "derive_t_voice_midi",
    "derive_tintinnabuli_tone",
    "position_rule",
    "second_voice",
    "t_voice",
    "t_voice_midi",
    "tintinnabuli",
    "tintinnabuli_t_voice",
    "tintinnabuli_voice",
    "tonic_triad",
)
