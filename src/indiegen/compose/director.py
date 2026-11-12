"""director(): a pure Plan -> Plan transform.

No RNG, no clock, no randomness of any kind. Every move it makes is appended
to ``plan.director_log`` so that a human can read what the arranger did.

A move declares the instruments it applies to, and it is logged only if it
actually changed something: a strategy that matched nothing is neither
applied nor logged.

The strategies are BRIEF T14's: drop the drums for a while, transpose the
motif, halve the rhythm, take the bass out, leave the texture alone, swap
the delay to triplets, move the harmonic centre to the relative mode. Each
one is a function over the plan and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from indiegen.compose.tension import rederive_section_tension
from indiegen.errors import PlanError
from indiegen.plan import (
    BassEvent,
    DelaySend,
    DirectorMove,
    Event,
    HatEvent,
    KickEvent,
    MotifAppearance,
    Plan,
    SectionPlan,
    SnareEvent,
)
from indiegen.spectrum import declared_centroid_millihz
from indiegen.theory.consonance import chord_dissonance
from indiegen.theory.scales import chord_pool, mode_scale, relative_of

TRANSPOSE_UP_FOURTH: str = "transpose_up_fourth"
TRANSPOSE_MOTIF: str = "transpose_motif"
INVERT_MOTIF: str = "invert_motif"
RETROGRADE_MOTIF: str = "retrograde_motif"
DROP_DRUMS: str = "drop_drums"
DROP_KICK: str = "drop_kick"
HALF_TIME: str = "half_time"
DROP_BASS: str = "drop_bass"
SOLO_TEXTURE: str = "solo_texture"
SWAP_DELAY_TO_TRIPLETS: str = "swap_delay_to_triplets"
REHARMONIZE_RELATIVE: str = "reharmonize_relative"

# The instruments the rhythm strategies act on.
RHYTHM_INSTRUMENTS: tuple[str, ...] = ("kick", "snare", "hat")

# The last three seconds of a track always keep their material. A drop
# that runs into the ending leaves silence there, and a track that ends
# in silence is a broken ending and not a drop.
ENDING_GUARD_SECONDS: int = 3


@dataclass(frozen=True)
class Arrangement:
    """The parts of the plan a strategy may rewrite."""

    events: list[Event]
    appearances: list[MotifAppearance]
    sections: list[SectionPlan]
    delay_sends: list[DelaySend]


def _split_and_transpose(events: list[Event], move: DirectorMove) -> list[Event]:
    """Split the sustained material at the move and transpose the second half."""
    result: list[Event] = []
    half = move.crossfade_frames // 2
    for event in events:
        if event.instrument not in move.applies_to:
            result.append(event)
            continue
        end = event.start_frame + event.duration_frames
        if event.start_frame >= move.sample or end <= move.sample:
            result.append(event)
            continue
        head_end = move.sample + move.crossfade_frames - half
        tail_start = move.sample - half
        head = event.model_copy(
            update={
                "duration_frames": head_end - event.start_frame,
                "release_frames": move.crossfade_frames,
            }
        )
        tail = event.model_copy(
            update={
                "start_frame": tail_start,
                "duration_frames": end - tail_start,
                "midi": event.midi + move.parameter,
                "attack_frames": move.crossfade_frames,
            }
        )
        result.extend([head, tail])
    return result


def _motif_indices(events: list[Event], start_frame: int) -> list[int]:
    """The indices of the plucks that play one appearance of the motif."""
    return [
        index for index, event in enumerate(events) if event.instrument == "motif" and event.start_frame == start_frame
    ]


def _reshape_motif(
    events: list[Event],
    appearances: list[MotifAppearance],
    move: DirectorMove,
    reshape: Callable[[MotifAppearance, list[int]], list[int]],
) -> tuple[list[Event], list[MotifAppearance]]:
    """Rewrite the motif's appearances after the move, and the plucks with them."""
    new_events = list(events)
    new_appearances: list[MotifAppearance] = []
    for appearance in appearances:
        if appearance.start_frame < move.sample:
            new_appearances.append(appearance)
            continue
        notes = list(appearance.notes)
        shaped = reshape(appearance, notes)
        if shaped == notes:
            new_appearances.append(appearance)
            continue
        indices = _motif_indices(new_events, appearance.start_frame)
        for position, index in enumerate(indices):
            if position >= len(shaped):
                break
            new_events[index] = new_events[index].model_copy(update={"midi": shaped[position]})
        new_appearances.append(appearance.model_copy(update={"notes": shaped}))
    return new_events, new_appearances


