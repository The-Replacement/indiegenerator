"""T13 - the Karplus-Strong guitar.

Tuned plucks with a high feedback ratio, a detuned pair for chorus, and the
occasional strummed cluster. This is the station's signature timbre: §3 has
it present in every lane, through a dotted-eighth delay.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import PluckCard
from indiegen.plan import PluckEvent, Rational


def plan_plucks(card: PluckCard, rng: SplitMix64, ctx: TechniqueContext) -> list[PluckEvent]:
    """Draw the plucks of the track, each as a detuned pair."""
    count = rng.between(card.count.min, card.count.max)
    spacing = rng.between(card.spacing_seconds.min, card.spacing_seconds.max) * ctx.sample_rate
    duration = rng.between(card.duration_seconds.min, card.duration_seconds.max) * ctx.sample_rate
    feedback = Rational(
        numerator=rng.between(card.feedback_num_min, card.feedback_num_max),
        denominator=card.feedback_den,
    )
    position = rng.between(0, 1000)
    excitation_seed = rng.next_u64()

    events: list[PluckEvent] = []
    start = 0
    for _ in range(count):
        if start >= ctx.duration_frames:
            break
        length = min(duration, ctx.duration_frames - start)
        # The layer only plays in the sections the arrangement has reached.
        section = ctx.section_at(start)
        densities = ctx.section_densities
        pluck_density = densities[min(section, len(densities) - 1)] if densities else 100
        if not ctx.admits(section, "ks", pluck_density, card.min_density):
            start += spacing
            continue
        for voice, detune in ((0, 0), (1, card.detune_cents)):
            events.append(
                PluckEvent(
                    kind="pluck",
                    instrument="ks",
                    start_frame=start,
                    duration_frames=length,
                    midi=ctx.root_midi,
                    pan_permille=0,
                    amplitude_millibels=-4000,
                    attack_frames=0,
                    release_frames=0,
                    feedback=feedback,
                    brightness=card.brightness,
                    pluck_position_permille=position,
                    detune_cents=detune,
                    excitation_seed=excitation_seed + voice,
                )
            )
        start += spacing
    return events
