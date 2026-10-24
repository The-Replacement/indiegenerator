"""T6 - euclidean rhythms with conditional triggers.

The percussion comes from euclid(k, n) patterns: Bjorklund's algorithm
spreads k pulses as evenly as possible over n steps. The variation comes
from the conditional triggers, not from random velocity jitter: a voice
that plays "one in two" or "only in a fill" is a decision about the
arrangement, and the same seed always makes the same one.

The hits are resolved here, at compose time. The renderer plays what the
plan says.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import BassCard, HatCard, KickCard, PatternCard, PinkCard, SnareCard
from indiegen.plan import BassEvent, BassHit, DrumHit, HatEvent, KickEvent, SnareEvent

FILL_BARS: int = 1


def euclid(k: int, n: int) -> list[bool]:
    """Bjorklund's algorithm: k pulses spread over n steps.

    The pulses are as evenly spaced as the circle allows, which is the
    family Bjorklund's algorithm generates: the gaps between the pulses
    differ by at most one step. The i-th pulse sits at the i-th multiple
    of n/k, so (4, 16) is the four on the floor and (8, 16) is the eighths.
    """
    if n <= 0:
        return []
    if k <= 0:
        return [False] * n
    if k >= n:
        return [True] * n
    pattern = [False] * n
    for index in range(k):
        pattern[(index * n) // k] = True
    return pattern


def rotate(pattern: list[bool], rotation: int) -> list[bool]:
    """The pattern, turned by ``rotation`` steps."""
    if not pattern:
        return pattern
    shift = rotation % len(pattern)
    return pattern[shift:] + pattern[:shift]


def _condition_holds(
    condition: str,
    period: int,
    occurrence: int,
    step_in_bar: int,
    bar_in_section: int,
    bars_in_section: int,
) -> bool:
    """Whether the conditional trigger lets this hit through."""
    if condition == "always":
        return True
    if condition == "one_in_two":
        return occurrence % max(1, period) == 0
    if condition == "three_in_four":
        span = max(2, period)
        return occurrence % span != span - 1
    if condition == "first_of_phrase":
        return step_in_bar == 0
    if condition == "fill_only":
        return bar_in_section >= bars_in_section - FILL_BARS
    return True


def _pulses(card: PatternCard, density: int) -> int:
    """The pulse count for a section of this density.

    ``density_scale_permille`` is how much of the fall from a density of
    100 the pulse count follows, so 0 keeps the pattern identical in every
    section - which is what every voice but the indie-noise wall wants -
    and 1000 makes the count proportional to the density.

    The wall is where this matters: euclid(16, 16) is already a hit on
    every step in the dense sections, so the only direction its density
    can move is DOWN, and the sparser sections are where it must. That is
    what makes a crest audible as a change of shape rather than of level.
    """
    clamped = max(0, min(100, density))
    fall = (card.euclid_k * (100 - clamped) * card.density_scale_permille) // 100_000
    return max(1, card.euclid_k - fall)


def _audible(ctx: TechniqueContext, frame: int, card: PatternCard) -> bool:
    """Whether the voice's layer has reached the section this FRAME is in.

    The gate belongs to the frame and not to the bar. A bar that straddles
    a section boundary used to carry the density of the section it started
    in into the section it ended in, so the sparse sections received the
    dense ones' material: at forty-five and ninety seconds dub-electronic's
    quietest section took nine and seven hat, snare and bass hits the
    arrangement had not reached, its energy arc inverted, and gate 5 failed;
    indie-noise took four hat hits into its outro, smearing the boundary
    until gate 7 counted one novelty peak too few.
    """
    densities = ctx.section_densities
    if not densities:
        return True
    section = ctx.section_at(frame)
    return densities[min(section, len(densities) - 1)] >= card.min_density


def _hit_frames(
    card: PatternCard,
    rng: SplitMix64,
    ctx: TechniqueContext,
    section_start: int,
    section_end: int,
) -> list[tuple[int, int]]:
    """The hits of one voice: (frame, velocity millibels) in section order."""
    frames_per_bar = ctx.frames_per_bar
    step_frames = max(1, frames_per_bar // card.steps_per_bar)
    first_bar = section_start // frames_per_bar if frames_per_bar else 0
    last_bar = section_end // frames_per_bar if frames_per_bar else 0
    hits: list[tuple[int, int]] = []
    occurrence = 0
    densities = ctx.section_densities
    patterns: dict[int, list[bool]] = {}
    for bar in range(first_bar, last_bar + 1):
        bar_start = bar * frames_per_bar
        section = ctx.section_at(bar_start)
        # The layers come and go with the sections: a voice that the
        # arrangement has not reached yet does not play.
        if densities and densities[min(section, len(densities) - 1)] < card.min_density:
            continue
        pattern = patterns.get(section)
        if pattern is None:
            # The pattern turns by a step per section, so two sections
            # that share a density still do not share a rhythm, and the
            # pulse count follows the density when the card asks for it.
            density = densities[min(section, len(densities) - 1)] if densities else 100
            pattern = rotate(euclid(_pulses(card, density), card.euclid_n), card.rotation + section)
            patterns[section] = pattern
        boundaries = ctx.section_boundaries
        section_first_bar = boundaries[min(section, len(boundaries) - 1)] // frames_per_bar if frames_per_bar else 0
        section_last_bar = boundaries[min(section + 1, len(boundaries) - 1)] // frames_per_bar if frames_per_bar else 0
        bar_in_section = bar - section_first_bar
        bars_in_section = max(1, section_last_bar - section_first_bar)
        for step, active in enumerate(pattern):
            if not active:
                if card.ghost_permille and rng.below(1000) < card.ghost_permille:
                    frame = bar_start + step * step_frames
                    if section_start <= frame < section_end and _audible(ctx, frame, card):
                        hits.append((frame, card.velocity_millibels - 1200))
                continue
            if not _condition_holds(
                card.condition,
                card.condition_period,
                occurrence,
                step,
                bar_in_section,
                bars_in_section,
            ):
                occurrence += 1
                continue
            occurrence += 1
            frame = bar_start + step * step_frames
            if section_start <= frame < section_end and _audible(ctx, frame, card):
                hits.append((frame, card.velocity_millibels))
    return hits


def _pink(card: PinkCard | None) -> PinkCard:
    """The lane's 1/f control signals, or a silent default."""
    if card is not None:
        return card
    return PinkCard(kind="pink", velocity_depth_millibels=0, micro_timing_frames=0, pan_drift_permille=0)