def _drop_hits(
    events: list[Event],
    move: DirectorMove,
    instruments: tuple[str, ...],
    ending: int,
) -> list[Event]:
    """Remove the hits of the given instruments inside the move's span.

    The ending is never emptied: the last seconds of a track keep their
    material, or the piece ends in silence.
    """
    stop = min(move.sample + move.crossfade_frames, ending)
    result: list[Event] = []
    for event in events:
        if event.instrument not in instruments or not isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            result.append(event)
            continue
        hits = [hit for hit in event.hits if not (move.sample <= hit.grid_frame() < stop)]
        result.append(event.model_copy(update={"hits": hits}))
    return result


def _half_time(events: list[Event], move: DirectorMove, frames_per_beat: int, ending: int) -> list[Event]:
    """Keep only the hits that land on a beat."""
    stop = min(move.sample + move.crossfade_frames, ending)
    result: list[Event] = []
    for event in events:
        if event.instrument not in RHYTHM_INSTRUMENTS or not isinstance(
            event, (KickEvent, SnareEvent, HatEvent, BassEvent)
        ):
            result.append(event)
            continue
        hits = [
            hit
            for hit in event.hits
            if not (move.sample <= hit.grid_frame() < stop) or hit.grid_frame() % frames_per_beat == 0
        ]
        result.append(event.model_copy(update={"hits": hits}))
    return result


def _degree_of(midi: int, scale: list[int]) -> int:
    """Where a note sits in a scale, or where the nearest note sits if it is outside.

    A bass note is drawn from the section's own scale, so the first case is
    the one that happens; the second keeps a note written chromatically from
    falling off the end of the list.
    """
    return min(range(len(scale)), key=lambda index: (abs(scale[index] - midi), index))


def _moved_sections(
    sections: list[SectionPlan],
    move: DirectorMove,
) -> tuple[list[SectionPlan], dict[int, tuple[list[int], list[int]]]]:
    """The sections after the move, and the two scales each one moved between.

    Both scales are built over the same span from their own root, so a note's
    index in the first is the same degree in the second.
    """
    new_sections: list[SectionPlan] = []
    scales: dict[int, tuple[list[int], list[int]]] = {}
    for section in sections:
        if section.start_frame < move.sample:
            new_sections.append(section)
            continue
        relative, interval = relative_of(section.mode)
        root = section.root_midi + interval
        scales[section.index] = (
            mode_scale(section.mode, section.root_midi - 12, 4),
            mode_scale(relative, root - 12, 4),
        )
        new_sections.append(section.model_copy(update={"mode": relative, "root_midi": root}))
    return new_sections, scales


def _reharmonize(
    events: list[Event],
    sections: list[SectionPlan],
    move: DirectorMove,
) -> tuple[list[Event], list[SectionPlan]]:
    """Move the harmonic centre of the sections after the move to the relative mode.

    The relative of a mode is the mode it shares its notes with, so the notes
    already written are still notes of the section's scale after the move and
    nothing has to be transposed for them to agree with it. What moves is the
    bass: each hit keeps its degree of the old scale and takes the same degree
    of the new one, so the root follows the centre while the melody, the pad
    and the drums hold the notes they were written with.
    """
    new_sections, scales = _moved_sections(sections, move)
    if not scales:
        return events, new_sections

    def scales_at(frame: int) -> tuple[list[int], list[int]] | None:
        for section in new_sections:
            if section.start_frame <= frame < section.end_frame and section.index in scales:
                return scales[section.index]
        return None

    new_events: list[Event] = []
    for event in events:
        if not isinstance(event, BassEvent):
            new_events.append(event)
            continue
        hits = list(event.hits)
        for index, hit in enumerate(event.hits):
            pair = scales_at(hit.grid_frame())
            if pair is None:
                continue
            before, after = pair
            hits[index] = hit.model_copy(update={"midi": after[_degree_of(hit.midi, before)]})
        new_events.append(event.model_copy(update={"hits": hits}))
    return new_events, new_sections


def _ending(plan: Plan) -> int:
    """The frame the ending's material starts at."""
    return max(0, plan.duration_frames - ENDING_GUARD_SECONDS * plan.sample_rate)


