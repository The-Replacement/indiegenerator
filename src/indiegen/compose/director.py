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

from collections.abc import Callable
from dataclasses import dataclass

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
from indiegen.theory.scales import RELATIVE_INTERVAL, RELATIVE_MODES

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

STRATEGIES: tuple[str, ...] = (
    TRANSPOSE_UP_FOURTH,
    TRANSPOSE_MOTIF,
    INVERT_MOTIF,
    RETROGRADE_MOTIF,
    DROP_DRUMS,
    DROP_KICK,
    HALF_TIME,
    DROP_BASS,
    SOLO_TEXTURE,
    SWAP_DELAY_TO_TRIPLETS,
    REHARMONIZE_RELATIVE,
)

# The instruments the rhythm strategies act on.
RHYTHM_INSTRUMENTS: tuple[str, ...] = ("kick", "snare", "hat")


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


def _drop_hits(events: list[Event], move: DirectorMove, instruments: tuple[str, ...]) -> list[Event]:
    """Remove the hits of the given instruments inside the move's span."""
    stop = move.sample + move.crossfade_frames
    result: list[Event] = []
    for event in events:
        if event.instrument not in instruments or not isinstance(event, (KickEvent, SnareEvent, HatEvent, BassEvent)):
            result.append(event)
            continue
        hits = [hit for hit in event.hits if not (move.sample <= hit.frame < stop)]
        result.append(event.model_copy(update={"hits": hits}))
    return result


def _half_time(events: list[Event], move: DirectorMove, frames_per_beat: int) -> list[Event]:
    """Keep only the hits that land on a beat."""
    stop = move.sample + move.crossfade_frames
    result: list[Event] = []
    for event in events:
        if event.instrument not in RHYTHM_INSTRUMENTS or not isinstance(
            event, (KickEvent, SnareEvent, HatEvent, BassEvent)
        ):
            result.append(event)
            continue
        hits = [hit for hit in event.hits if not (move.sample <= hit.frame < stop) or hit.frame % frames_per_beat == 0]
        result.append(event.model_copy(update={"hits": hits}))
    return result


def _reharmonize(
    events: list[Event],
    sections: list[SectionPlan],
    move: DirectorMove,
) -> tuple[list[Event], list[SectionPlan]]:
    """Move the harmonic centre of the sections after the move to the relative mode.

    The notes do not move: a relative mode is the same set of pitches with
    another centre, and the bass follows the new centre, which is what the
    ear hears.
    """
    new_sections: list[SectionPlan] = []
    roots: dict[int, int] = {}
    for section in sections:
        if section.start_frame < move.sample:
            new_sections.append(section)
            continue
        relative = RELATIVE_MODES.get(section.mode, section.mode)
        root = section.root_midi + RELATIVE_INTERVAL
        roots[section.index] = root
        new_sections.append(section.model_copy(update={"mode": relative, "root_midi": root}))
    if not roots:
        return events, new_sections
    new_events: list[Event] = []
    for event in events:
        if not isinstance(event, BassEvent):
            new_events.append(event)
            continue
        hits = []
        for hit in event.hits:
            owner = next(
                (item for item in new_sections if item.start_frame <= hit.frame < item.end_frame),
                None,
            )
            if owner is None or owner.index not in roots:
                hits.append(hit)
                continue
            offset = hit.midi - (owner.root_midi - RELATIVE_INTERVAL)
            hits.append(hit.model_copy(update={"midi": owner.root_midi - 12 + offset + 12}))
        new_events.append(event.model_copy(update={"hits": hits}))
    return new_events, new_sections


def _apply(move: DirectorMove, plan: Plan) -> Arrangement | None:
    """Apply one move. ``None`` means it changed nothing."""
    events = list(plan.events)
    appearances = list(plan.motif_appearances)
    sections = list(plan.sections)
    delay_sends = list(plan.delay_sends)

    if move.strategy == TRANSPOSE_UP_FOURTH:
        new_events = _split_and_transpose(events, move)
        if new_events == events:
            return None
        return Arrangement(new_events, appearances, sections, delay_sends)

    if move.strategy in (TRANSPOSE_MOTIF, INVERT_MOTIF, RETROGRADE_MOTIF):
        if "motif" not in move.applies_to:
            return None
        if move.strategy == TRANSPOSE_MOTIF:

            def reshape(appearance: MotifAppearance, notes: list[int]) -> list[int]:
                return [note + move.parameter for note in notes]

        elif move.strategy == INVERT_MOTIF:

            def reshape(appearance: MotifAppearance, notes: list[int]) -> list[int]:
                # The axis is the harmonic centre of the section the
                # appearance is in, the same axis the composer used.
                section = plan.sections[min(appearance.section_index, len(plan.sections) - 1)]
                axis = section.root_midi if plan.sections else 0
                return [2 * axis - note for note in notes]

        else:

            def reshape(appearance: MotifAppearance, notes: list[int]) -> list[int]:
                return list(reversed(notes))

        new_events, new_appearances = _reshape_motif(events, appearances, move, reshape)
        if new_appearances == appearances:
            return None
        return Arrangement(new_events, new_appearances, sections, delay_sends)

    if move.strategy in (DROP_DRUMS, DROP_KICK, DROP_BASS, SOLO_TEXTURE):
        instruments = tuple(move.applies_to)
        if not instruments:
            return None
        new_events = _drop_hits(events, move, instruments)
        if new_events == events:
            return None
        return Arrangement(new_events, appearances, sections, delay_sends)

    if move.strategy == HALF_TIME:
        if plan.frames_per_beat <= 0:
            return None
        new_events = _half_time(events, move, plan.frames_per_beat)
        if new_events == events:
            return None
        return Arrangement(new_events, appearances, sections, delay_sends)

    if move.strategy == SWAP_DELAY_TO_TRIPLETS:
        if not delay_sends or plan.frames_per_beat <= 0:
            return None
        triplets = plan.frames_per_beat * 2 // 3
        if triplets <= 0 or delay_sends[0].delay_frames == triplets:
            return None
        delay_sends = [delay_sends[0].model_copy(update={"delay_frames": triplets}), *delay_sends[1:]]
        return Arrangement(events, appearances, sections, delay_sends)

    if move.strategy == REHARMONIZE_RELATIVE:
        new_events, new_sections = _reharmonize(events, sections, move)
        if new_sections == sections:
            return None
        return Arrangement(new_events, appearances, new_sections, delay_sends)

    raise PlanError(f"unknown director strategy {move.strategy!r}", preset=plan.preset, seed=plan.seed)


def director(plan: Plan) -> Plan:
    """Apply the strategy deck to a Plan. The input is never modified."""
    events = list(plan.events)
    appearances = list(plan.motif_appearances)
    sections = list(plan.sections)
    delay_sends = list(plan.delay_sends)
    log = list(plan.director_log)
    for move in plan.strategy_deck:
        if move.sample >= plan.duration_frames:
            continue
        result = _apply(move, plan)
        if result is None:
            continue
        events = result.events
        appearances = result.appearances
        sections = result.sections
        delay_sends = result.delay_sends
        log.append(move)
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
