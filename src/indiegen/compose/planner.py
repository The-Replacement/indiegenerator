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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, cast

from indiegen.compose import tension
from indiegen.compose.context import TechniqueContext
from indiegen.compose.director import ENDING_GUARD_SECONDS
from indiegen.compose.microtiming import apply_micro_timing
from indiegen.compose.rng import SplitMix64, groove_offsets, seed_from_bytes
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
    LeadCard,
    PadCard,
    PinkCard,
    PluckCard,
    PolyPeriodCard,
    Preset,
    SnareCard,
    StationPreset,
    StrategyCard,
    TechniqueCard,
)
from indiegen.errors import PlanError
from indiegen.plan import (
    SAMPLE_RATE,
    DelaySend,
    DirectorMove,
    DubChainSpec,
    Event,
    FrippertronicsSpec,
    HitBase,
    LeadEvent,
    MotifAppearance,
    MotifCell,
    MotifNote,
    PadEnvelopeSegment,
    PadEvent,
    Partial,
    Plan,
    PluckEvent,
    PolyPeriodEvent,
    Rational,
    ReverbSpec,
    RhythmEvent,
    SectionPlan,
    SectionProfile,
)
from indiegen.spectrum import declared_centroid_millihz
from indiegen.theory.scales import mode_scale, relative_of

# The three forms of a release: a full track, a longform and an interlude.
Form = Literal["full", "longform", "interlude"]

# The dimensions two consecutive sections have to differ in.
MINIMUM_DIFFERENCES: int = 2

# The harmonic center moves at least this often and at most this often, in
# bars. BRIEF T16: "every 16-64 bars".
MODE_SHIFT_MIN_BARS: int = 16
MODE_SHIFT_MAX_BARS: int = 64

# The shortest a section may be in a lane with a pulse, in bars. BRIEF 6
# asks for section lengths in 4-bar multiples, and _section_lengths snaps
# them to that - but it GIVES UP the snapping when the sections do not fit,
# which is the wrong thing to give up: a section shorter than this cannot
# carry the material its function declares. A motif that recurs once a
# phrase, or a timbre that has to establish itself, needs the room, and
# what has to give instead is the COUNT of sections.
#
# Measured (c32): at six sections a 4-bar floor needs 66.2 s at
# kosmische's tempo, so a 45 s or a 60 s draw produced two- and three-bar
# sections - and kosmische failed gate 6 at 60 s and gate 7 at 45 s, with
# motorik and indie-noise failing gate 7 at 45 s alongside it. Every
# duration whose smallest section was four bars or more passed.
MINIMUM_SECTION_BARS: int = 4

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
# The same pairs, as the read-only lookup `_would_empty` needs: the tuple is
# the declaration, this is the index into it, built once instead of twice per
# call in the arranger's bar loop.
_LAYERS_BY_DROP: Mapping[str, tuple[str, ...]] = MappingProxyType(dict(DROPPING_STRATEGIES))


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


def _snapped_shares(shares: list[int], frames_per_bar: int) -> list[int]:
    """The shares snapped to four-bar multiples, with the floor applied."""
    floor = MINIMUM_SECTION_BARS * frames_per_bar
    block = 4 * frames_per_bar
    return [max(floor, round(share / frames_per_bar / 4) * block) for share in shares]


