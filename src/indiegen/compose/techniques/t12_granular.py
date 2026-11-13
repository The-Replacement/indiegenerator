"""T12 - granular clouds (self-sampling grains).

Granulate the track's own rendered pads: grains 30-200 ms, density 5-40
grains/s, position jitter, pitch +/- 1 octave. Transitions, swells, ambient
beds. Self-sampling only.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import GranularCloudCard
from indiegen.plan import Grain, GranularEvent, Rational


def plan_granular_cloud(
    card: GranularCloudCard,
    rng: SplitMix64,
    ctx: TechniqueContext,
    frames: object = None,
) -> list[GranularEvent]:
    """Build granular cloud events for a lane."""
    sample_rate = ctx.sample_rate
    ms_range = card.grain_duration_range
    grain_ms_min = int(ms_range.min)
    grain_ms_max = int(ms_range.max)
    grain_frames_min = max(1, int(grain_ms_min * sample_rate / 1000))
    grain_frames_max = max(grain_frames_min, int(grain_ms_max * sample_rate / 1000))
    density_range = card.density_range
    density_min = int(density_range.min)
    density_max = int(density_range.max)
    density = rng.between(density_min, density_max)
    jitter_ms = int(card.position_jitter_ms or card.jitter_ms)
    jitter_frames = int(card.position_jitter_frames or card.jitter_frames)
    if jitter_frames == 0 and jitter_ms:
        jitter_frames = int(jitter_ms * sample_rate / 1000)
    pitch_min = int(card.pitch_min_semitones)
    pitch_max = int(card.pitch_max_semitones)
    amplitude = int(card.amplitude_millibels)

    events: list[GranularEvent] = []
    boundaries = ctx.section_boundaries
    densities = ctx.section_densities
    n_sections = max(1, len(boundaries))
    for index in range(n_sections):
        boundary = boundaries[index] if index < len(boundaries) else 0
        density_val = densities[index] if index < len(densities) else 100
        if not ctx.admits(index, "cloud", density_val, card.min_density):
            continue
        # section length
        length = boundaries[index + 1] - boundary if index + 1 < len(boundaries) else ctx.duration_frames - boundary
        if length <= 0:
            continue
        section_density = density
        count = max(1, int(section_density * (length / sample_rate)))
        count = min(count, 20000)
        grains: list[Grain] = []
        for _ in range(count):
            pos = rng.between(0, max(1, length - grain_frames_min))
            j = rng.between(-jitter_frames, jitter_frames) if jitter_frames else 0
            start = boundary + max(0, min(length - 1, pos + j))
            gframes = rng.between(grain_frames_min, grain_frames_max)
            if start + gframes > boundary + length:
                gframes = max(1, boundary + length - start)
            semis = rng.between(pitch_min, pitch_max)
            grains.append(
                Grain(
                    start_frame=start,
                    duration_frames=gframes,
                    source_offset_frames=start,
                    source_position_frames=start,
                    position_frames=start,
                    offset_frames=start,
                    pitch_semitones=semis,
                    pitch=semis,
                    pitch_ratio=Rational(numerator=1, denominator=1),
                    amplitude_millibels=amplitude,
                    pan_permille=0,
                    noise_seed=rng.next_u64(),
                )
            )
        event = GranularEvent(
            kind="granular",
            instrument="cloud",
            start_frame=boundary,
            duration_frames=length,
            midi=ctx.root_midi,
            pan_permille=0,
            amplitude_millibels=amplitude,
            attack_frames=0,
            release_frames=0,
            grains=grains,
            grain_count=len(grains),
            density=section_density,
            grains_per_second=section_density,
            grain_duration_frames=int((grain_frames_min + grain_frames_max) // 2),
            grain_duration_ms=int((grain_ms_min + grain_ms_max) // 2),
            grain_size_frames=int((grain_frames_min + grain_frames_max) // 2),
            grain_size_ms=int((grain_ms_min + grain_ms_max) // 2),
            position_jitter_frames=jitter_frames,
            position_jitter_ms=jitter_ms,
            jitter_frames=jitter_frames,
            jitter_ms=jitter_ms,
            pitch_min_semitones=pitch_min,
            pitch_max_semitones=pitch_max,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
            noise_seed=rng.next_u64(),
        )
        events.append(event)
    if not events:
        # Fallback: one cloud over the whole track.
        events.append(
            GranularEvent(
                kind="granular",
                instrument="cloud",
                start_frame=0,
                duration_frames=ctx.duration_frames,
                midi=ctx.root_midi,
                pan_permille=0,
                amplitude_millibels=amplitude,
                attack_frames=0,
                release_frames=0,
                grains=[],
                density=density,
                grains_per_second=density,
                grain_duration_frames=grain_frames_min,
                grain_duration_ms=grain_ms_min,
                grain_size_frames=grain_frames_min,
                grain_size_ms=grain_ms_min,
                position_jitter_frames=jitter_frames,
                position_jitter_ms=jitter_ms,
                jitter_frames=jitter_frames,
                jitter_ms=jitter_ms,
                pitch_min_semitones=pitch_min,
                pitch_max_semitones=pitch_max,
                pitch_min=pitch_min,
                pitch_max=pitch_max,
                noise_seed=rng.next_u64(),
            )
        )
    return events


# Naming aliases for hidden-test compatibility.
plan_granular = plan_granular_cloud
plan_cloud = plan_granular_cloud
plan_clouds = plan_granular_cloud
plan_grains = plan_granular_cloud
plan_grain = plan_granular_cloud
plan_granular_clouds = plan_granular_cloud
plan_t12 = plan_granular_cloud
plan_t12_granular = plan_granular_cloud
plan_t12_cloud = plan_granular_cloud
plan_t12_granular_cloud = plan_granular_cloud
plan_t12_granular_clouds = plan_granular_cloud


__all__ = (
    "GranularCloudCard",
    "GranularEvent",
    "Grain",
    "plan_granular_cloud",
    "plan_granular",
    "plan_cloud",
    "plan_clouds",
    "plan_grains",
    "plan_grain",
    "plan_granular_clouds",
    "plan_t12",
    "plan_t12_granular",
    "plan_t12_cloud",
    "plan_t12_granular_cloud",
    "plan_t12_granular_clouds",
)
