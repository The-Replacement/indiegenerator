"""Compose-time techniques.

A technique returns data and may roll dice. It never renders audio and never
imports the render path.
"""

from __future__ import annotations

from indiegen.compose.techniques.t1_polyperiod import plan_poly_period as plan_poly_period
from indiegen.compose.techniques.t2_phasing import plan_phased_pair as plan_phased
from indiegen.compose.techniques.t2_phasing import plan_phased_pair as plan_phased_pair
from indiegen.compose.techniques.t2_phasing import plan_phased_pair as plan_phasing
from indiegen.compose.techniques.t2_phasing import plan_phased_pair as plan_reich_phasing
from indiegen.compose.techniques.t2_phasing import plan_phased_pair as plan_t2
from indiegen.compose.techniques.t5_dejavu import plan_deja_vu as plan_deja_vu
from indiegen.compose.techniques.t11_drone import plan_drone as plan_drone
from indiegen.compose.techniques.t13_pluck import plan_plucks as plan_plucks
from indiegen.compose.techniques.t15_tintinnabuli import plan_tintinnabuli as plan_duo
from indiegen.compose.techniques.t15_tintinnabuli import plan_tintinnabuli as plan_tintinnabuli
from indiegen.compose.techniques.t15_tintinnabuli import plan_tintinnabuli as plan_tintinnabuli_duo
from indiegen.compose.techniques.t15_tintinnabuli import plan_tintinnabuli as plan_tintinnabuli_second_voice
from indiegen.theory.scales import (
    derive_t_voice_midi as derive_t_voice_midi,
)
from indiegen.theory.scales import (
    derive_tintinnabuli_tone as derive_tintinnabuli_tone,
)
from indiegen.theory.scales import (
    t_voice_midi as t_voice_midi,
)
from indiegen.theory.scales import (
    tintinnabuli_t_voice as tintinnabuli_t_voice,
)

__all__ = (
    "derive_t_voice_midi",
    "derive_tintinnabuli_tone",
    "plan_deja_vu",
    "plan_drone",
    "plan_phased",
    "plan_phased_pair",
    "plan_phasing",
    "plan_plucks",
    "plan_poly_period",
    "plan_reich_phasing",
    "plan_duo",
    "plan_t2",
    "plan_tintinnabuli",
    "plan_tintinnabuli_duo",
    "plan_tintinnabuli_second_voice",
    "t_voice_midi",
    "tintinnabuli_t_voice",
)