def plan_kick(card: KickCard, rng: SplitMix64, ctx: TechniqueContext, pink: PinkCard | None) -> KickEvent:
    """The kick drum's hits."""
    hits = _hit_frames(card.pattern, rng, ctx, 0, ctx.duration_frames)
    return KickEvent(
        kind="kick",
        instrument="kick",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=ctx.root_midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        hits=[DrumHit(frame=frame, velocity_millibels=velocity) for frame, velocity in hits],
        noise_seed=rng.next_u64(),
        velocity_depth_millibels=_pink(pink).velocity_depth_millibels,
        micro_timing_frames=_pink(pink).micro_timing_frames,
        pan_drift_permille=_pink(pink).pan_drift_permille,
        body_hz=card.body_hz,
        drop_hz=card.drop_hz,
        drop_frames=card.drop_frames,
        decay_frames=card.decay_frames,
    )


def plan_snare(card: SnareCard, rng: SplitMix64, ctx: TechniqueContext, pink: PinkCard | None) -> SnareEvent:
    """The snare drum's hits."""
    hits = _hit_frames(card.pattern, rng, ctx, 0, ctx.duration_frames)
    return SnareEvent(
        kind="snare",
        instrument="snare",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=ctx.root_midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        hits=[DrumHit(frame=frame, velocity_millibels=velocity) for frame, velocity in hits],
        noise_seed=rng.next_u64(),
        velocity_depth_millibels=_pink(pink).velocity_depth_millibels,
        micro_timing_frames=_pink(pink).micro_timing_frames,
        pan_drift_permille=_pink(pink).pan_drift_permille,
        body_hz=card.body_hz,
        body_decay_frames=card.body_decay_frames,
        noise_decay_frames=card.noise_decay_frames,
    )


def plan_hat(card: HatCard, rng: SplitMix64, ctx: TechniqueContext, pink: PinkCard | None) -> HatEvent:
    """The hat's hits."""
    hits = _hit_frames(card.pattern, rng, ctx, 0, ctx.duration_frames)
    return HatEvent(
        kind="hat",
        instrument="hat",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=ctx.root_midi,
        pan_permille=200,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        hits=[DrumHit(frame=frame, velocity_millibels=velocity) for frame, velocity in hits],
        noise_seed=rng.next_u64(),
        velocity_depth_millibels=_pink(pink).velocity_depth_millibels,
        micro_timing_frames=_pink(pink).micro_timing_frames,
        pan_drift_permille=_pink(pink).pan_drift_permille,
        cutoff_hz=card.cutoff_hz,
        decay_frames=card.decay_frames,
        lowpass_hz=card.lowpass_hz,
    )


def plan_bass(card: BassCard, rng: SplitMix64, ctx: TechniqueContext, pink: PinkCard | None) -> BassEvent:
    """The bass line: an eighth-note root with the occasional octave jump.

    The root comes from the section's own harmonic centre, so a modal shift
    is heard in the bass and not only in the notes on top of it. The jumps
    are the only surprise, and they are rare.
    """
    hits = _hit_frames(card.pattern, rng, ctx, 0, ctx.duration_frames)
    bass: list[BassHit] = []
    for index, (frame, velocity) in enumerate(hits):
        root = ctx.section_roots[ctx.section_at(frame)] if ctx.section_roots else ctx.root_midi
        midi = root + card.midi_offset_semitones
        if rng.below(1000) < card.octave_jump_permille:
            midi += 12
        # Phrase-end fifth: BRIEF 5 recipe. Only on the last hit of a
        # phrase (section boundary crossing), and only when enabled.
        is_phrase_end = index == len(hits) - 1 or ctx.section_at(hits[index + 1][0]) != ctx.section_at(frame)
        if is_phrase_end and card.fifth_permille > 0 and rng.below(1000) < card.fifth_permille:
            midi += 7
        bass.append(BassHit(frame=frame, velocity_millibels=velocity, midi=midi))
    return BassEvent(
        kind="bass",
        instrument="bass",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=ctx.root_midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        hits=bass,
        noise_seed=rng.next_u64(),
        velocity_depth_millibels=_pink(pink).velocity_depth_millibels,
        micro_timing_frames=_pink(pink).micro_timing_frames,
        pan_drift_permille=_pink(pink).pan_drift_permille,
        cutoff_hz=card.cutoff_hz,
        decay_frames=card.decay_frames,
    )
