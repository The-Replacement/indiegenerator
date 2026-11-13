"""Tintinnabuli second voice.

The M-voice is the motif/pluck cell the lane already plans: the station
signature on the Karplus-Strong bus. The T-voice is derived note-against-note
from those M notes by Pärt's position rule over the section's tonic triad.

The card is an armature, not a line of its own. It declares the position, the
range direction, the process and the T-voice timbre; the composer derives the
T events from the final M events, so the two voices cannot drift apart in
register or time.
"""

from __future__ import annotations

from collections.abc import Sequence

from indiegen.compose.context import TechniqueContext
from indiegen.config import TintinnabuliCard
from indiegen.plan import PluckEvent, Rational
from indiegen.theory.scales import tintinnabuli_t_voice

# The T-voice's excitation differs from its M note's, deterministically: the
# rule decides the pitch, and this decides that the two strings are not the
# same string.
_EXCITATION_MIX: int = 0x9E3779B97F4A7C15


def _triad_mode(declared: str, section_mode: str) -> str:
    """The triad quality: the section's mode unless the card overrides it."""
    return section_mode if declared == "auto" else declared


def _feedback(card: TintinnabuliCard, m_event: PluckEvent) -> Rational:
    """A feedback inside the declared range, chosen by the M note alone."""
    span = max(0, card.feedback_num_max - card.feedback_num_min)
    numerator = card.feedback_num_min + (m_event.excitation_seed % (span + 1))
    return Rational(numerator=numerator, denominator=card.feedback_den)


def plan_tintinnabuli(
    m_events: Sequence[PluckEvent],
    card: TintinnabuliCard,
    ctx: TechniqueContext,
    section_modes: Sequence[str],
) -> list[PluckEvent]:
    """Derive the T-voice note-against-note from the M-voice plucks.

    One T event per admitted M event, at the same frame and for the same
    duration. The pitch is the position rule against the section's tonic
    triad; the process's index is the ordinal of the emitted T note, so a
    section the card does not play in does not shift the process.
    """
    if not section_modes:
        return []
    out: list[PluckEvent] = []
    t_index = 0
    for m_event in m_events:
        section = min(ctx.section_at(m_event.start_frame), len(section_modes) - 1)
        density = ctx.section_densities[section] if ctx.section_densities else 100
        if not ctx.admits(section, "tintinnabuli", density, card.min_density):
            continue
        root = ctx.section_roots[section] if ctx.section_roots else ctx.root_midi
        mode = _triad_mode(card.tonic_triad_mode, section_modes[section])
        t_midi = tintinnabuli_t_voice(
            m_event.midi,
            root,
            mode,
            card.position,
            card.range_direction,
            index=t_index,
            process=card.process,
        )
        out.append(
            PluckEvent(
                kind="pluck",
                instrument="tintinnabuli",
                start_frame=m_event.start_frame,
                duration_frames=m_event.duration_frames,
                midi=t_midi,
                pan_permille=0,
                amplitude_millibels=card.amplitude_millibels,
                attack_frames=0,
                release_frames=0,
                feedback=_feedback(card, m_event),
                brightness=card.brightness,
                pluck_position_permille=card.pluck_position_permille,
                detune_cents=card.detune_cents,
                excitation_seed=m_event.excitation_seed ^ _EXCITATION_MIX,
            )
        )
        t_index += 1
    return out
