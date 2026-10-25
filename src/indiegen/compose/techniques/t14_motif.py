"""T14, part one: the motif and its appearances.

The station's signature is a recurring motif: three to seven notes, one
cell, transformed per track but recognisable. The cell is played by the
Karplus-Strong, so the motif and the station's signature timbre are the
same voice - the motif is heard through the dotted-eighth delay like
everything else the guitar plays.

Every appearance is recorded in the plan: the section it sits in, the
transform it wears, the pitches and the durations. Gate 13 counts the
appearances that wear a transform, and the arranger's strategies can
rewrite them afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.plan import MotifAppearance, PluckEvent, Rational
from indiegen.theory.motif import TRANSFORMS, Cell, transform

# The motif's amplitude, the same as the deja-vu's stabs.
MOTIF_AMPLITUDE_MILLIBELS: int = -6000

# The transposition of a transformed statement, in semitones.
TRANSPOSE_RANGE: int = 5

# The length of a fragment, in notes.
FRAGMENT_LENGTH: int = 2

# A phrase is eight bars in a pulsed lane, and half a minute in a lane
# with no pulse. The motif comes back once a phrase.
PHRASE_BARS: int = 8
PHRASE_SECONDS: int = 30


@dataclass(frozen=True)
class StringVoice:
    """The Karplus-Strong's parameters, from the lane's string card."""

    feedback_numerator: int
    feedback_denominator: int
    brightness: Rational
    pluck_position_permille: int
    detune_cents: int


def build_cell(bank: list[list[int]], rhythm: list[int], root_midi: int, step_frames: int, rng: SplitMix64) -> Cell:
    """The motif cell: the drawn motif's pitches and their durations.

    The bank's entries are scale degrees over the track's root, and the
    rhythm is the cell's own shape in steps of the lane's beat.
    """
    if not bank:
        return []
    degrees = list(rng.choice(bank))
    if not degrees:
        return []
    notes: Cell = []
    for index, degree in enumerate(degrees):
        steps = rhythm[index % len(rhythm)] if rhythm else 1
        notes.append((root_midi + degree, max(1, steps * step_frames)))
    return notes


def plan_motif(
    cell: Cell,
    string: StringVoice,
    ctx: TechniqueContext,
    rng: SplitMix64,
) -> tuple[list[MotifAppearance], list[PluckEvent]]:
    """The motif's appearances, and the plucks that play them.

    The motif is stated at the start of every section and at the head of
    every phrase: a motif that only comes back once a minute is a
    callback, and BRIEF 6 wants a cell that recurs. The first statement is
    the cell as it is; every other one wears a transform, so the motif
    comes back without ever coming back the same - which is what BRIEF 6
    asks for and what BRIEF 7 accepts.
    """
    if not cell:
        return [], []
    appearances: list[MotifAppearance] = []
    events: list[PluckEvent] = []
    statement = 0
    boundaries = ctx.section_boundaries
    phrase_frames = ctx.frames_per_bar * PHRASE_BARS if ctx.frames_per_bar else PHRASE_SECONDS * ctx.sample_rate
    placements: list[tuple[int, int]] = []
    for index in range(len(boundaries) - 1):
        placements.append((boundaries[index], index))
    frame = phrase_frames
    while frame < ctx.duration_frames:
        section = ctx.section_index(frame)
        if not any(placement == frame for placement, _ in placements):
            placements.append((frame, section))
        frame += phrase_frames
    placements.sort()
    for placement, section in placements:
        name = "identity" if statement == 0 else TRANSFORMS[(statement - 1) % len(TRANSFORMS)]
        parameter = 0
        if name == "transpose":
            parameter = rng.between(-TRANSPOSE_RANGE, TRANSPOSE_RANGE)
        elif name == "fragment":
            parameter = FRAGMENT_LENGTH
        axis = ctx.section_roots[section] if ctx.section_roots else ctx.root_midi
        shaped = transform(name, cell, parameter, axis)
        total = sum(duration for _, duration in shaped)
        if placement + total > ctx.duration_frames:
            continue
        offset = placement
        for midi, duration in shaped:
            events.append(
                PluckEvent(
                    kind="pluck",
                    instrument="motif",
                    start_frame=offset,
                    duration_frames=duration,
                    midi=midi,
                    pan_permille=0,
                    amplitude_millibels=MOTIF_AMPLITUDE_MILLIBELS,
                    attack_frames=0,
                    release_frames=0,
                    feedback=Rational(
                        numerator=string.feedback_numerator,
                        denominator=string.feedback_denominator,
                    ),
                    brightness=string.brightness,
                    pluck_position_permille=string.pluck_position_permille,
                    detune_cents=string.detune_cents,
                    excitation_seed=rng.next_u64(),
                )
            )
            offset += duration
        appearances.append(
            MotifAppearance(
                section_index=section,
                transform=name,
                parameter=parameter,
                start_frame=placement,
                notes=[midi for midi, _ in shaped],
                durations=[duration for _, duration in shaped],
            )
        )
        statement += 1
    return appearances, events