def _section_consonance(plan: Plan, section: SectionPlan) -> dict[str, int]:
    """What the section's own scale admits of the declared sonority, and its roughness.

    The section is measured at its CURRENT mode and root - the ones the moves
    left it with - so a reharmonized section is measured at the root it moved
    to, with the same ruler the composer drew the harmonic centre with: the
    declared sonority against the plan's declared voices, admitted under the
    section's own scale and the plan's chromatic budget.

    Two facts, not one: the register-fair scorer averages per pair, so a
    fragment (a dyad prefix) scores LOW and the roughness alone would praise a
    section that cannot carry the sonority at all. The admitted count is the
    candidacy fact; the permille is the roughness fact. Both 0 when consonance
    scoring is off, the lane declares no sonority, or the plan declares no
    voices.
    """
    if not plan.consonance_scoring_enabled or not plan.chord_intervals or not plan.chord_voices:
        return {"chord_tones_admitted": 0, "chord_consonance_permille": 0}
    scale = mode_scale(section.mode, section.root_midi, 2)
    tones = chord_pool(scale, section.root_midi, plan.chord_intervals, plan.chromatic_budget_permille)
    voices = [[(ratio.numerator, ratio.denominator) for ratio in voice] for voice in plan.chord_voices]
    return {
        "chord_tones_admitted": len(tones),
        "chord_consonance_permille": chord_dissonance(tones, voices) if tones else 0,
    }


def _apply(move: DirectorMove, plan: Plan) -> Arrangement | None:
    """Apply one move. ``None`` means it changed nothing."""
    handler = _HANDLERS.get(move.strategy)
    if handler is None:
        raise PlanError(f"unknown director strategy {move.strategy!r}", preset=plan.preset, seed=plan.seed)
    parts = Arrangement(
        events=list(plan.events),
        appearances=list(plan.motif_appearances),
        sections=list(plan.sections),
        delay_sends=list(plan.delay_sends),
    )
    return handler(move, plan, parts)


def _transpose_up_fourth(move: DirectorMove, plan: Plan, parts: Arrangement) -> Arrangement | None:
    events = _split_and_transpose(parts.events, move)
    if events == parts.events:
        return None
    return Arrangement(events, parts.appearances, parts.sections, parts.delay_sends)


def _motif(move: DirectorMove, plan: Plan, parts: Arrangement) -> Arrangement | None:
    if "motif" not in move.applies_to:
        return None
    shape = _MOTIF_SHAPES.get(move.strategy)
    if shape is None:
        raise PlanError(f"unknown director strategy {move.strategy!r}", preset=plan.preset, seed=plan.seed)
    events, appearances = _reshape_motif(
        parts.events, parts.appearances, move, lambda appearance, notes: shape(plan, appearance, notes, move)
    )
    if appearances == parts.appearances:
        return None
    return Arrangement(events, appearances, parts.sections, parts.delay_sends)


def _drop(move: DirectorMove, plan: Plan, parts: Arrangement) -> Arrangement | None:
    instruments = tuple(move.applies_to)
    if not instruments:
        return None
    events = _drop_hits(parts.events, move, instruments, _ending(plan))
    if events == parts.events:
        return None
    return Arrangement(events, parts.appearances, parts.sections, parts.delay_sends)


def _half_time_move(move: DirectorMove, plan: Plan, parts: Arrangement) -> Arrangement | None:
    if plan.frames_per_beat <= 0:
        return None
    events = _half_time(parts.events, move, plan.frames_per_beat, _ending(plan))
    if events == parts.events:
        return None
    return Arrangement(events, parts.appearances, parts.sections, parts.delay_sends)


def _triplets(move: DirectorMove, plan: Plan, parts: Arrangement) -> Arrangement | None:
    if not parts.delay_sends or plan.frames_per_beat <= 0:
        return None
    triplets = plan.frames_per_beat * 2 // 3
    if triplets <= 0 or parts.delay_sends[0].delay_frames == triplets:
        return None
    delay_sends = [parts.delay_sends[0].model_copy(update={"delay_frames": triplets}), *parts.delay_sends[1:]]
    return Arrangement(parts.events, parts.appearances, parts.sections, delay_sends)


def _reharmonize_relative(move: DirectorMove, plan: Plan, parts: Arrangement) -> Arrangement | None:
    events, sections = _reharmonize(parts.events, parts.sections, move)
    if sections == parts.sections:
        return None
    return Arrangement(events, parts.appearances, sections, parts.delay_sends)


