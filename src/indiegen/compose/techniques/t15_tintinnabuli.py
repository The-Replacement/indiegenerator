"""Tintinnabuli duo - M-voice and T-voice.

M-voice is the motif/pluck cell in a higher register; T-voice is generated
note-against-note from it by a POSITION rule against the section tonic triad.
Both voices reuse the Karplus-Strong PluckEvent.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import TintinnabuliCard
from indiegen.plan import PluckEvent, Rational
from indiegen.theory.scales import tintinnabuli_t_voice


def _infer_mode(scale: list[int], root: int, declared: str) -> str:
    if declared != "auto":
        return declared
    if root + 4 in scale:
        return "major"
    return "minor"


def plan_tintinnabuli(card: TintinnabuliCard, rng: SplitMix64, ctx: TechniqueContext) -> list[PluckEvent]:
    """Generate the M-voice and T-voice pluck events."""
    count = rng.between(card.count.min, card.count.max)
    spacing = rng.between(card.spacing_seconds.min, card.spacing_seconds.max) * ctx.sample_rate
    duration = rng.between(card.duration_seconds.min, card.duration_seconds.max) * ctx.sample_rate
    feedback = Rational(
        numerator=rng.between(card.feedback_num_min, card.feedback_num_max),
        denominator=card.feedback_den,
    )
    excitation_seed = rng.next_u64()

    events: list[PluckEvent] = []
    start = 0
    note_index = 0
    for _ in range(count):
        if start >= ctx.duration_frames:
            break
        length = min(duration, ctx.duration_frames - start)
        section = ctx.section_at(start)
        densities = ctx.section_densities
        density = densities[min(section, len(densities) - 1)] if densities else 100
        if not ctx.admits(section, "tintinnabuli", density, card.min_density):
            start += spacing
            continue

        root = ctx.section_roots[section] if ctx.section_roots and section < len(ctx.section_roots) else ctx.root_midi
        scale = (
            ctx.section_scales[section] if ctx.section_scales and section < len(ctx.section_scales) else ctx.scale_midi
        )
        mode = _infer_mode(scale, root, card.tonic_triad_mode)

        m_midi = root + 12
        t_midi = tintinnabuli_t_voice(
            m_midi,
            root,
            mode,
            card.position,
            card.range_direction,
            index=note_index,
            process=card.process,
        )

        for voice, midi, _detune_offset in (
            ("tintinnabuli_m", m_midi, 0),
            ("tintinnabuli", t_midi, card.detune_cents),
        ):
            events.append(
                PluckEvent(
                    kind="pluck",
                    instrument=voice,
                    start_frame=start,
                    duration_frames=length,
                    midi=midi,
                    pan_permille=0,
                    amplitude_millibels=card.amplitude_millibels,
                    attack_frames=0,
                    release_frames=0,
                    feedback=feedback,
                    brightness=card.brightness,
                    pluck_position_permille=card.pluck_position_permille,
                    detune_cents=card.detune_cents if voice == "tintinnabuli" else 0,
                    excitation_seed=excitation_seed + (0 if voice == "tintinnabuli_m" else 1),
                )
            )
        note_index += 1
        start += spacing

    return events
