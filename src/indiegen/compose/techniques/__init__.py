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

__all__ = (
    "plan_deja_vu",
    "plan_drone",
    "plan_phased",
    "plan_phased_pair",
    "plan_phasing",
    "plan_plucks",
    "plan_poly_period",
    "plan_reich_phasing",
    "plan_t2",
)
