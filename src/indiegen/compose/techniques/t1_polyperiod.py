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


def plan_poly_period(card: PolyPeriodCard, rng: SplitMix64, ctx: TechniqueContext) -> list[PolyPeriodEvent]:
    """Draw the voices of one poly-period loop.

    The card is a ``PolyPeriodCard``; it is typed as ``object`` here so that
    this module does not import the preset models, which live one layer up.
    """
    voice_count = rng.between(card.voice_count.min, card.voice_count.max)
    low = card.period_seconds_range.min * ctx.sample_rate
    high = card.period_seconds_range.max * ctx.sample_rate

    periods: list[int] = []
    while len(periods) < voice_count:
        candidate = rng.between(low, high)
        if candidate not in periods:
            periods.append(candidate)

    fractions = [rng.between(card.on_fraction_permille.min, card.on_fraction_permille.max) for _ in range(voice_count)]
    phases = [rng.below(period) for period in periods]
    phases[0] = 0  # the gate-8 safety rule: a voice is present from the first frame

    ons = [max(1, period * fraction // 1000) for period, fraction in zip(periods, fractions, strict=True)]
    ons = [min(on, period) for on, period in zip(ons, periods, strict=True)]

    density = _density(periods, ons, phases, ctx.duration_frames)
    if density > DENSITY_MAX:
        scale = (DENSITY_MAX * 0.9) / density
        ons = [max(1, min(period, int(on * scale))) for on, period in zip(ons, periods, strict=True)]
    elif density < DENSITY_MIN:
        scale = (DENSITY_MIN * 1.1) / density
        ons = [max(1, min(period, int(on * scale))) for on, period in zip(ons, periods, strict=True)]

    density = _density(periods, ons, phases, ctx.duration_frames)
    if not DENSITY_MIN <= density <= DENSITY_MAX:
        raise PlanError(
            f"poly-period density {density:.3f} is outside [{DENSITY_MIN}, {DENSITY_MAX}]",
            preset=ctx.preset,
            seed=ctx.seed,
        )

    intervals: list[int] = []
    for interval in card.chord_intervals:
        if ctx.root_midi + interval in ctx.scale_midi:
            intervals.append(interval)
        else:
            break
    if not intervals:
        intervals = [0]

    pitches: list[int] = []
    for index in range(voice_count):
        interval = intervals[index % len(intervals)]
        pitches.append(ctx.root_midi + interval)

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