def _floored_shares(weights: list[int], total_frames: int, frames_per_bar: int) -> list[int]:
    """Split the frames by weight, pinning every section at the floor.

    The alternative when the four-bar snap does not fit. Sections that the
    proportional split would put below MINIMUM_SECTION_BARS are pinned
    there and the frames that are left are split by weight among the rest;
    the split is proportional rather than snapped, because snapping needs
    more room than a short piece has and the FLOOR is what the material
    actually needs - a section below it cannot carry the motif's recurrence
    or establish the timbre its function declares.

    Returns the plain proportional split only when even the floor does not
    fit, which the caller has already ruled out by drawing a section count
    whose floor fits.
    """
    floor = MINIMUM_SECTION_BARS * frames_per_bar
    count = len(weights)
    total_weight = sum(weights) or 1
    if count * floor > total_frames:
        return [max(1, total_frames * weight // total_weight) for weight in weights]
    shares = [0] * count
    pinned = [False] * count
    remaining = total_frames
    while True:
        free = [index for index in range(count) if not pinned[index]]
        if not free:
            break
        free_weight = sum(weights[index] for index in free) or 1
        for index in free:
            shares[index] = remaining * weights[index] // free_weight
        short = [index for index in free if shares[index] < floor]
        if not short:
            break
        for index in short:
            shares[index] = floor
            pinned[index] = True
            remaining -= floor
    return shares


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
    4-bar multiples when a pulse exists.

    The floor, MINIMUM_SECTION_BARS, is the one thing the snapping may not
    give up. The snap needs room - a section with twice the weight rounds
    up twice as far - and when it does not fit the floor is kept by an
    unsnapped proportional split instead (``_floored_shares``). Only when
    even the floor does not fit is it abandoned, which the caller has
    already made impossible by drawing a section count whose floor fits.
    """
    weights = [node.bars for node in nodes]
    total_weight = sum(weights) or 1
    shares = [max(1, total_frames * weight // total_weight) for weight in weights]
    if pulsed and frames_per_bar:
        snapped = _snapped_shares(shares, frames_per_bar)
        shares = snapped if sum(snapped) <= total_frames else _floored_shares(weights, total_frames, frames_per_bar)
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
                mode, interval = relative_of(original_mode)
                root = original_root + interval
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


def _segment_roots(section_roots: list[int], pool: list[int], segments: int) -> list[list[int]]:
    """Per-section chord-segment roots. ``segments=1`` degenerates to the section root."""
    if segments <= 1:
        return [[root] for root in section_roots]
    if not pool:
        return [[root] for root in section_roots]
    out: list[list[int]] = []
    for root in section_roots:
        base = pool.index(root) if root in pool else 0
        out.append([pool[(base + j) % len(pool)] for j in range(segments)])
    return out


def _planar_offset(events: list[Event], k: int) -> list[Event]:
    """Planar (parallel) motion: every poly-period chord tone moves by k semitones.

    Scale membership is waived for the offset only: the voices keep their
    declared intervals and the whole voicing slides in parallel. At ``k = 0``
    the list is returned untouched, byte for byte.
    """
    if k == 0:
        return events
    out: list[Event] = []
    for event in events:
        if isinstance(event, PolyPeriodEvent):
            voices = [voice.model_copy(update={"midi": voice.midi + k}) for voice in event.voices]
            out.append(event.model_copy(update={"voices": voices, "midi": event.midi + k}))
        else:
            out.append(event)
    return out


def _ornament_events(events: list[Event], boundaries: list[int], seed: int, permille: int, grace: int) -> list[Event]:
    """Plan-time grace/anticipation plucks at phrase boundaries (L08).

    Each host pluck that has room gets a short anticipation pluck ``grace``
    frames before it (clipped to the bar start, never crossing). Emission is
    a pure function of the plan, so re-composition is byte-stable and
    reprises stay deterministic. ``permille == 0`` or ``grace == 0`` is a
    no-op.
    """
    if permille <= 0 or grace <= 0:
        return events
    out = list(events)
    plucks = [e for e in events if isinstance(e, PluckEvent)]
    for host in plucks:
        section_start = 0
        for i in range(len(boundaries) - 1):
            if boundaries[i] <= host.start_frame < boundaries[i + 1]:
                section_start = boundaries[i]
                break
        if host.start_frame - grace < section_start:
            continue  # no room: grace would cross the bar start
        import numpy as np

        roll_rng = np.random.default_rng(seed * 1000003 + host.start_frame)
        if roll_rng.random() * 1000 > permille:
            continue
        out.append(
            PluckEvent(
                kind="pluck",
                instrument="ks",
                start_frame=host.start_frame - grace,
                duration_frames=grace,
                midi=host.midi,
                pan_permille=host.pan_permille,
                amplitude_millibels=host.amplitude_millibels,
                attack_frames=0,
                release_frames=0,
                feedback=host.feedback,
                brightness=host.brightness,
                pluck_position_permille=host.pluck_position_permille,
                detune_cents=host.detune_cents,
                excitation_seed=host.excitation_seed + 100000,
            )
        )
    return out


def _on_odd_beat(frame: int, frames_per_beat: int) -> bool:
    """Whether ``frame`` lands on an odd beat of the bar."""
    return frames_per_beat > 0 and (frame // frames_per_beat) % 2 == 1


def _groove_section_start(boundaries: list[int], frame: int) -> int:
    """The start of the section ``frame`` falls in, or 0."""
    floor = 0
    for boundary in boundaries:
        if boundary <= frame:
            floor = boundary
        else:
            break
    return floor


def _shift_hits(hits: Sequence[HitBase], swing: int, frames_per_beat: int, duration_frames: int) -> list[HitBase]:
    """Swing the hits on odd beats, keeping the list non-decreasing.

    ``render_drum_block`` walks the hits with a cursor and stops at the
    first hit past the block, so the list has to stay sorted: a swung hit
    is clamped to its predecessor plus one.
    """
    shifted: list[HitBase] = []
    previous = -1
    for hit in hits:
        frame = hit.frame
        if _on_odd_beat(frame, frames_per_beat):
            frame += swing
        frame = min(frame, duration_frames - 1)
        if frame <= previous:
            frame = previous + 1
        previous = frame
        shifted.append(hit.model_copy(update={"frame": frame}) if frame != hit.frame else hit)
    return shifted


def _groove_event(
    event: Event,
    swing: int,
    frames_per_beat: int,
    jitter_delta: int,
    boundaries: list[int],
    duration_frames: int,
) -> Event:
    """One event after the swing and the jitter, clamped to its section."""
    new_event: Event = event
    if swing and isinstance(event, (PluckEvent, RhythmEvent)) and _on_odd_beat(event.start_frame, frames_per_beat):
        start = event.start_frame + swing
        if start + event.duration_frames > duration_frames:
            start = duration_frames - event.duration_frames
        if start >= 0:
            new_event = new_event.model_copy(update={"start_frame": start})
    if jitter_delta and isinstance(new_event, PluckEvent):
        floor = _groove_section_start(boundaries, new_event.start_frame)
        start = max(floor, new_event.start_frame + jitter_delta, 0)
        if start + new_event.duration_frames > duration_frames:
            start = duration_frames - new_event.duration_frames
        if start >= 0:
            new_event = new_event.model_copy(update={"start_frame": start})
    if swing and isinstance(new_event, RhythmEvent) and new_event.hits:
        new_event = new_event.model_copy(
            update={"hits": _shift_hits(new_event.hits, swing, frames_per_beat, duration_frames)}
        )
    return new_event


def _apply_groove(
    events: list[Event],
    appearances: list[MotifAppearance],
    boundaries: list[int],
    frames_per_beat: int,
    pulse: str,
    swing_permille: int,
    jitter_frames: int,
    seed: int,
    duration_frames: int,
) -> tuple[list[Event], list[MotifAppearance]]:
    """Swing the offbeats and drift the plucks. Pure and deterministic.

    Swing moves an onset that falls on an odd beat later by
    ``frames_per_beat * swing_permille // 6000`` frames: at 1000 that is a
    sixth of a beat, the triplet feel, and it is a no-op in a lane with no
    pulse. The plucks then drift on a compose-side low-frequency stream in
    ``[-jitter_frames, +jitter_frames]``. The motif's recorded appearances
    move with their plucks, or the Director could not find them again.
    """
    if swing_permille <= 0 and jitter_frames <= 0:
        return events, appearances
    swing = frames_per_beat * swing_permille // 6000 if (pulse == "bars" and frames_per_beat > 0) else 0
    # One jitter offset per (instrument, start, midi) group: the station's
    # detuned chorus pair is one gesture, so both voices drift together.
    groups: dict[tuple[str, int, int], int] = {}
    for event in events:
        if isinstance(event, PluckEvent):
            key = (event.instrument, event.start_frame, event.midi)
            if key not in groups:
                groups[key] = len(groups)
    offsets = groove_offsets(seed, len(groups), jitter_frames)
    out: list[Event] = []
    moved: dict[int, int] = {}
    for event in events:
        delta = (
            offsets[groups[(event.instrument, event.start_frame, event.midi)]] if isinstance(event, PluckEvent) else 0
        )
        new_event = _groove_event(event, swing, frames_per_beat, delta, boundaries, duration_frames)
        if (
            isinstance(new_event, PluckEvent)
            and new_event.instrument == "motif"
            and new_event.start_frame != event.start_frame
        ):
            moved[event.start_frame] = new_event.start_frame
        out.append(new_event)
    if not moved:
        return out, appearances
    new_appearances = [
        appearance.model_copy(update={"start_frame": moved[appearance.start_frame]})
        if appearance.start_frame in moved
        else appearance
        for appearance in appearances
    ]
    return out, new_appearances


def _apply_timbre(events: list[Event], drive_permille: int, snap_permille: int) -> list[Event]:
    """Stamp the lane's drive on the voices and its snap on the drum hits.

    The shaper lives on the voice (a pluck, a pad, a drone, a poly-period
    loop) and the snap on the rhythm events. Both default to zero and a
    zero is a strict no-op, so a lane that declares neither is the lane it
    always was.
    """
    if drive_permille <= 0 and snap_permille <= 0:
        return events
    out: list[Event] = []
    for event in events:
        updates: dict[str, int] = {}
        if drive_permille > 0 and isinstance(event, PluckEvent):
            updates["drive_permille"] = drive_permille
        if snap_permille > 0 and isinstance(event, RhythmEvent):
            updates["snap_permille"] = snap_permille
        out.append(event.model_copy(update=updates) if updates else event)
    return out


def _pad_event(card: PadCard, rng: SplitMix64, ctx: TechniqueContext, start: int, length: int, root: int) -> PadEvent:
    """The sustained pad: the S0 instrument, with the S0 field semantics."""
    count = rng.between(card.partials.min, card.partials.max)
    detunes = [rng.between(card.detune_min_cents, card.detune_max_cents) for _ in range(count - 1)]
    weighted = card.envelope_segments > 0 and count >= 2
    partials = [Partial(ratio=Rational(numerator=1, denominator=1), amplitude_millibels=0, detune_cents=0)]
    for index in range(2, count + 1):
        detune = detunes[index - 2] if index - 2 < len(detunes) else 0
        # Weighted pads roll the upper partials off so a permutation of the
        # weights has something to permute: uniform weights make the
        # segment switch a no-op by construction.
        weight = -min(1200, 600 * (index - 1)) if weighted else 0
        partials.append(
            Partial(
                ratio=Rational(numerator=index, denominator=1),
                amplitude_millibels=weight,
                detune_cents=detune,
            )
        )
    segments: list[PadEnvelopeSegment] = []
    if weighted:
        # Equal segments measured from the previous boundary; each segment
        # rotates the weight assignment by one partial (the Farben rotation).
        share = max(1, length // card.envelope_segments)
        for step in range(card.envelope_segments - 1):
            segments.append(
                PadEnvelopeSegment(
                    delta_frames=share,
                    permutation=[(index + step + 1) % count for index in range(count)],
                )
            )
        # The first declared segment starts from the event's own weights
        # (identity is implicit until the first permutation lands).
        segments = [
            PadEnvelopeSegment(delta_frames=share, permutation=list(range(count))),
            *segments,
        ]
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
        partials=partials,
        lfo_rate=card.lfo_rate,
        lfo_depth_cents=card.lfo_depth_cents,
        envelope_segments=segments,
    )


def _string_voice(cards: Sequence[TechniqueCard]) -> StringVoice | None:
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
        if isinstance(event, RhythmEvent):
            if any(start <= hit.frame < stop for hit in event.hits):
                kinds.add(event.kind)
            continue
        if event.start_frame < stop and event.start_frame + event.duration_frames > start:
            kinds.add(event.kind)
    return sorted(kinds)


def _rhythm_variants(cards: Sequence[TechniqueCard], count: int) -> list[int | None]:
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


def _pattern_min_density(card: TechniqueCard) -> int:
    return card.pattern.min_density  # type: ignore[union-attr]


def _card_min_density(card: TechniqueCard) -> int:
    """The density at which a card's layer starts to play."""
    spec = CARD_SPECS.get(card.kind)
    if spec is None:
        return 0
    return spec.min_density(card)


def _card_instrument(card: TechniqueCard) -> str | None:
    """The instrument a card puts in the plan, or None when it is not one."""
    spec = CARD_SPECS.get(card.kind)
    return spec.instrument if spec is not None else None


def _playing_ranges(
    lane: LanePreset,
    nodes: list[SectionProfile],
    boundaries: list[int],
    ctx: TechniqueContext | None = None,
) -> dict[str, list[tuple[int, int]]]:
    """The spans of the track in which each instrument plays.

    The layers follow the sections: a voice the arrangement has not
    reached yet does not play. The Director's moves are drawn inside
    these spans, so that a move that drops the drums is not drawn in a
    section where there are no drums.
    """
    # The Director draws against the node's declared density when admission is
    # off, and against the admitted layer sets when it is on: the deck is an
    # arrangement decision over the material that actually sounds.
    ranges: dict[str, list[tuple[int, int]]] = {}
    for card in lane.techniques:
        name = _card_instrument(card)
        if name is None:
            continue
        minimum = _card_min_density(card)
        if ctx is not None:
            spans = [
                (boundaries[index], boundaries[index + 1])
                for index in range(len(nodes))
                if ctx.admits(index, name, nodes[index].density, minimum)
            ]
        else:
            spans = [
                (boundaries[index], boundaries[index + 1])
                for index in range(len(nodes))
                if nodes[index].density >= minimum
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
    layers = _LAYERS_BY_DROP.get(strategy)
    if layers is None:
        return False
    end = sample + span
    for name in layers:
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


def _admission_mode(tension: int) -> str:
    """The layer mode a planned tension level selects.

    Tension tracks arrangement fullness (#38): sparse sections have low
    tension, so ``all`` fires at T <= 421 to fill them. Full sections defer
    to the density gate.
    """
    if tension <= 421:
        return "all"
    return "density"


@dataclass(frozen=True)
class _PlanInputs:
    """The values compose() has computed, handed to the assembler."""

    preset_name: str
    seed: int
    station: StationPreset
    lane: LanePreset
    form: Form
    frames: int
    tempo: int
    frames_per_beat: int
    title_words: tuple[str, str]
    dither_seed: int
    cell: list[tuple[int, int]]
    appearances: list[MotifAppearance]
    sections: list[SectionPlan]
    nodes: list[SectionProfile]
    delay_send: DelaySend
    reverb: ReverbSpec | None
    frippertronics: FrippertronicsSpec | None
    dub_chain: DubChainSpec | None
    deck: list[DirectorMove]
    replay: list[int]
    events: list[Event]


def _assemble_plan(inputs: _PlanInputs) -> Plan:
    """Build the Plan from already-computed values. No RNG here."""
    station = inputs.station
    lane = inputs.lane
    return Plan(
        version=3,
        format_version=station.format_version,
        preset=inputs.preset_name,
        seed=inputs.seed,
        lane=lane.lane,
        alias=lane.alias,
        album=lane.album,
        file_token=lane.file_token,
        title=f"{inputs.title_words[0]} {inputs.title_words[1]}",
        sample_rate=SAMPLE_RATE,
        channels=2,
        duration_frames=inputs.frames,
        duration_range_frames=[
            lane.duration_range_seconds[0] * SAMPLE_RATE,
            lane.duration_range_seconds[1] * SAMPLE_RATE,
        ],
        form=inputs.form,
        tempo_bpm=inputs.tempo,
        frames_per_beat=inputs.frames_per_beat,
        meter_numerator=lane.meter[0],
        meter_denominator=lane.meter[1],
        pulse=lane.pulse,
        scale_midi=list(lane.scale_midi),
        tuning_system=station.tuning_system,
        chord_segments_per_section=station.chord_segments_per_section,
        chromatic_budget_permille=station.chromatic_budget_permille,
        chord_tone_intervals=list(station.chord_tone_intervals),
        harmony_cp_enabled=1 if station.harmony_cp_enabled else 0,
        harmony_voice_leading_limit=station.harmony_voice_leading_limit,
        planar_offset_semitones=station.planar_offset_semitones,
        ornament_permille=station.ornament_permille,
        grace_offset_frames=station.grace_offset_frames,
        double_copies=station.double_copies,
        double_offset_frames=station.double_offset_frames,
        swing_permille=lane.swing_permille,
        melodic_jitter_frames=lane.melodic_jitter_frames,
        fx_sends=list(lane.fx_sends),
        techniques=[card.kind for card in lane.techniques],
        strategy_deck=inputs.deck,
        section_count_range=list(lane.section_count_range),
        section_count=len(inputs.nodes),
        sections=inputs.sections,
        motif=MotifCell(notes=[MotifNote(midi=midi, duration_frames=duration) for midi, duration in inputs.cell]),
        motif_appearances=inputs.appearances,
        deja_vu_replay_permille=list(inputs.replay),
        title_words=list(station.title_words),
        lane_weights=list(station.lane_weights),
        dither_seed=inputs.dither_seed,
        dither_lsb=station.dither_lsb,
        target_lufs_millibels=station.target_lufs_millibels,
        ceiling_millibels=station.ceiling_millibels,
        bus_gains=list(lane.bus_gains),
        duck=lane.duck,
        fade_in_frames=station.fade_in_frames,
        fade_out_frames=station.fade_out_frames,
        section_crossfade_frames=station.section_crossfade_frames,
        track_number=station.track_number,
        delay_sends=[inputs.delay_send],
        reverb=inputs.reverb,
        frippertronics=inputs.frippertronics,
        dub_chain=inputs.dub_chain,
        events=inputs.events,
        director_log=[],
    )


def _build_fx_deck_and_replay(
    station: StationPreset,
    lane: LanePreset,
    frames: int,
    frames_per_beat: int,
    frames_per_bar: int,
    pulsed: bool,
    events: list[Event],
    nodes: list[SectionProfile],
    boundaries: list[int],
    rng: SplitMix64,
    ctx: TechniqueContext | None = None,
) -> tuple[DelaySend, ReverbSpec | None, FrippertronicsSpec | None, DubChainSpec | None, list[DirectorMove], list[int]]:
    """Build the delay send, reverb, Frippertronics, dub chain, Director deck and deja-vu replay.

    The RNG draws here (Frippertronics, dub chain, Director) happen in this
    order, exactly as they did inline, so the draw sequence is unchanged.
    """
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
        _playing_ranges(lane, nodes, boundaries, ctx),
        rng,
    )
    deja_vu = next((card for card in lane.techniques if isinstance(card, DejaVuCard)), None)
    replay = [replay_permille(deja_vu, index, len(nodes)) for index in range(len(nodes))] if deja_vu else []
    return delay_send, reverb, frippertronics, dub_chain, deck, replay


def _motif_and_postproc(
    events: list[Event],
    station: StationPreset,
    lane: LanePreset,
    root_midi: int,
    frames_per_beat: int,
    rng: SplitMix64,
    ctx: TechniqueContext,
    boundaries: list[int],
    seed: int,
    frames: int,
    section_roots: list[int],
    harmonic_modes: list[tuple[str, int]],
    section_scales: list[list[int]],
) -> tuple[list[Event], list[tuple[int, int]], list[MotifAppearance]]:
    """Motif, planar and production steps between the lane events and the walk.

    The motif is the station signature; the rest is planar motion, groove,
    timbre, ornament, doubling and voice leading, in the order compose()
    always applied them. Only the motif consumes the compose RNG.
    """
    cell = build_cell(station.motif_bank, station.motif_rhythm, root_midi, frames_per_beat, rng)
    string = _string_voice(lane.techniques)
    appearances: list[MotifAppearance] = []
    out = list(events)
    if string is not None:
        appearances, motif_events = plan_motif(cell, string, ctx, rng)
        out.extend(motif_events)
    out = _planar_offset(out, station.planar_offset_semitones)
    out, appearances = _apply_groove(
        out,
        appearances,
        boundaries,
        frames_per_beat,
        lane.pulse,
        lane.swing_permille,
        lane.melodic_jitter_frames,
        seed,
        frames,
    )
    out = _apply_timbre(out, lane.drive_permille, lane.snap_permille)
    out = _ornament_events(out, boundaries, seed, station.ornament_permille, station.grace_offset_frames)
    out = _double_events(out, station.double_copies, station.double_offset_frames, frames)
    out, appearances = _apply_voice_leading(
        out,
        appearances,
        boundaries,
        section_roots,
        [mode for mode, _ in harmonic_modes],
        section_scales,
        lane,
    )
    return out, list(cell), appearances


def _ambient_interlude_section_count(lane: LanePreset, frames: int, section_count: int) -> int:
    """Two longer sections for ambient interludes lift the centroid noise floor (issue #7)."""
    if lane.lane == "ambient" and 45 * SAMPLE_RATE <= frames < 90 * SAMPLE_RATE:
        return 2
    return section_count


def compose(preset: Preset, seed: int, duration_frames: int | None = None, form: Form | None = None) -> Plan:  # noqa: C901
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
    if pulsed and frames_per_bar:
        # Honour MINIMUM_SECTION_BARS by drawing FEWER sections, not by
        # shortening them. _section_lengths otherwise gives up its own
        # 4-bar floor when the draw does not fit, and a section below that
        # floor cannot carry the material its function declares.
        #
        # Never below the lane's own minimum: a track too short for even
        # that many 4-bar sections (a test's five seconds) keeps the count
        # it declared, and _section_lengths falls back to the unsnapped
        # proportional split for it.
        room = max(
            lane.section_count_range[0],
            frames // (MINIMUM_SECTION_BARS * frames_per_bar),
        )
        section_count = min(section_count, room)

    section_count = _ambient_interlude_section_count(lane, frames, section_count)

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
    section_segment_roots = _segment_roots(section_roots, roots, station.chord_segments_per_section)

    # c12: opt-in CP harmonic progression. When enabled, replace the
    # RNG-chosen section roots with a deterministically selected feasible
    # solution of the CP solver (voice-leading parsimony + boundary
    # resolution). Default off => byte-identical to the legacy path.
    if station.harmony_cp_enabled:
        from indiegen.theory.harmony_cp import select_solution, solve_progressions

        domain = roots if roots else list(lane.scale_midi)
        tonic = root_midi if root_midi in domain else (domain[0] if domain else None)
        sols = solve_progressions(
            domain,
            len(nodes),
            voice_leading_limit=station.harmony_voice_leading_limit,
            fixed_first=tonic,
        )
        cp_solution = select_solution(sols, seed)
        if cp_solution is not None and len(cp_solution) == len(nodes):
            section_roots = list(cp_solution)
            section_scales = [mode_scale(mode, root, 2) for (mode, _), root in zip(modes, section_roots, strict=True)]
            section_segment_roots = _segment_roots(section_roots, roots, station.chord_segments_per_section)

    title_words = rng.choice(station.title_words), rng.choice(station.title_words)
    dither_seed = rng.next_u64()

    # T7 resolves once: the lane's 1/f control signals are declared by the
    # pink card and stamped onto the drum events.
    pink = next((card for card in lane.techniques if isinstance(card, PinkCard)), None)

    # The lane's bed: pad and drone only, via CARD_SPECS.bed. A lane with no
    # bed card (dub, indie) carries an empty bed and falls back to density.
    bed_instruments = sorted(
        {
            spec.instrument
            for card in lane.techniques
            if (spec := CARD_SPECS.get(card.kind)) is not None and spec.bed and spec.instrument is not None
        }
    )

    def _make_ctx(admission_modes: list[str], enabled: bool) -> TechniqueContext:
        return TechniqueContext(
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
            tuning_system=station.tuning_system,
            chord_segments_per_section=station.chord_segments_per_section,
            chromatic_budget_permille=station.chromatic_budget_permille,
            chord_tone_intervals=list(station.chord_tone_intervals),
            tension_admission_enabled=enabled,
            section_admission_modes=list(admission_modes),
            bed_instruments=list(bed_instruments),
            section_ic_bands=[[node.entropy_ic_min_permille, node.entropy_ic_max_permille] for node in nodes],
            harmony_cp_enabled=station.harmony_cp_enabled,
            harmony_voice_leading_limit=station.harmony_voice_leading_limit,
        )

    if not lane.tension_admission_enabled:
        ctx = _make_ctx([], False)
        events = _events_for_lane(
            lane, nodes, boundaries, lengths, section_roots, section_segment_roots, rng, ctx, pink
        )
        tension_values_pass1: list[int] | None = None
        tension_steps_pass1: list[int] | None = None
        tension_levels_pass1: list[int] | None = None
        deck_snap: int | None = None
    else:
        ctx_density = _make_ctx(["density"] * len(nodes), True)
        snap = rng.snapshot()
        events_pass1 = _events_for_lane(
            lane, nodes, boundaries, lengths, section_roots, section_segment_roots, rng, ctx_density, pink
        )
        # The first-pass walk must see the same material the committed walk
        # sees: lane events plus the motif and post-production. Sparse
        # sections carry no pitched lane material at all, so their pitch and
        # roughness are the motif's; walking the raw lane events alone moved
        # dub45's outro by 40 permille and flipped it to all.
        events_pass1, _, _ = _motif_and_postproc(
            events_pass1,
            station,
            lane,
            root_midi,
            frames_per_beat,
            rng,
            ctx_density,
            boundaries,
            seed,
            frames,
            section_roots,
            modes,
            section_scales,
        )
        # The fx and deck draws must not drift with the admitted events: the
        # first pass replicates the committed draw order, so its post-motif
        # state is the state the deck would have drawn from without
        # admission. Restoring it before the fx/deck build keeps the
        # admitted plan's deck to admitted-range filtering alone.
        deck_snap = rng.snapshot()
        tension_values_pass1, tension_steps_pass1, tension_levels_pass1 = _tension_walk(
            preset, seed, nodes, boundaries, lengths, frames_per_bar, events_pass1
        )
        admission_modes = [_admission_mode(value) for value in tension_values_pass1]
        rng.restore(snap)
        ctx = _make_ctx(admission_modes, True)
        events = _events_for_lane(
            lane, nodes, boundaries, lengths, section_roots, section_segment_roots, rng, ctx, pink
        )

    events, cell, appearances = _motif_and_postproc(
        events,
        station,
        lane,
        root_midi,
        frames_per_beat,
        rng,
        ctx,
        boundaries,
        seed,
        frames,
        section_roots,
        modes,
        section_scales,
    )

    if not lane.tension_admission_enabled:
        tension_values, tension_steps, tension_levels = _tension_walk(
            preset, seed, nodes, boundaries, lengths, frames_per_bar, events
        )
        sections = _section_plans(
            nodes,
            boundaries,
            lengths,
            frames_per_bar,
            modes,
            section_roots,
            lane,
            events,
            tension_values,
            tension_steps,
            tension_levels,
        )
    else:
        if tension_values_pass1 is None or tension_steps_pass1 is None or tension_levels_pass1 is None:
            raise PlanError("tension admission pass missing", preset=preset.name, seed=seed)
        placeholder = _section_plans(
            nodes,
            boundaries,
            lengths,
            frames_per_bar,
            modes,
            section_roots,
            lane,
            events,
            tension_values_pass1,
            tension_steps_pass1,
            tension_levels_pass1,
        )
        rederived = tension.rederive_section_tension(events, placeholder)
        sections = [
            section.model_copy(
                update={
                    "tension_permille": rederived[index][0],
                    "tension_delta_permille": rederived[index][1],
                }
            )
            for index, section in enumerate(placeholder)
        ]
    rhythm_variants = _rhythm_variants(lane.techniques, len(nodes))

    _assert_sections_differ(preset, seed, sections, rhythm_variants)

    if deck_snap is not None:
        rng.restore(deck_snap)
    delay_send, reverb, frippertronics, dub_chain, deck, replay = _build_fx_deck_and_replay(
        station, lane, frames, frames_per_beat, frames_per_bar, pulsed, events, nodes, boundaries, rng, ctx
    )

    # The performance jitter is the last thing compose() does, and every
    # reader of a hit's position - the renderer's bus keyframes, the
    # Director's windows, the section-density test - asks grid_frame(). c33.
    events = apply_micro_timing(events, frames, SAMPLE_RATE)

    inputs = _PlanInputs(
        preset_name=preset.name,
        seed=seed,
        station=station,
        lane=lane,
        form=form,
        frames=frames,
        tempo=tempo,
        frames_per_beat=frames_per_beat,
        title_words=title_words,
        dither_seed=dither_seed,
        cell=cell,
        appearances=appearances,
        sections=sections,
        nodes=nodes,
        delay_send=delay_send,
        reverb=reverb,
        frippertronics=frippertronics,
        dub_chain=dub_chain,
        deck=deck,
        replay=replay,
        events=events,
    )
    return _assemble_plan(inputs)


@dataclass(frozen=True)
class _LaneFrames:
    """Where each section starts, how long it is, and the lane's pink card."""

    nodes: list[SectionProfile]
    boundaries: list[int]
    lengths: list[int]
    section_roots: list[int]
    section_segment_roots: list[list[int]]
    pink: PinkCard | None


CardEvents = Callable[[TechniqueCard, SplitMix64, TechniqueContext, _LaneFrames], Sequence[Event]]


@dataclass(frozen=True)
class CardSpec:
    """The single registration of one technique card kind.

    Everything the composer needs to know about a card kind lives here, so
    adding a technique means adding one entry to ``CARD_SPECS`` and nothing
    else: no new branch in ``_card_instrument``, no new branch in
    ``_card_min_density``, no new row in a dispatch table.
    """

    events: CardEvents
    instrument: str | None
    min_density: Callable[[TechniqueCard], int]
    bed: bool = False


def _pad_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    """One pad per chord segment the card declares itself dense enough for."""
    pad = cast(PadCard, card)
    out: list[Event] = []
    for index in range(len(frames.nodes)):
        if not ctx.admits(index, "pad", frames.nodes[index].density, pad.min_density):
            continue
        boundary = frames.boundaries[index]
        length = frames.lengths[index]
        seg_roots = frames.section_segment_roots[index]
        count = len(seg_roots)
        seg_len = length // count
        for seg, root in enumerate(seg_roots):
            start = boundary + seg * seg_len
            dur = seg_len if seg < count - 1 else (length - seg * seg_len)
            out.append(_pad_event(pad, rng, ctx, start, dur, root))
    return out


LEAD_RATIOS: tuple[tuple[int, int], ...] = ((1, 1), (1, 1), (3, 2), (9, 8), (2, 1))
"""The lead's palette: the detuned pair, then a fifth, an add9 and an octave."""


def _lead_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    """The lead, from its entry section on, where the section is dense enough.

    BRIEF 5 says the lead enters at section 3+. It enters as ONE voice over the
    whole section rather than per chord segment: the segments are a bar-level
    harmonic rhythm, and a lead that restarted on every segment would be a
    sequence, not a line.
    """
    lead = cast(LeadCard, card)
    out: list[Event] = []
    for index in range(len(frames.nodes)):
        if index < lead.entry_section:
            continue
        if not ctx.admits(index, "lead", frames.nodes[index].density, lead.min_density):
            continue
        length = frames.lengths[index]
        count = min(rng.between(lead.partials.min, lead.partials.max), len(LEAD_RATIOS))
        detunes = [rng.between(lead.detune_min_cents, lead.detune_max_cents) for _ in range(count)]
        partials: list[Partial] = []
        for position in range(count):
            numerator, denominator = LEAD_RATIOS[position]
            # The first two partials are the detuned pair BRIEF names; the
            # colour tones sit under them, so the fifth and the add9 are spice
            # and not a chord.
            weight = 0 if position < 2 else -min(1200, 900 * (position - 1))
            partials.append(
                Partial(
                    ratio=Rational(numerator=numerator, denominator=denominator),
                    amplitude_millibels=weight,
                    detune_cents=detunes[position] if position < 2 else 0,
                )
            )
        # A short section cannot carry a slow attack: both fades are bounded by
        # the section, or the envelope would still be opening when it ends.
        attack = min(lead.attack_seconds * ctx.sample_rate, length // 4)
        release = min(lead.release_seconds * ctx.sample_rate, length // 4)
        out.append(
            LeadEvent(
                kind="lead",
                instrument="lead",
                start_frame=frames.boundaries[index],
                duration_frames=length,
                midi=frames.section_roots[index] + 12,
                pan_permille=lead.pan_permille,
                amplitude_millibels=lead.amplitude_millibels,
                attack_frames=attack,
                release_frames=release,
                partials=partials,
                lfo_rate=lead.lfo_rate,
                lfo_depth_cents=lead.lfo_depth_cents,
            )
        )
    return out


def _drone_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    """One drone per chord segment, from the same card."""
    drone = cast(DroneCard, card)
    out: list[Event] = []
    for index in range(len(frames.nodes)):
        if not ctx.admits(index, "drone", frames.nodes[index].density, drone.min_density):
            continue
        boundary = frames.boundaries[index]
        length = frames.lengths[index]
        seg_roots = frames.section_segment_roots[index]
        count = len(seg_roots)
        seg_len = length // count
        for seg, root in enumerate(seg_roots):
            start = boundary + seg * seg_len
            dur = seg_len if seg < count - 1 else (length - seg * seg_len)
            out.append(plan_drone(drone, rng, ctx, start, dur, root, ctx.tuning_system))
    return out


def _poly_period_events(
    card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames
) -> Sequence[Event]:
    poly = cast(PolyPeriodCard, card)
    if frames.nodes:
        admitted = any(
            ctx.admits(index, "poly_period", frames.nodes[index].density, poly.min_density)
            for index in range(len(frames.nodes))
        )
        if not admitted:
            return []
    return plan_poly_period(poly, rng, ctx)


def _pluck_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    return plan_plucks(cast(PluckCard, card), rng, ctx)


def _deja_vu_events(
    card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames
) -> Sequence[Event]:
    return plan_deja_vu(cast(DejaVuCard, card), rng, ctx)


def _kick_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    return [plan_kick(cast(KickCard, card), rng, ctx, frames.pink)]


def _snare_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    return [plan_snare(cast(SnareCard, card), rng, ctx, frames.pink)]


def _hat_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    return [plan_hat(cast(HatCard, card), rng, ctx, frames.pink)]


def _bass_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    return [plan_bass(cast(BassCard, card), rng, ctx, frames.pink)]


def _no_events(card: TechniqueCard, rng: SplitMix64, ctx: TechniqueContext, frames: _LaneFrames) -> Sequence[Event]:
    """A card that is a send or a stream, not an instrument: it schedules nothing."""
    return []


# One row per card kind: the tag the discriminated union already carries, and
# the builder that turns that card into events. A kind that is missing from
# this table is a preset bug the composer reports; a kind that is present but
# does not play is ``_no_events``, said out loud. The old ``else`` branch sent
# every unrecognised card to the drone builder.
def _min_density_card(card: TechniqueCard) -> int:
    return card.min_density  # type: ignore[union-attr]


CARD_SPECS: Mapping[str, CardSpec] = MappingProxyType(
    {
        "pad": CardSpec(_pad_events, "pad", _min_density_card, True),
        "lead": CardSpec(_lead_events, "lead", _min_density_card),
        "poly_period": CardSpec(_poly_period_events, "poly_period", _min_density_card),
        "pluck": CardSpec(_pluck_events, "ks", _min_density_card),
        "kick": CardSpec(_kick_events, "kick", _pattern_min_density),
        "snare": CardSpec(_snare_events, "snare", _pattern_min_density),
        "hat": CardSpec(_hat_events, "hat", _pattern_min_density),
        "bass": CardSpec(_bass_events, "bass", _pattern_min_density),
        "deja_vu": CardSpec(_deja_vu_events, "pluck", _min_density_card),
        "drone": CardSpec(_drone_events, "drone", _min_density_card, True),
        "pink": CardSpec(_no_events, None, lambda _: 0),
        "frippertronics": CardSpec(_no_events, None, lambda _: 0),
        "dub_chain": CardSpec(_no_events, None, lambda _: 0),
    }
)


def _events_for_lane(
    lane: LanePreset,
    nodes: list[SectionProfile],
    boundaries: list[int],
    lengths: list[int],
    section_roots: list[int],
    section_segment_roots: list[list[int]],
    rng: SplitMix64,
    ctx: TechniqueContext,
    pink: PinkCard | None,
) -> list[Event]:
    """Every event the lane's cards declare, in the order the lane declares them."""
    frames = _LaneFrames(
        nodes=nodes,
        boundaries=boundaries,
        lengths=lengths,
        section_roots=section_roots,
        section_segment_roots=section_segment_roots,
        pink=pink,
    )
    events: list[Event] = []
    for card in lane.techniques:
        spec = CARD_SPECS.get(card.kind)
        if spec is None:
            raise PlanError(f"unknown technique card {card.kind!r}", preset=lane.lane, seed=ctx.seed)
        events.extend(spec.events(card, rng, ctx, frames))
    return events


def _tension_walk(
    preset: Preset,
    seed: int,
    nodes: list[SectionProfile],
    boundaries: list[int],
    lengths: list[int],
    frames_per_bar: int,
    events: list[Event],
) -> tuple[list[int], list[int], list[int]]:
    """The tension the planned material spends, and the levels it buys.

    The features are read from the events the composer actually planned, so
    a corridor is a statement about the audio and not about the node. The
    walk solves each section's level inside the trim budget; a corridor it
    cannot reach spends nothing, the declared level stands, and the miss
    is recorded in the step it actually spent.
    """
    pitched = tension.pitched_notes(events)
    materials = [
        tension.section_features(
            events,
            boundaries[index],
            boundaries[index + 1],
            max(1, lengths[index] // frames_per_bar) if frames_per_bar else 1,
            nodes[index].level_millibels,
            pitched,
        )
        for index in range(len(nodes))
    ]
    corridors = [(node.tension_delta_min_permille, node.tension_delta_max_permille) for node in nodes]
    values, steps, levels = tension.walk(materials, [node.level_millibels for node in nodes], corridors)
    # c39 deliberately does NOT raise when a corridor is missed: the corridor
    # is the plan's intent and #10 is the gate that judges it. A budget that
    # can refuse a legal seed would make the generator fragile, and the plan
    # already carries the corridor beside the step it actually spent.
    return values, steps, levels


def _section_plans(
    nodes: list[SectionProfile],
    boundaries: list[int],
    lengths: list[int],
    frames_per_bar: int,
    modes: list[tuple[str, int]],
    section_roots: list[int],
    lane: LanePreset,
    events: list[Event],
    tension_values: list[int],
    tension_steps: list[int],
    tension_levels: list[int],
) -> list[SectionPlan]:
    """The sections the plan records: what each one carries and what sounds in it."""
    sections: list[SectionPlan] = []
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
                level_millibels=tension_levels[index],
                techniques=[card.kind for card in lane.techniques],
                instrumentation=_instrumentation(events, start, stop),
                mode=modes[index][0],
                root_midi=section_roots[index],
                texture=node.texture,
                reprise_of=reprise,
                centroid_hz=_planned_centroid(lane.timbre, node.function),
                declared_centroid_millihz=declared_centroid_millihz(events, start, stop),
                tension_permille=tension_values[index],
                tension_delta_permille=tension_steps[index],
                tension_delta_min_permille=node.tension_delta_min_permille,
                tension_delta_max_permille=node.tension_delta_max_permille,
                entropy_ic_min_permille=node.entropy_ic_min_permille,
                entropy_ic_max_permille=node.entropy_ic_max_permille,
                valence_permille=node.valence_permille,
                arousal_permille=node.arousal_permille,
            )
        )
    return sections


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


def _double_events(events: list[Event], copies: int, offset: int, total_frames: int) -> list[Event]:
    """Micro-offset doubling (L16): clone each event ``copies`` times shifted by multiples of ``offset``.

    Offsets are plan integers, so the comb-filter null is bit-exact. At
    ``copies == 0`` the list is returned untouched. Clones that would start
    past the track end are dropped; drum hits are shifted by the same delta.
    """
    if copies <= 0 or offset <= 0:
        return events
    out = list(events)
    for copy_idx in range(1, copies + 1):
        delta = copy_idx * offset
        for event in events:
            new_start = event.start_frame + delta
            if new_start >= total_frames:
                continue
            cloned = event.model_copy(update={"start_frame": new_start})
            if isinstance(event, RhythmEvent) and event.hits:
                cloned = cloned.model_copy(
                    update={"hits": [h.model_copy(update={"frame": h.frame + delta}) for h in event.hits]}
                )
            remaining = total_frames - new_start
            if cloned.duration_frames > remaining:
                cloned = cloned.model_copy(update={"duration_frames": remaining})
            out.append(cloned)
    return out


def _section_at_frame(boundaries: list[int], frame: int) -> int:
    for index in range(len(boundaries) - 1):
        if boundaries[index] <= frame < boundaries[index + 1]:
            return index
    if boundaries:
        return len(boundaries) - 2
    return 0


def _smoothed_pluck(scale: list[int], previous: int, current: int) -> int | None:
    """The scale note that makes a leap between two plucks less of a leap.

    The score keeps the note close to both ends, weighting the note it came
    from heavily and the note it is going to loosely, and the candidate has to
    be a real improvement - two semitones better, in the same register - or
    the leap stays as written.
    """
    interval = abs(current - previous)
    candidates = []
    for note in scale:
        if note < 36 or note > 96:
            continue
        dist_from_previous = abs(note - previous)
        if dist_from_previous < interval - 2:  # must be meaningfully better
            candidates.append((dist_from_previous + abs(note - current) * 0.3, note))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _pluck_indices_by_instrument(out: list[Event]) -> dict[str, list[int]]:
    """Pluck event indices grouped by instrument, in plan order."""
    from indiegen.plan import PluckEvent

    by_inst: dict[str, list[int]] = {}
    for idx, event in enumerate(out):
        if isinstance(event, PluckEvent):
            by_inst.setdefault(event.instrument, []).append(idx)
    return by_inst


def _lead_one_instrument(
    out: list[Event],
    boundaries: list[int],
    section_scales: list[list[int]],
    instrument: str,
    indices: list[int],
) -> dict[tuple[int, int], int]:
    """Smooth leaps for one instrument; return motif moves to track for appearances."""
    from indiegen.plan import PluckEvent

    moved_motif: dict[tuple[int, int], int] = {}
    if instrument == "bass":
        return moved_motif
    ordered = sorted(indices, key=lambda i: out[i].start_frame)
    for position in range(1, len(ordered)):
        previous = out[ordered[position - 1]]
        current = out[ordered[position]]
        if not isinstance(previous, PluckEvent) or not isinstance(current, PluckEvent):
            continue
        if abs(current.midi - previous.midi) <= 6:  # already smooth enough
            continue
        section = _section_at_frame(boundaries, current.start_frame)
        scale = section_scales[section] if section < len(section_scales) else []
        if not scale:
            continue
        new_midi = _smoothed_pluck(scale, previous.midi, current.midi)
        if new_midi is None:
            continue
        out[ordered[position]] = current.model_copy(update={"midi": new_midi})
        if instrument == "motif":
            moved_motif[(current.start_frame, position)] = new_midi
    return moved_motif


def _lead_plucks(
    out: list[Event],
    boundaries: list[int],
    section_scales: list[list[int]],
) -> dict[tuple[int, int], int]:
    """Smooth the leaps between consecutive plucks of one instrument at a time.

    Only the plucks move, only when the interval is more than a tritone, and
    only to a note the section's own scale contains: the pass exists to stop a
    line jumping around, not to rewrite it. Returns the motif notes it moved,
    keyed the way the appearance update expects them.
    """
    moved_motif: dict[tuple[int, int], int] = {}
    for instrument, indices in _pluck_indices_by_instrument(out).items():
        moved_motif.update(_lead_one_instrument(out, boundaries, section_scales, instrument, indices))
    return moved_motif


def _smoothed_bass(scale: list[int], previous: int, current: int) -> int | None:
    """The scale note that keeps a bass line stepwise across a big leap.

    The bass rule is stricter than the pluck's: the note has to land within
    five semitones of where it came from, because a bass that wanders takes
    the harmonic floor with it.
    """
    interval = abs(current - previous)
    candidates = []
    for note in scale:
        if note < 24 or note > 72:
            continue
        dist = abs(note - previous)
        if dist < interval - 1 and dist <= 5:  # stepwise preferred
            candidates.append((dist, note))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _lead_bass(out: list[Event], boundaries: list[int], section_scales: list[list[int]]) -> None:
    """Voice lead the bass line in place, hit by hit, more conservatively."""
    from indiegen.plan import BassEvent

    for idx, event in enumerate(out):
        if not isinstance(event, BassEvent):
            continue
        new_hits = []
        previous_midi: int | None = None
        for hit in event.hits:
            if previous_midi is not None and abs(hit.midi - previous_midi) > 7:  # large leap in bass
                section = _section_at_frame(boundaries, hit.frame)
                scale = section_scales[section] if section < len(section_scales) else []
                new_midi = _smoothed_bass(scale, previous_midi, hit.midi) if scale else None
                if new_midi is not None:
                    new_hits.append(hit.model_copy(update={"midi": new_midi}))
                    previous_midi = new_midi
                    continue
            new_hits.append(hit)
            previous_midi = hit.midi
        if new_hits != event.hits:
            out[idx] = event.model_copy(update={"hits": new_hits})


def _appearance_notes(
    appearances: list[MotifAppearance],
    out: list[Event],
    moved_motif: dict[tuple[int, int], int],
) -> list[MotifAppearance]:
    """Bring the recorded appearances in line with the notes that were moved."""
    if not moved_motif:
        return appearances
    from indiegen.plan import PluckEvent

    new_appearances: list[MotifAppearance] = []
    for appearance in appearances:
        notes = list(appearance.notes)
        # Find motif plucks for this appearance
        app_plucks = [
            ev
            for ev in out
            if isinstance(ev, PluckEvent)
            and ev.instrument == "motif"
            and appearance.start_frame <= ev.start_frame < appearance.start_frame + sum(appearance.durations)
        ]
        app_plucks.sort(key=lambda ev: ev.start_frame)
        for position, pluck in enumerate(app_plucks):
            if position < len(notes):
                notes[position] = pluck.midi
        new_appearances.append(appearance.model_copy(update={"notes": notes}))
    return new_appearances


def _apply_voice_leading(
    events: list[Event],
    appearances: list[MotifAppearance],
    boundaries: list[int],
    section_roots: list[int],
    section_modes: list[str],
    section_scales: list[list[int]],
    lane: LanePreset,
) -> tuple[list[Event], list[MotifAppearance]]:
    """Conservative voice leading pass: smooth large leaps while staying in scale.

    Only adjusts plucks (including motif), keeps changes minimal to avoid
    breaking modal character or creating functional cadences.

    The pass is three moves in a fixed order - the plucks, the bass, and the
    appearances that record what the plucks used to say - and each one lives
    in its own function because they answer to different rules.
    """
    out = list(events)
    moved_motif = _lead_plucks(out, boundaries, section_scales)
    _lead_bass(out, boundaries, section_scales)
    return out, _appearance_notes(appearances, out, moved_motif)
