"""T1 - poly-period loops (Eno, Music for Airports).

Three to nine voices, each looping on its own period between fifteen and
ninety seconds. The periods are distinct, so the superpattern is the least
common multiple of all of them and effectively never repeats. All the voices
come from one chord, chosen so that at most one pair forms a minor second:
beauty with one grain of spice.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.config import PolyPeriodCard
from indiegen.errors import PlanError
from indiegen.plan import Partial, PolyPeriodEvent, PolyPeriodVoice
from indiegen.theory.scales import chord_pool

MINOR_SECOND_SEMITONES: frozenset[int] = frozenset({1, 11})
DENSITY_MIN: float = 0.5
DENSITY_MAX: float = 2.0


def sounding_frames(period: int, on: int, phase: int, duration: int) -> int:
    """The exact number of frames a voice sounds over the track's real length."""
    total = 0
    start = phase
    while start < duration:
        total += max(0, min(start + on, duration) - start)
        start += period
    return total


def _density(periods: list[int], ons: list[int], phases: list[int], duration: int) -> float:
    """The average number of voices sounding at any instant."""
    if duration <= 0:
        return 0.0
    frames = sum(
        sounding_frames(period, on, phase, duration) for period, on, phase in zip(periods, ons, phases, strict=True)
    )
    return frames / duration


def _minor_second_pairs(pitches: list[int]) -> int:
    """The number of unordered voice pairs a minor second apart."""
    pairs = 0
    for index, first in enumerate(pitches):
        for second in pitches[index + 1 :]:
            if abs(first - second) % 12 in MINOR_SECOND_SEMITONES:
                pairs += 1
    return pairs


def _usable_intervals(card: PolyPeriodCard, ctx: TechniqueContext) -> list[int]:
    """The chord tones the scale and the chromatic budget admit.

    The station may declare its own chromatic sonority; the card's
    ``chord_intervals`` are the fallback. At ``chromatic_budget_permille = 0``
    this is exactly the old filter: the prefix stops at the first tone the
    scale cannot carry.
    """
    declared = ctx.chord_tone_intervals or card.chord_intervals
    return chord_pool(ctx.scale_midi, ctx.root_midi, declared, ctx.chromatic_budget_permille)


def _draw_periods(rng: SplitMix64, card: PolyPeriodCard, count: int, sample_rate: int) -> list[int]:
    """``count`` distinct periods, drawn from the card's range."""
    low = card.period_seconds_range.min * sample_rate
    high = card.period_seconds_range.max * sample_rate
    periods: list[int] = []
    while len(periods) < count:
        candidate = rng.between(low, high)
        if candidate not in periods:
            periods.append(candidate)
    return periods


def _fit_density(ons: list[int], periods: list[int], phases: list[int], duration_frames: int) -> list[int]:
    """Pull the on-windows toward the density band, once, in the same direction.

    The band is a declaration the card makes; this is the one correction
    step. A plan that is still outside the band after it is a plan the
    composer refuses, not one it quietly accepts.
    """
    density = _density(periods, ons, phases, duration_frames)
    if density > DENSITY_MAX:
        scale = (DENSITY_MAX * 0.9) / density
    elif density < DENSITY_MIN:
        scale = (DENSITY_MIN * 1.1) / density
    else:
        return ons
    return [max(1, min(period, int(on * scale))) for on, period in zip(ons, periods, strict=True)]


def plan_poly_period(card: PolyPeriodCard, rng: SplitMix64, ctx: TechniqueContext) -> list[PolyPeriodEvent]:
    """Draw the voices of one poly-period loop.

    The card is a ``PolyPeriodCard``. The chord's usable tones come first:
    the voices take the chord's intervals in order, so the offsets are a
    prefix of the declared list rather than a cycle of it, and the voice
    count is capped by how many tones the scale can actually carry.
    """
    intervals = _usable_intervals(card, ctx)
    voice_count = min(rng.between(card.voice_count.min, card.voice_count.max), len(intervals))
    if voice_count < 3:
        raise PlanError(
            f"poly-period chord has only {voice_count} usable tones",
            preset=ctx.preset,
            seed=ctx.seed,
        )

    periods = _draw_periods(rng, card, voice_count, ctx.sample_rate)

    fractions = [rng.between(card.on_fraction_permille.min, card.on_fraction_permille.max) for _ in range(voice_count)]
    phases = [rng.below(period) for period in periods]
    phases[0] = 0  # the gate-8 safety rule: a voice is present from the first frame

    ons = [max(1, period * fraction // 1000) for period, fraction in zip(periods, fractions, strict=True)]
    ons = [min(on, period) for on, period in zip(ons, periods, strict=True)]

    ons = _fit_density(ons, periods, phases, ctx.duration_frames)

    density = _density(periods, ons, phases, ctx.duration_frames)
    if not DENSITY_MIN <= density <= DENSITY_MAX:
        raise PlanError(
            f"poly-period density {density:.3f} is outside [{DENSITY_MIN}, {DENSITY_MAX}]",
            preset=ctx.preset,
            seed=ctx.seed,
        )

    pitches: list[int] = []
    for index in range(voice_count):
        # The voices take the chord's intervals in order, so the offsets are a
        # prefix of the declared list rather than a cycle of it.
        pitches.append(ctx.root_midi + intervals[index])

    while _minor_second_pairs(pitches) > 1:
        pitches.pop()

    if not pitches:
        raise PlanError("poly-period chord has no voices left", preset=ctx.preset, seed=ctx.seed)

    partials = [Partial(ratio=ratio, amplitude_millibels=-300, detune_cents=0) for ratio in card.partial_ratios]
    voices = [
        PolyPeriodVoice(period_frames=period, on_frames=on, phase_frames=phase, midi=pitch)
        for period, on, phase, pitch in zip(periods, ons, phases, pitches, strict=True)
    ]
    event = PolyPeriodEvent(
        kind="poly_period",
        instrument="poly_period",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=pitches[0],
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=ctx.attack_frames,
        release_frames=ctx.release_frames,
        voices=voices,
        partials=partials,
    )
    return [event]
