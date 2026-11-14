"""T8 - radiophonic splices + ring-mod test-tone interludes."""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import RadiophonicCard
from indiegen.plan import RadiophonicEvent


def plan_radiophonic(
    card: RadiophonicCard,
    rng: SplitMix64,
    ctx: TechniqueContext,
    frames: int | None = None,
) -> list[RadiophonicEvent]:
    events: list[RadiophonicEvent] = []
    duration = ctx.duration_frames
    amplitude = int(card.amplitude_millibels)
    events.append(
        RadiophonicEvent(
            kind="radiophonic",
            instrument="radiophonic",
            start_frame=0,
            duration_frames=duration,
            midi=ctx.root_midi,
            pan_permille=0,
            amplitude_millibels=amplitude,
            attack_frames=0,
            release_frames=0,
            partials=list(card.partials),
            carrier_ratio=card.carrier_ratio,
            noise_seed=rng.next_u64(),
        )
    )
    return events


plan_ring_mod = plan_radiophonic
plan_ringmod = plan_radiophonic
plan_test_tone = plan_radiophonic
plan_t8 = plan_radiophonic
plan_t8_radiophonic = plan_radiophonic


__all__ = (
    "RadiophonicCard",
    "RadiophonicEvent",
    "plan_radiophonic",
    "plan_ring_mod",
    "plan_ringmod",
    "plan_test_tone",
    "plan_t8",
    "plan_t8_radiophonic",
)
