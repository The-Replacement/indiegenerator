"""Compose-time techniques.

A technique returns data and may roll dice. It never renders audio and never
imports the render path.
"""

from __future__ import annotations

from indiegen.compose.techniques.t1_polyperiod import plan_poly_period as plan_poly_period
from indiegen.compose.techniques.t11_drone import plan_drone as plan_drone
from indiegen.compose.techniques.t13_pluck import plan_plucks as plan_plucks