def _shape_transpose(plan: Plan, appearance: MotifAppearance, notes: list[int], move: DirectorMove) -> list[int]:
    return [note + move.parameter for note in notes]


def _shape_invert(plan: Plan, appearance: MotifAppearance, notes: list[int], move: DirectorMove) -> list[int]:
    # The axis is the harmonic centre of the section the appearance is in,
    # the same axis the composer used.
    axis = plan.sections[min(appearance.section_index, len(plan.sections) - 1)].root_midi if plan.sections else 0
    return [2 * axis - note for note in notes]


def _shape_retrograde(plan: Plan, appearance: MotifAppearance, notes: list[int], move: DirectorMove) -> list[int]:
    return list(reversed(notes))


# One entry per strategy: the name a preset declares, and the function that
# realises it. A strategy that is missing here is a preset error that the
# Director reports, not a move that is silently ignored.
_MOTIF_SHAPES: Mapping[str, Callable[[Plan, MotifAppearance, list[int], DirectorMove], list[int]]] = MappingProxyType(
    {
        TRANSPOSE_MOTIF: _shape_transpose,
        INVERT_MOTIF: _shape_invert,
        RETROGRADE_MOTIF: _shape_retrograde,
    }
)

_HANDLERS: Mapping[str, Callable[[DirectorMove, Plan, Arrangement], Arrangement | None]] = MappingProxyType(
    {
        TRANSPOSE_UP_FOURTH: _transpose_up_fourth,
        TRANSPOSE_MOTIF: _motif,
        INVERT_MOTIF: _motif,
        RETROGRADE_MOTIF: _motif,
        DROP_DRUMS: _drop,
        DROP_KICK: _drop,
        DROP_BASS: _drop,
        SOLO_TEXTURE: _drop,
        HALF_TIME: _half_time_move,
        SWAP_DELAY_TO_TRIPLETS: _triplets,
        REHARMONIZE_RELATIVE: _reharmonize_relative,
    }
)


def director(plan: Plan) -> Plan:
    """Apply the strategy deck to a Plan. The input is never modified.

    The moves are applied to the *running* plan, one after the other, so
    that the arranger's moves compose: a move that drops the drums and a
    later move that halves the rhythm are both in the result, and the
    second one sees what the first one did.
    """
    events = list(plan.events)
    appearances = list(plan.motif_appearances)
    sections = list(plan.sections)
    delay_sends = list(plan.delay_sends)
    log = list(plan.director_log)
    for move in plan.strategy_deck:
        if move.sample >= plan.duration_frames:
            continue
        running = plan.model_copy(
            update={
                "events": events,
                "motif_appearances": appearances,
                "sections": sections,
                "delay_sends": delay_sends,
            }
        )
        result = _apply(move, running)
        if result is None:
            continue
        events = result.events
        appearances = result.appearances
        sections = result.sections
        delay_sends = result.delay_sends
        log.append(move)
    # c41: the declared centroid is a statement about the material that
    # sounds, so it is re-derived from the FINAL events. The deck contains
    # transpose_up_fourth, which rewrites pad, drone and lead midi: a field
    # computed before the moves would be stale in exactly the way gate 6's
    # timbre table is stale, inside the field that exists to name the
    # staleness. No RNG here - the leaf is a pure function of the events.
    # The tension is the same statement: it is re-derived from the final
    # events at the final levels, without re-running the solver, so levels
    # and corridors stand and only the spent walk moves.
    rederived = rederive_section_tension(events, sections)
    sections = [
        section.model_copy(
            update={
                "declared_centroid_millihz": declared_centroid_millihz(events, section.start_frame, section.end_frame),
                "tension_permille": rederived[index][0],
                "tension_delta_permille": rederived[index][1],
                # issue #17: what the section's post-move harmony measures. A
                # pure function of the plan - the moves may have rewritten the
                # section's mode and root, and this is the plan saying whether
                # the centre it ended on can still carry the lane's sonority.
                **_section_consonance(plan, section),
            }
        )
        for index, section in enumerate(sections)
    ]
    updated = plan.model_copy(
        update={
            "events": events,
            "motif_appearances": appearances,
            "sections": sections,
            "delay_sends": delay_sends,
            "director_log": log,
        }
    )
    return Plan.model_validate(updated.model_dump())
