"""compose(): the only place randomness exists.

The RNG is created here, every draw happens here, and it dies when this
function returns. Everything downstream reads the frozen Plan and never rolls.

The arranger lives here too. The arrangement is a walk over the station's
section graph: the walk starts at the intro, follows the declared
successors, and ends at the outro. The sections carry the tension curve
(their level), the density, the harmonic center (the mode and the root)
and the texture, and no two consecutive sections may be the same
arrangement: they have to differ in at least two of the five dimensions
BRIEF 6 names.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from indiegen.compose.context import TechniqueContext
from indiegen.compose.director import ENDING_GUARD_SECONDS
from indiegen.compose.rng import SplitMix64, seed_from_bytes
from indiegen.compose.techniques import plan_drone, plan_plucks, plan_poly_period
from indiegen.compose.techniques.t5_dejavu import plan_deja_vu, replay_permille
from indiegen.compose.techniques.t6_drums import plan_bass, plan_hat, plan_kick, plan_snare
from indiegen.compose.techniques.t14_motif import StringVoice, build_cell, plan_motif
from indiegen.config import (
    BassCard,
    DejaVuCard,
    DirectorCard,
    DroneCard,
    DubChainCard,
    FrippertronicsCard,
    HatCard,
    KickCard,
    LanePreset,
    PadCard,
    PinkCard,
    PluckCard,
    PolyPeriodCard,
    Preset,
    SnareCard,
    StationPreset,
    StrategyCard,
)
from indiegen.errors import PlanError
from indiegen.plan import (
    SAMPLE_RATE,
    BassEvent,
    DelaySend,
    DirectorMove,
    DubChainSpec,
    Event,
    FrippertronicsSpec,
    HatEvent,
    KickEvent,
    MotifAppearance,
    MotifCell,
    MotifNote,
    PadEvent,
    Plan,
    PluckEvent,
    Rational,
    ReverbSpec,
    SectionPlan,
    SectionProfile,
    SnareEvent,
)
from indiegen.theory.scales import RELATIVE_INTERVAL, RELATIVE_MODES, mode_scale

# The three forms of a release: a full track, a longform and an interlude.
Form = Literal["full", "longform", "interlude"]

# The dimensions two consecutive sections have to differ in.
DIMENSIONS: tuple[str, ...] = ("instrumentation", "harmonic_center", "rhythm", "density", "texture")
MINIMUM_DIFFERENCES: int = 2

# The harmonic center moves at least this often and at most this often, in
# bars. BRIEF T16: "every 16-64 bars".
MODE_SHIFT_MIN_BARS: int = 16
MODE_SHIFT_MAX_BARS: int = 64

# The density an arrangement has to reach. A track that never gets here has
# no peak, and the layers that only exist in the dense sections are in
# none of it.
DENSE_SECTION_DENSITY: int = 70

# The strategies that take material away, and the instruments they take.
DROPPING_STRATEGIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("drop_drums", ("kick", "snare", "hat")),
    ("drop_kick", ("kick",)),
    ("drop_bass", ("bass",)),
    ("solo_texture", ("kick", "snare", "hat", "bass")),
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


def _paths_from(
    graph: list[SectionProfile],
    start: str,
    count: int,
    rng: SplitMix64,
) -> list[list[SectionProfile]]:
    """Every walk of the graph that is ``count`` nodes long and ends at the outro.

    The walk never visits a function twice, so an arrangement is a shape and
    not a loop, and the branches are taken in a rotated order, so the draw
    decides which of the legal arrangements this seed gets.

    Every arrangement also reaches a dense section. A walk that never gets
    there is a track with no peak, and the layers that only exist in the
    dense sections - the hats, the noise wall - are in none of it: half the
    dub lane's arrangements had no hats at all, and the lane's recipe says
    they are a layer. The arc is the shape, not a detail of it.
    """
    by_function = {node.function: node for node in graph}
    if start not in by_function:
        raise PlanError(f"the section graph has no {start!r} node", preset="station")
    if "outro" not in by_function:
        raise PlanError("the section graph has no 'outro' node", preset="station")
    results: list[list[SectionProfile]] = []

    def walk(path: list[SectionProfile], used: set[str]) -> None:
        if len(path) == count:
            if path[-1].function == "outro":
                results.append(list(path))
            return
        node = path[-1]
        successors = [by_function[name] for name in node.next if name in by_function]
        if not successors:
            return
        offset = rng.below(len(successors))
        for index in range(len(successors)):
            successor = successors[(index + offset) % len(successors)]
            if successor.function in used:
                continue
            walk(path + [successor], used | {successor.function})

    walk([by_function[start]], {start})
    dense = [path for path in results if max(node.density for node in path) >= DENSE_SECTION_DENSITY]
    # A graph whose paths are too short to reach a dense section keeps its
    # own paths: the ambient lane's two and three section arrangements are
    # legal, and they have no dense section to reach.
    return dense if dense else results


def _walk_graph(graph: list[SectionProfile], count: int, rng: SplitMix64) -> list[SectionProfile]:
    """The nodes of this track's arrangement."""
    paths = _paths_from(graph, "intro", count, rng)
    if not paths:
        raise PlanError(
            f"the section graph has no arrangement of {count} sections",
            preset="station",
        )
    return paths[rng.below(len(paths))]


