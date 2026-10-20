"""compose-time: the only place randomness exists, and the Director beside it."""

from __future__ import annotations

from indiegen.compose.director import director as director
from indiegen.compose.planner import compose as compose
from indiegen.compose.rng import SplitMix64 as SplitMix64
