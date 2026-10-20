"""compose(): the only place randomness exists.

The RNG is created here, every draw happens here, and it dies when this
function returns. Everything downstream reads the frozen Plan and never rolls.
"""

from __future__ import annotations

from indiegen.compose.rng import SplitMix64, seed_from_bytes
from indiegen.config import Preset, canonical_preset_json
from indiegen.errors import PlanError
from indiegen.plan import SAMPLE_RATE, NoteEvent, Plan, SectionPlan


def pick_lane(preset: Preset, rng: SplitMix64) -> str:
    """The weighted lane pick. Called from compose, with the compose RNG."""
    if preset.kind == "lane":
        return preset.lanes[0].lane
    entries = [entry for entry in preset.lanes if entry.weight > 0]
    if not entries:
        raise PlanError("station blend has no lane with a positive weight", preset=preset.name)
    total = sum(entry.weight for entry in entries)
    draw = rng.below(total)
    for entry in entries:
        draw -= entry.weight
        if draw < 0:
            return entry.lane
    return entries[-1].lane


def _section_boundaries(frames: int, frames_per_bar: int, section_count: int) -> list[int]:
    """Bar-aligned section boundaries, with the last section running to the end.

    A slow tempo can make one bar longer than the whole track, so the
    boundaries are clamped to keep every section at least one frame long.
    """
    bars_total = max(section_count, frames // frames_per_bar)
    boundaries: list[int] = [0]
    for index in range(1, section_count):
        bar = round(index * bars_total / section_count)
        boundary = min(frames - (section_count - index), bar * frames_per_bar)
        boundaries.append(max(boundary, boundaries[-1] + 1))
    boundaries.append(frames)
    return boundaries


def compose(preset: Preset, seed: int, duration_frames: int | None = None) -> Plan:
    """Build the frozen Plan from a preset and a seed."""
    material = canonical_preset_json(preset) + b"\x00" + str(seed).encode("utf-8")
    rng = SplitMix64(seed_from_bytes(material))

    station = preset.station
    lane_name = pick_lane(preset, rng)
    lane = next(entry.parameters for entry in preset.lanes if entry.lane == lane_name)

    if duration_frames is None:
        frames = rng.between(lane.duration_range_seconds[0], lane.duration_range_seconds[1]) * SAMPLE_RATE
    else:
        frames = duration_frames
    if frames <= 0:
        raise PlanError("duration must be positive", preset=preset.name, seed=seed)

    tempo = rng.between(lane.tempo_range_bpm[0], lane.tempo_range_bpm[1])
    frames_per_beat = round(60 * SAMPLE_RATE / tempo)
    beats_per_bar = lane.meter[0] * 4 // lane.meter[1]
    frames_per_bar = frames_per_beat * beats_per_bar
    section_count = rng.between(lane.section_count_range[0], lane.section_count_range[1])

    motif = list(rng.choice(station.motif_bank))
    title_words = rng.choice(station.title_words), rng.choice(station.title_words)

    boundaries = _section_boundaries(frames, frames_per_bar, section_count)
    sections: list[SectionPlan] = []
    for index in range(section_count):
        profile = station.section_profiles[index % len(station.section_profiles)]
        start = boundaries[index]
        end = boundaries[index + 1]
        sections.append(
            SectionPlan(
                index=index,
                function=profile.function,
                start_frame=start,
                end_frame=end,
                bars=max(1, (end - start) // frames_per_bar),
                density=profile.density,
                level_millibels=profile.level_millibels,
                motif=list(motif),
                techniques=[card.name for card in lane.techniques],
            )
        )

    card = lane.techniques[0]
    detunes = [rng.between(card.detune_min_cents, card.detune_max_cents) for _ in range(card.partials - 1)]
    event = NoteEvent(
        instrument=card.name,
        start_frame=0,
        duration_frames=frames,
        midi=rng.choice(lane.scale_midi),
        velocity_millibels=card.amplitude_millibels,
        partials=card.partials,
        partial_detune_cents=detunes,
        lfo_rate=card.lfo_rate,
        lfo_depth_cents=card.lfo_depth_cents,
        amplitude_millibels=card.amplitude_millibels,
        pan_permille=0,
        attack_frames=lane.attack_frames,
        release_frames=lane.release_frames,
    )

    plan = Plan(
        version=1,
        format_version=station.format_version,
        preset=preset.name,
        seed=seed,
        lane=lane.lane,
        alias=lane.alias,
        album=lane.album,
        file_token=lane.file_token,
        title=f"{title_words[0]} {title_words[1]}",
        sample_rate=SAMPLE_RATE,
        channels=2,
        duration_frames=frames,
        duration_range_frames=[
            lane.duration_range_seconds[0] * SAMPLE_RATE,
            lane.duration_range_seconds[1] * SAMPLE_RATE,
        ],
        tempo_bpm=tempo,
        frames_per_beat=frames_per_beat,
        meter_numerator=lane.meter[0],
        meter_denominator=lane.meter[1],
        scale_midi=list(lane.scale_midi),
        palette=list(station.palette),
        fx_sends=list(lane.fx_sends),
        techniques=list(lane.techniques),
        strategy_deck=list(station.strategy_deck),
        section_count_range=list(lane.section_count_range),
        section_count=section_count,
        sections=sections,
        motif=motif,
        title_words=list(station.title_words),
        lane_weights=list(station.lane_weights),
        dither_seed=rng.next_u64(),
        dither_lsb=station.dither_lsb,
        master_gain_millibels=station.target_peak_millibels,
        ceiling_millibels=station.ceiling_millibels,
        fade_in_frames=station.fade_in_frames,
        fade_out_frames=station.fade_out_frames,
        section_crossfade_frames=station.section_crossfade_frames,
        track_number=station.track_number,
        events=[event],
        director_log=[],
    )
    return plan
