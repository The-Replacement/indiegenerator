"""T11 - a spectral drone stack (Cluster, Harmonia).

One fundamental, a handful of partials, each with its own slow drift on
detune and on amplitude. The movement is the beating of near-unison partials,
not a filter sweep: the drift is 1/f, clipped to the declared depth, and the
partials are exact rational ratios.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import DroneCard
from indiegen.plan import AmplitudeLfo, DetuneLfo, DriftingPartial, DroneEvent


def plan_drone(
    card: DroneCard,
    rng: SplitMix64,
    ctx: TechniqueContext,
    start_frame: int,
    duration_frames: int,
    root_midi: int,
    tuning_system: int = 0,
) -> DroneEvent:
    """Draw the partials of one drone stack.

    The drone is scheduled per section, so a modal shift is heard in the
    fundamental and not only in the notes on top of it.
    """
    count = rng.between(card.partial_count.min, card.partial_count.max)
    ratios = list(card.ratios)
    if tuning_system == 1:
        ratios = [r for r in ratios if not (r.numerator == 5 and r.denominator == 4)]
    partials: list[DriftingPartial] = []
    for index in range(count):
        ratio = ratios[index % len(ratios)]
        detune = rng.between(card.detune_cents_range.min, card.detune_cents_range.max)
        partials.append(
            DriftingPartial(
                ratio=ratio,
                amplitude_millibels=-300 - index * 120,
                detune_cents=detune,
                detune_lfo=DetuneLfo(rate=card.detune_lfo_rate, depth_cents=card.detune_lfo_depth_cents),
                amplitude_lfo=AmplitudeLfo(
                    rate=card.amplitude_lfo_rate,
                    depth_millibels=card.amplitude_lfo_depth_millibels,
                ),
            )
        )
    return DroneEvent(
        kind="drone",
        instrument="drone",
        start_frame=start_frame,
        duration_frames=duration_frames,
        midi=root_midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=ctx.attack_frames,
        release_frames=ctx.release_frames,
        partials=partials,
        noise_seed=rng.next_u64(),
    )