def _section_lengths(
    nodes: list[SectionProfile],
    total_frames: int,
    frames_per_bar: int,
    pulsed: bool,
) -> list[int]:
    """How long each section lasts, in frames.

    The nodes carry their lengths in bars, and the bars are weights: they
    are scaled to fill the track exactly. In a pulsed lane the lengths are
    snapped to multiples of four bars, because BRIEF 6 asks for lengths in
    4-bar multiples when a pulse exists. The snapping is given up when it
    does not fit: a section that has no frames is not a section.
    """
    weights = [node.bars for node in nodes]
    total_weight = sum(weights) or 1
    shares = [max(1, total_frames * weight // total_weight) for weight in weights]
    if pulsed and frames_per_bar:
        snapped = [max(4, round(share / frames_per_bar / 4) * 4) * frames_per_bar for share in shares]
        if sum(snapped) <= total_frames:
            shares = snapped
        # No section may be longer than the harmonic center can be held:
        # BRIEF T16 moves the center every 16 to 64 bars, and a section
        # longer than that would hold one mode for longer than the brief
        # allows. The surplus is spread over the sections that have room.
        cap = MODE_SHIFT_MAX_BARS * frames_per_bar
        for _ in range(8):
            over = sum(max(0, share - cap) for share in shares)
            if over <= 0:
                break
            room = [index for index, share in enumerate(shares) if share < cap]
            if not room:
                break
            room_total = sum(cap - shares[index] for index in room)
            for index in room:
                shares[index] += over * (cap - shares[index]) // room_total
            shares = [min(share, cap) for share in shares]
    remainder = total_frames - sum(shares)
    shares[-1] += remainder
    if shares[-1] < 1:
        deficit = 1 - shares[-1]
        for index in range(len(shares) - 2, -1, -1):
            take = min(deficit, max(0, shares[index] - 1))
            shares[index] -= take
            deficit -= take
            if deficit <= 0:
                break
        shares[-1] += deficit - 1
    return shares


def _assign_modes(
    mode_pool: list[str],
    nodes: list[SectionProfile],
    lengths: list[int],
    frames_per_bar: int,
    root_midi: int,
    rng: SplitMix64,
) -> list[tuple[str, int]]:
    """The harmonic center of every section: a mode and a root.

    The shift is a section event, so it never lands mid-bar, and the
    harmonic center moves at least every sixteen bars and at most every
    sixty-four: when the next section would carry the mode past that, the
    shift is forced.

    A section that reprises an earlier one is that section under a
    transform: the reprise takes the relative mode of the section it
    reprises, a minor third below, which is a real harmonic change and not
    a label.
    """
    if not mode_pool:
        raise PlanError("the lane declares no mode to draw from", preset="station")
    assigned: list[tuple[str, int]] = []
    mode = mode_pool[0]
    held_bars = 0
    for index, length in enumerate(lengths):
        bars = max(1, length // frames_per_bar) if frames_per_bar else 0
        if assigned:
            forced = held_bars + bars > MODE_SHIFT_MAX_BARS
            if forced or (held_bars >= MODE_SHIFT_MIN_BARS and rng.below(1000) < 400):
                choices = [name for name in mode_pool if name != mode]
                if choices:
                    mode = choices[rng.below(len(choices))]
                    held_bars = 0
        root = root_midi
        node = nodes[index]
        if node.reprise_of:
            original = next(
                (other for other, item in enumerate(nodes) if item.function == node.reprise_of),
                -1,
            )
            if 0 <= original < len(assigned):
                original_mode, original_root = assigned[original]
                mode = RELATIVE_MODES.get(original_mode, original_mode)
                root = original_root + RELATIVE_INTERVAL
                held_bars = 0
        assigned.append((mode, root))
        held_bars += bars
    return assigned


def _section_boundaries(lengths: list[int]) -> list[int]:
    """The frame where each section starts, and the end of the track."""
    boundaries = [0]
    for length in lengths:
        boundaries.append(boundaries[-1] + length)
    return boundaries


def _chord_roots(scale_midi: list[int], intervals: list[int], tones: int) -> list[int]:
    """The scale notes that can carry the chord's first tones.

    A chord tone has to be in the lane's scale, so the root is drawn from
    the notes that support the whole chord rather than from the whole scale.
    """
    wanted = intervals[:tones]
    return [root for root in scale_midi if all(root + interval in scale_midi for interval in wanted)]


def _pad_event(card: PadCard, rng: SplitMix64, ctx: TechniqueContext, start: int, length: int, root: int) -> PadEvent:
    """The sustained pad: the S0 instrument, with the S0 field semantics."""
    count = rng.between(card.partials.min, card.partials.max)
    detunes = [rng.between(card.detune_min_cents, card.detune_max_cents) for _ in range(count - 1)]
    return PadEvent(
        kind="pad",
        instrument="pad",
        start_frame=start,
        duration_frames=length,
        midi=root,
        pan_permille=0,
        amplitude_millibels=card.amplitude_millibels,
        attack_frames=ctx.attack_frames,
        release_frames=ctx.release_frames,
        partials=count,
        partial_detune_cents=detunes,
        lfo_rate=card.lfo_rate,
        lfo_depth_cents=card.lfo_depth_cents,
    )


def _string_voice(cards: Sequence[object]) -> StringVoice | None:
    """The Karplus-Strong's parameters, from whichever card declares them."""
    for card in cards:
        if isinstance(card, PluckCard):
            return StringVoice(
                feedback_numerator=card.feedback_num_min,
                feedback_denominator=card.feedback_den,
                brightness=card.brightness,
                pluck_position_permille=card.pluck_position_permille,
                detune_cents=card.detune_cents,
            )
        if isinstance(card, DejaVuCard):
            return StringVoice(
                feedback_numerator=card.feedback_num,
                feedback_denominator=card.feedback_den,
                brightness=card.brightness,
                pluck_position_permille=card.pluck_position_permille,
                detune_cents=card.detune_cents,
            )
    return None


def _instrumentation(events: list[Event], start: int, stop: int) -> list[str]:
    """The kinds of event that sound in a window of the track.

    A drum pattern spans the whole track, so the drums are in a section
    only if a hit of theirs actually lands in it.
    """
    kinds: set[str] = set()
    for event in events:
        if isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            if any(start <= hit.frame < stop for hit in event.hits):
                kinds.add(event.kind)
            continue
        if event.start_frame < stop and event.start_frame + event.duration_frames > start:
            kinds.add(event.kind)
    return sorted(kinds)


def _rhythm_variants(cards: Sequence[object], count: int) -> list[int | None]:
    """The rhythmic pattern of every section, or None when the lane has none.

    The drums' pattern turns by one step per section, so two sections that
    share a density still do not share a pattern.
    """
    rotation: int | None = None
    for card in cards:
        if isinstance(card, (KickCard, SnareCard, HatCard, BassCard)):
            rotation = card.pattern.rotation
            break
    if rotation is None:
        return [None] * count
    return [(rotation + index) % 1000 for index in range(count)]


def _planned_centroid(timbre: dict[str, int], function: str) -> int:
    """The spectral centroid the lane expects for a section.

    The lane's recipe says what each kind of section sounds like, and the
    numbers were measured on real renders of this lane: BRIEF 5's "starting
    specs, measured, then tuned". A lane with no entry for a function gets
    the average of the ones it has, which is the best guess left.
    """
    if not timbre:
        return 1000
    value = timbre.get(function)
    if value is not None:
        return value
    return max(1, sum(timbre.values()) // len(timbre))


def _card_instrument(card: object) -> str | None:
    """The instrument a card puts in the plan, or None when it is not one."""
    if isinstance(card, PadCard):
        return "pad"
    if isinstance(card, PolyPeriodCard):
        return "poly_period"
    if isinstance(card, DroneCard):
        return "drone"
    if isinstance(card, PluckCard):
        return "ks"
    if isinstance(card, KickCard):
        return "kick"
    if isinstance(card, SnareCard):
        return "snare"
    if isinstance(card, HatCard):
        return "hat"
    if isinstance(card, BassCard):
        return "bass"
    if isinstance(card, DejaVuCard):
        return "pluck"
    return None


def _card_min_density(card: object) -> int:
    """The density at which a card's layer starts to play."""
    if isinstance(card, (KickCard, SnareCard, HatCard, BassCard)):
        return card.pattern.min_density
    if isinstance(card, (PadCard, PolyPeriodCard, DroneCard, PluckCard, DejaVuCard)):
        return card.min_density
    return 0


def _playing_ranges(
    lane: LanePreset,
    nodes: list[SectionProfile],
    boundaries: list[int],
) -> dict[str, list[tuple[int, int]]]:
    """The spans of the track in which each instrument plays.

    The layers follow the sections: a voice the arrangement has not
    reached yet does not play. The Director's moves are drawn inside
    these spans, so that a move that drops the drums is not drawn in a
    section where there are no drums.
    """
    ranges: dict[str, list[tuple[int, int]]] = {}
    for card in lane.techniques:
        name = _card_instrument(card)
        if name is None:
            continue
        spans = [
            (boundaries[index], boundaries[index + 1])
            for index in range(len(nodes))
            if nodes[index].density >= _card_min_density(card)
        ]
        if spans:
            ranges.setdefault(name, []).extend(spans)
    for name in ranges:
        ranges[name] = sorted(ranges[name])
    return ranges


def _draw_moves(
    card: DirectorCard,
    frames: int,
    frames_per_bar: int,
    pulsed: bool,
    instruments: set[str],
    ranges: dict[str, list[tuple[int, int]]],
    rng: SplitMix64,
) -> list[DirectorMove]:
    """The Director's moves, drawn at compose time.

    The draw is the composition's: the Director itself is a pure Plan to
    Plan transform and rolls nothing. In a pulsed lane the Director fires
    every 8 to 24 bars, and in a lane with no pulse every 60 to 180
    seconds.

    A strategy that names instruments the lane does not have is not drawn,
    and a strategy is not drawn in a stretch where its instruments do not
    play: a move that could not change anything would be a move that did
    not fire.
    """
    moves: list[DirectorMove] = []
    choices = [entry for entry in card.strategies if not entry.applies_to or instruments.intersection(entry.applies_to)]
    if not choices:
        return moves
    sample = 0
    previous = ""
    while True:
        if pulsed and frames_per_bar:
            remaining = max(1, (frames - sample) // frames_per_bar - 1)
            step = min(rng.between(card.bars_min, card.bars_max), remaining) * frames_per_bar
        else:
            remaining = max(1, (frames - sample) // SAMPLE_RATE - 1)
            step = min(rng.between(card.seconds_min, card.seconds_max), remaining) * SAMPLE_RATE
        target = sample + step
        if target >= frames:
            break
        if pulsed and frames_per_bar:
            sample = (target // frames_per_bar) * frames_per_bar
        else:
            # A lane with no pulse has no bar grid, and the Director's
            # moves are not section events: it fires every 60 to 180
            # seconds whatever the sections do.
            sample = (target // SAMPLE_RATE) * SAMPLE_RATE
        if sample >= frames or sample >= frames - ENDING_GUARD_SECONDS * SAMPLE_RATE:
            # The ending keeps its material: a move in the last seconds
            # would have nothing left to move.
            break
        available = [entry for entry in choices if entry.strategy != previous]
        playing = {name for name, spans in ranges.items() if any(low <= sample < high for low, high in spans)}
        applicable = [entry for entry in available if not entry.applies_to or playing.intersection(entry.applies_to)]
        if not applicable:
            # Nothing but the plan-level moves is possible here.
            applicable = [entry for entry in available if not entry.applies_to]
        if not applicable:
            applicable = available or choices
        choice: StrategyCard = applicable[rng.below(len(applicable))]
        previous = choice.strategy
        span = choice.span_bars * frames_per_bar if choice.span_bars else choice.crossfade_frames
        if _would_empty(choice.strategy, sample, span, ranges):
            # A drop that takes the whole of a layer is not a drop, it is a
            # hole: the layer plays in one section, the drop covers it, and
            # the voice is gone for the whole track. The move is not drawn.
            continue
        moves.append(
            DirectorMove(
                sample=sample,
                strategy=choice.strategy,
                detail=choice.detail,
                parameter=rng.between(choice.parameter_min, choice.parameter_max),
                crossfade_frames=span,
                applies_to=list(choice.applies_to),
            )
        )
    return moves


def _would_empty(
    strategy: str,
    sample: int,
    span: int,
    ranges: dict[str, list[tuple[int, int]]],
) -> bool:
    """Would this drop take the whole of a layer's material?

    A drop that covers every stretch in which a voice plays silences it
    for the whole track, and a voice that is silent for the whole track is
    not a drop. The dub lane's hats play in one section; a drop of eight
    bars in that section took all of them, and the lane had no hats at all.
    """
    if strategy not in dict(DROPPING_STRATEGIES):
        return False
    end = sample + span
    for name in dict(DROPPING_STRATEGIES)[strategy]:
        spans = ranges.get(name)
        if not spans:
            continue
        if all(sample <= low and high <= end for low, high in spans):
            return True
    return False


def _frippertronics_spec(card: FrippertronicsCard, rng: SplitMix64) -> FrippertronicsSpec:
    """T3's send, resolved to integers."""
    delay_seconds = rng.between(card.delay_seconds.min, card.delay_seconds.max)
    feedback = rng.between(card.feedback_permille.min, card.feedback_permille.max)
    rate = rng.between(card.wow_rate_hz.min, card.wow_rate_hz.max)
    return FrippertronicsSpec(
        delay_frames=delay_seconds * SAMPLE_RATE,
        feedback_permille=feedback,
        cutoff_start_hz=card.cutoff_start_hz,
        cutoff_step_hz=card.cutoff_step_hz,
        cutoff_floor_hz=card.cutoff_floor_hz,
        saturation_permille=card.saturation_permille,
        wow_depth_permille=card.wow_depth_permille,
        wow_rate=Rational(numerator=rate, denominator=10),
        send_millibels=card.send_millibels,
    )


def _dub_chain_spec(card: DubChainCard, rng: SplitMix64) -> DubChainSpec:
    """T10's chain, resolved to integers."""
    return DubChainSpec(
        bit_depth=card.bit_depth,
        bandpass_hz=card.bandpass_hz,
        bandpass_q_num=card.bandpass_q_num,
        bandpass_q_den=card.bandpass_q_den,
        drift_depth_hz=card.drift_depth_hz,
        drift_seed=rng.next_u64(),
        send_millibels=card.send_millibels,
        sidechain_depth_millibels=card.sidechain_depth_millibels,
        sidechain_release_frames=card.sidechain_release_frames,
    )


def _form_for(station: StationPreset, duration_frames: int | None) -> Form:
    """The form of a track, when the caller did not name one.

    A render without a duration is a full track. A render with one is the
    form whose range holds it, and a duration that no form covers (a test's
    sixty seconds, say) is a full track: the form is a statement about the
    release, not about the length alone.
    """
    if duration_frames is None:
        return station.forms[0].form
    seconds = duration_frames // SAMPLE_RATE
    for card in station.forms:
        low, high = card.duration_range_seconds
        if low <= seconds <= high:
            return card.form
    return station.forms[0].form


def compose(preset: Preset, seed: int, duration_frames: int | None = None, form: Form | None = None) -> Plan:
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

    if form is None:
        form = _form_for(station, duration_frames)
    form_card = next(entry for entry in station.forms if entry.form == form)

    if duration_frames is None:
        low, high = form_card.duration_range_seconds
        # A form with a single declared duration does not draw one: the plan
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
    pulsed = lane.pulse == "bars"

    # The arrangement: a walk over the station's section graph.
    nodes = _walk_graph(station.section_graph, section_count, rng)
    lengths = _section_lengths(nodes, frames, frames_per_bar, pulsed)
    boundaries = _section_boundaries(lengths)
    densities = [node.density for node in nodes]

    intervals = next(
        (card.chord_intervals for card in lane.techniques if isinstance(card, PolyPeriodCard)),
        [],
    )
    roots = _chord_roots(lane.scale_midi, intervals, 3) if intervals else list(lane.scale_midi)
    root_midi = rng.choice(roots if roots else lane.scale_midi)

    modes = _assign_modes(lane.mode_pool, nodes, lengths, frames_per_bar, root_midi, rng)
    section_roots = [root for _, root in modes]
    section_scales = [mode_scale(mode, root, 2) for mode, root in modes]

    title_words = rng.choice(station.title_words), rng.choice(station.title_words)
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
        frames_per_bar=frames_per_bar,
        attack_frames=lane.attack_frames or 0,
        release_frames=lane.release_frames or 0,
        section_boundaries=list(boundaries),
        section_densities=densities,
        section_scales=section_scales,
        section_roots=section_roots,
        section_functions=[node.function for node in nodes],
    )

    # T7 resolves once: the lane's 1/f control signals are declared by the
    # pink card and stamped onto the drum events.
    pink = next((card for card in lane.techniques if isinstance(card, PinkCard)), None)

    events: list[Event] = []
    for card in lane.techniques:
        if isinstance(card, PadCard):
            for index in range(len(nodes)):
                if nodes[index].density < card.min_density:
                    continue
                events.append(_pad_event(card, rng, ctx, boundaries[index], lengths[index], section_roots[index]))
        elif isinstance(card, PolyPeriodCard):
            events.extend(plan_poly_period(card, rng, ctx))
        elif isinstance(card, PluckCard):
            events.extend(plan_plucks(card, rng, ctx))
        elif isinstance(card, KickCard):
            events.append(plan_kick(card, rng, ctx, pink))
        elif isinstance(card, SnareCard):
            events.append(plan_snare(card, rng, ctx, pink))
        elif isinstance(card, HatCard):
            events.append(plan_hat(card, rng, ctx, pink))
        elif isinstance(card, BassCard):
            events.append(plan_bass(card, rng, ctx, pink))
        elif isinstance(card, DejaVuCard):
            events.extend(plan_deja_vu(card, rng, ctx))
        elif isinstance(card, (PinkCard, FrippertronicsCard, DubChainCard)):
            continue
        else:
            for index in range(len(nodes)):
                events.append(plan_drone(card, rng, ctx, boundaries[index], lengths[index], section_roots[index]))

    # The motif: the station's signature, played by the Karplus-Strong.
    cell = build_cell(station.motif_bank, station.motif_rhythm, root_midi, frames_per_beat, rng)
    string = _string_voice(lane.techniques)
    appearances: list[MotifAppearance] = []
    motif_events: list[PluckEvent] = []
    if string is not None:
        appearances, motif_events = plan_motif(cell, string, ctx, rng)
        events.extend(motif_events)

    sections: list[SectionPlan] = []
    rhythm_variants = _rhythm_variants(lane.techniques, len(nodes))
    for index, node in enumerate(nodes):
        start = boundaries[index]
        stop = boundaries[index + 1]
        reprise = -1
        if node.reprise_of:
            reprise = next((other for other, item in enumerate(nodes) if item.function == node.reprise_of), -1)
        sections.append(
            SectionPlan(
                index=index,
                function=node.function,
                start_frame=start,
                end_frame=stop,
                bars=max(1, lengths[index] // frames_per_bar) if frames_per_bar else 1,
                density=node.density,
                level_millibels=node.level_millibels,
                techniques=[card.kind for card in lane.techniques],
                instrumentation=_instrumentation(events, start, stop),
                mode=modes[index][0],
                root_midi=section_roots[index],
                texture=node.texture,
                reprise_of=reprise,
                transform=node.transform,
                centroid_hz=_planned_centroid(lane.timbre, node.function),
            )
        )

    _assert_sections_differ(preset, seed, sections, rhythm_variants)

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
    frippertronics = next(
        (_frippertronics_spec(card, rng) for card in lane.techniques if isinstance(card, FrippertronicsCard)),
        None,
    )
    dub_chain = next(
        (_dub_chain_spec(card, rng) for card in lane.techniques if isinstance(card, DubChainCard)),
        None,
    )
    deck = _draw_moves(
        station.director,
        frames,
        frames_per_bar,
        pulsed,
        {event.instrument for event in events},
        _playing_ranges(lane, nodes, boundaries),
        rng,
    )
    deja_vu = next((card for card in lane.techniques if isinstance(card, DejaVuCard)), None)
    replay = [replay_permille(deja_vu, index, len(nodes)) for index in range(len(nodes))] if deja_vu else []

    return Plan(
        version=3,
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
        form=form,
        tempo_bpm=tempo,
        frames_per_beat=frames_per_beat,
        meter_numerator=lane.meter[0],
        meter_denominator=lane.meter[1],
        pulse=lane.pulse,
        scale_midi=list(lane.scale_midi),
        palette=list(station.palette),
        fx_sends=list(lane.fx_sends),
        techniques=[card.kind for card in lane.techniques],
        strategy_deck=deck,
        section_count_range=list(lane.section_count_range),
        section_count=len(nodes),
        sections=sections,
        motif=MotifCell(notes=[MotifNote(midi=midi, duration_frames=duration) for midi, duration in cell]),
        motif_appearances=appearances,
        deja_vu_replay_permille=list(replay),
        title_words=list(station.title_words),
        lane_weights=list(station.lane_weights),
        dither_seed=dither_seed,
        dither_lsb=station.dither_lsb,
        target_lufs_millibels=station.target_lufs_millibels,
        ceiling_millibels=station.ceiling_millibels,
        bus_gains=list(lane.bus_gains),
        fade_in_frames=station.fade_in_frames,
        fade_out_frames=station.fade_out_frames,
        section_crossfade_frames=station.section_crossfade_frames,
        track_number=station.track_number,
        delay_sends=[delay_send],
        reverb=reverb,
        frippertronics=frippertronics,
        dub_chain=dub_chain,
        events=events,
        director_log=[],
    )


def _assert_sections_differ(
    preset: Preset,
    seed: int,
    sections: list[SectionPlan],
    rhythm_variants: list[int | None],
) -> None:
    """No two consecutive sections may be the same arrangement.

    BRIEF 6: "Each section differs from the previous in at least 2 of:
    instrumentation, harmonic center, rhythmic pattern, density,
    texture/space." A section that does not differ is a section that
    repeats, and BRIEF 7 rejects a track that repeats a section verbatim.
    """
    for previous, current in zip(sections, sections[1:], strict=False):
        differences = 0
        if previous.instrumentation != current.instrumentation:
            differences += 1
        if (previous.mode, previous.root_midi) != (current.mode, current.root_midi):
            differences += 1
        if rhythm_variants[previous.index] != rhythm_variants[current.index]:
            differences += 1
        if previous.density != current.density:
            differences += 1
        if previous.texture != current.texture:
            differences += 1
        if differences < MINIMUM_DIFFERENCES:
            raise PlanError(
                f"sections {previous.index} and {current.index} differ in {differences} dimensions, "
                f"and at least {MINIMUM_DIFFERENCES} are needed",
                preset=preset.name,
                seed=seed,
            )
