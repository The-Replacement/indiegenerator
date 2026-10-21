"""T5 - the deja-vu sequencer.

Randomness with memory, and the single most important anti-random-walk
mechanism there is. The lane keeps a ring buffer of the values it has
generated; each step either replays one from the buffer or generates a new
one, quantized to the scale and biased toward the harmonic center. The
replay probability morphs across the sections, from a little at the start
to a lot at the end, so a motif emerges and dissolves instead of being
looped or wandered.

The stabs it produces are Karplus-Strong plucks: the guitar is the
instrument and T5 is what plays it.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import DejaVuCard
from indiegen.plan import PluckEvent, Rational

REPLAY_START_PERMILLE: int = 150
REPLAY_END_PERMILLE: int = 850


def _nearest_scale_note(scale: list[int], target: int) -> int:
    """The scale note nearest to the target, within the scale's own range."""
    if not scale:
        return target
    return min(scale, key=lambda note: (abs(note - target), note))


def replay_permille(card: DejaVuCard, section: int, section_count: int) -> int:
    """The replay probability of a section, from explore to locked.

    BRIEF T5: "d morphs per section: 0.15 (explore) -> 0.85 (locked)". The
    plan records the resolved values, so gate 13 can assert that the morph
    really happened.
    """
    if section_count <= 1:
        return card.replay_max_permille
    position = section / (section_count - 1)
    low = card.replay_min_permille
    high = card.replay_max_permille
    return int(round(low + (high - low) * position))


def plan_deja_vu(card: DejaVuCard, rng: SplitMix64, ctx: TechniqueContext) -> list[PluckEvent]:
    """The deja-vu stabs over the track.

    The buffer holds the last pitches that were generated, and a step
    replays one of them with the section's probability. The new values are
    drawn around the harmonic centre of the section and quantized to the
    section's scale, so a modal shift is heard in the notes themselves.
    """
    buffer: list[int] = []
    events: list[PluckEvent] = []
    boundaries = ctx.section_boundaries
    section_count = max(1, len(boundaries) - 1)
    step_frames = max(1, ctx.frames_per_beat * card.step_beats)
    total_steps = ctx.duration_frames // step_frames

    densities = ctx.section_densities
    for step in range(total_steps):
        frame = step * step_frames
        section = 0
        for index, boundary in enumerate(boundaries):
            if frame >= boundary:
                section = index
        # The layer only plays in the sections the arrangement has reached.
        if densities and densities[min(section, len(densities) - 1)] < card.min_density:
            continue
        probability = replay_permille(card, section, section_count)
        scale = ctx.section_scales[section] if ctx.section_scales else ctx.scale_midi
        root = ctx.section_roots[section] if ctx.section_roots else ctx.root_midi
        if buffer and rng.below(1000) < probability:
            midi = buffer[rng.below(len(buffer))]
        else:
            offset = card.bias + rng.between(-card.spread, card.spread)
            midi = _nearest_scale_note(scale, root + offset)
            buffer.append(midi)
            if len(buffer) > card.buffer_size:
                buffer.pop(0)
        events.append(
            PluckEvent(
                kind="pluck",
                instrument="pluck",
                start_frame=frame,
                duration_frames=card.note_frames,
                midi=midi,
                pan_permille=rng.between(-300, 300),
                amplitude_millibels=-600,
                attack_frames=0,
                release_frames=0,
                feedback=Rational(numerator=card.feedback_num, denominator=card.feedback_den),
                brightness=card.brightness,
                pluck_position_permille=card.pluck_position_permille,
                detune_cents=card.detune_cents,
                excitation_seed=rng.next_u64(),
            )
        )
    return events
