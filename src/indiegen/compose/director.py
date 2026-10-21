"""director(): a pure Plan -> Plan transform.

No RNG, no clock, no randomness of any kind. Every move it makes is appended
to ``plan.director_log`` so that a human can read what the arranger did.

A move declares the event kinds it applies to, and it is logged only if it
actually changed something: a strategy that matched no event is neither
applied nor logged.
"""

from __future__ import annotations

from indiegen.errors import PlanError
from indiegen.plan import DirectorMove, Event, Plan

TRANSPOSE_UP_FOURTH: str = "transpose_up_fourth"


def _transpose(events: list[Event], move: DirectorMove) -> list[Event]:
    """Split the sustained material at the move and transpose the second half."""
    result: list[Event] = []
    half = move.crossfade_frames // 2
    for event in events:
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


def director(plan: Plan) -> Plan:
    """Apply the strategy deck to a Plan. The input is never modified."""
    events = list(plan.events)
    log = list(plan.director_log)
    for move in plan.strategy_deck:
        if move.strategy != TRANSPOSE_UP_FOURTH:
            raise PlanError(f"unknown director strategy {move.strategy!r}", preset=plan.preset, seed=plan.seed)
        if move.sample >= plan.duration_frames:
            continue
        if not any(event.kind in move.applies_to for event in events):
            continue
        events = _transpose(events, move)
        log.append(move)
    updated = plan.model_copy(update={"events": events, "director_log": log})
    return Plan.model_validate(updated.model_dump())
