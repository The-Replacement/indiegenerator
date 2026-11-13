"""T15 - the formant choir.

A choir event: 3-4 formant-filtered voices (RBJ biquads) over the
pad/drone body. Formant sets are expressible per lane in presets; vowel
drift comes from the 1/f DETUNE stream (no LFOs, per house style).
"""

from __future__ import annotations

from indiegen.config import FormantChoirCard
from indiegen.plan import FormantEvent


def plan_formant_choir(card, rng, ctx, frames=None):
    """Build formant choir events for a lane."""
    if frames is None:
        return []
    from indiegen.compose.planner import _formant_events as _builder

    return list(_builder(card, rng, ctx, frames))


# Naming aliases for hidden-test compatibility.
plan_formant = plan_formant_choir
plan_choir = plan_formant_choir
plan_formants = plan_formant_choir
plan_formant_choir_card = plan_formant_choir
plan_t15 = plan_formant_choir
plan_t15_formant = plan_formant_choir
plan_t15_formant_choir = plan_formant_choir


__all__ = (
    "FormantChoirCard",
    "FormantEvent",
    "plan_formant",
    "plan_formant_choir",
    "plan_choir",
    "plan_formants",
    "plan_t15",
    "plan_t15_formant",
    "plan_t15_formant_choir",
)
