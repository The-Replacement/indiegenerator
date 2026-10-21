"""compose(): the only place randomness exists.

The RNG is created here, every draw happens here, and it dies when this
function returns. Everything downstream reads the frozen Plan and never rolls.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64, seed_from_bytes
from indiegen.compose.techniques import plan_drone, plan_plucks, plan_poly_period
from indiegen.config import PadCard, PluckCard, PolyPeriodCard, Preset
from indiegen.errors import PlanError
from indiegen.plan import (
    SAMPLE_RATE,
    DelaySend,
    Event,
    PadEvent,
    Plan,
    ReverbSpec,
    SectionPlan,
)


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


def _pad_event(card: PadCard, rng: SplitMix64, ctx: TechniqueContext) -> PadEvent:
    """The sustained pad: the S0 instrument, with the S0 field semantics."""
    count = rng.between(card.partials.min, card.partials.max)
    detunes = [rng.between(card.detune_min_cents, card.detune_max_cents) for _ in range(count - 1)]
    return PadEvent(
        kind="pad",
        instrument="pad",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=ctx.root_midi,
        pan_permille=0,
        amplitude_millibels=card.amplitude_millibels,
        attack_frames=ctx.attack_frames,
        release_frames=ctx.release_frames,
        partials=count,
        partial_detune_cents=detunes,
        lfo_rate=card.lfo_rate,
        lfo_depth_cents=card.lfo_depth_cents,
    )


def _chord_roots(scale_midi: list[int], intervals: list[int], tones: int) -> list[int]:
    """The scale notes that can carry the chord's first tones.

    A chord tone has to be in the lane's scale, so the root is drawn from the
    notes that support the whole chord rather than from the whole scale.
    """
    wanted = intervals[:tones]
    return [root for root in scale_midi if all(root + interval in scale_midi for interval in wanted)]


def compose(preset: Preset, seed: int, duration_frames: int | None = None) -> Plan:
    """Build the frozen Plan from a preset and a seed.

    The PRNG is seeded from the preset's *identity* and the seed, not from
    the whole preset file. That keeps the draw sequence stable when a
    parameter changes, so the mutation sweep can tell a parameter that is
    consumed from one that is merely declared.
    """
    material = f"{preset.name}|{seed}".encode()
    rng = SplitMix64(seed_from_bytes(material))

    station = preset.station
    lane_name = pick_lane(preset, rng)
    lane = next(entry.parameters for entry in preset.lanes if entry.lane == lane_name)

    if duration_frames is None:
        low, high = lane.duration_range_seconds
        # A lane with a single declared duration does not draw one: the plan
        # must not depend on whether the caller passed the duration or not.
        frames = low * SAMPLE_RATE if low == high else rng.between(low, high) * SAMPLE_RATE
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
    intervals = next(
        (card.chord_intervals for card in lane.techniques if isinstance(card, PolyPeriodCard)),
        [],
    )
    roots = _chord_roots(lane.scale_midi, intervals, 3) if intervals else list(lane.scale_midi)
    root_midi = rng.choice(roots if roots else lane.scale_midi)
    dither_seed = rng.next_u64()

    ctx = TechniqueContext(
        preset=preset.name,
        seed=seed,
        lane=lane.lane,
        scale_midi=list(lane.scale_midi),
        root_midi=root_midi,
        sample_rate=SAMPLE_RATE,
        duration_frames=frames,
        frames_per_beat=frames_per_beat,
        attack_frames=lane.attack_frames,
        release_frames=lane.release_frames,
    )

    events: list[Event] = []
    for card in lane.techniques:
        if isinstance(card, PadCard):
            events.append(_pad_event(card, rng, ctx))
        elif isinstance(card, PolyPeriodCard):
            events.extend(plan_poly_period(card, rng, ctx))
        elif isinstance(card, PluckCard):
            events.extend(plan_plucks(card, rng, ctx))
        else:
            events.append(plan_drone(card, rng, ctx))

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
                techniques=[card.kind for card in lane.techniques],
            )
        )

    delay = station.delay
    delay_send = DelaySend(
        name="dotted_eighth",
        delay_frames=delay.delay_ratio.numerator * frames_per_beat // delay.delay_ratio.denominator,
        feedback=delay.feedback,
        damping=delay.damping,
        send_millibels=delay.send_millibels,
    )
    reverb = (
        ReverbSpec(
            comb_delays_frames=list(lane.reverb.comb_delays_frames),
            comb_feedback=lane.reverb.comb_feedback,
            damping=lane.reverb.damping,
            allpass_delays_frames=list(lane.reverb.allpass_delays_frames),
            allpass_feedback=lane.reverb.allpass_feedback,
            stereo_spread_frames=lane.reverb.stereo_spread_frames,
            send_millibels=lane.reverb.send_millibels,
        )
        if lane.reverb is not None
        else None
    )

    return Plan(
        version=2,
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
        techniques=[card.kind for card in lane.techniques],
        strategy_deck=list(station.strategy_deck),
        section_count_range=list(lane.section_count_range),
        section_count=section_count,
        sections=sections,
        motif=motif,
        title_words=list(station.title_words),
        lane_weights=list(station.lane_weights),
        dither_seed=dither_seed,
        dither_lsb=station.dither_lsb,
        master_gain_millibels=station.target_peak_millibels,
        ceiling_millibels=station.ceiling_millibels,
        fade_in_frames=station.fade_in_frames,
        fade_out_frames=station.fade_out_frames,
        section_crossfade_frames=station.section_crossfade_frames,
        track_number=station.track_number,
        delay_sends=[delay_send],
        reverb=reverb,
        events=events,
        director_log=[],
    )
