"""T2 - Reich phasing: a phased pair of the same cell.

Two voices share one cell (one pitch, one partial set). The second voice's
period is the first's scaled by ``ratio(n, n+k)`` (i.e. ``n/(n+k)``), so
the two drift and re-enter unison at the integer convergence points the
plan already schedules. The event is a ``PolyPeriodEvent``: the render path
is unchanged (S0 frozen) and no new dispatch branch is needed.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.compose.techniques.t1_polyperiod import (
    _density,
    _usable_intervals,
)
from indiegen.config import PhasedPairCard, RangeInt
from indiegen.errors import PlanError
from indiegen.plan import Partial, PolyPeriodEvent, PolyPeriodVoice

DENSITY_MIN: float = 0.5
DENSITY_MAX: float = 2.0


def _first_range(card: PhasedPairCard, *attrs: str) -> RangeInt | None:
    for attr in attrs:
        value = getattr(card, attr, None)
        if value is not None:
            return value  # type: ignore[no-any-return]
    return None


def _effective_ratio(card: PhasedPairCard) -> tuple[int, int]:
    """The combined (numerator, denominator) of every ratio representation."""
    n = card.n if card.n != 0 else 1
    k = card.k
    if n + k <= 0:
        k = 0
    ratio_n = card.ratio_n if card.ratio_n != 0 else 1
    ratio_k = card.ratio_k
    if ratio_n + ratio_k <= 0:
        ratio_k = 0
    numerator = card.numerator if card.numerator != 0 else 1
    denominator = card.denominator if card.denominator != 0 else 1

    num = card.ratio.numerator * n * ratio_n * numerator
    den = card.ratio.denominator * (n + k) * (ratio_n + ratio_k) * denominator
    if num <= 0:
        num = 1
    if den <= 0:
        den = 1
    return num, den


def plan_phased_pair(card: PhasedPairCard, rng: SplitMix64, ctx: TechniqueContext) -> list[PolyPeriodEvent]:  # noqa: C901
    """Draw one phased pair: same cell, two periods related by n/(n+k)."""
    intervals = _usable_intervals(card, ctx)  # type: ignore[arg-type]
    if not intervals:
        intervals = [0]

    pitch = ctx.root_midi + intervals[0]

    period_range = _first_range(card, "period_seconds_range", "cell_seconds_range", "period_range", "cell_range")
    if period_range is None:
        period_range = _first_range(card, "period_seconds_range")
    if period_range is None:
        from indiegen.config import RangeInt

        period_range = RangeInt(min=1, max=2)

    card_low = period_range.min * ctx.sample_rate
    card_high = period_range.max * ctx.sample_rate
    shortest_section_frames = ctx.duration_frames
    boundaries = ctx.section_boundaries or []
    if len(boundaries) >= 2:
        lengths = [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]
        positive = [length for length in lengths if length > 0]
        if positive:
            shortest_section_frames = min(positive)

    capped_high = min(card_high, shortest_section_frames)
    if capped_high < card_low:
        high = max(capped_high, ctx.sample_rate)
        low = ctx.sample_rate
    else:
        high = capped_high
        low = min(card_low, high)
        if low < ctx.sample_rate:
            low = ctx.sample_rate
        if low > high:
            low = high
    if high < low:
        low, high = high, low
    if low < 1:
        low = 1
    if high < low:
        high = low

    period = rng.between(low, high)

    on_range = _first_range(card, "on_fraction_permille", "on_fraction")
    if on_range is None:
        from indiegen.config import RangeInt

        on_range = RangeInt(min=1000, max=1000)
    fraction = rng.between(on_range.min, on_range.max)
    on = max(1, period * fraction // 1000)
    on = min(on, period)

    num, den = _effective_ratio(card)
    second_period = max(1, period * num // den)
    second_on = max(1, second_period * fraction // 1000)
    second_on = min(second_on, second_period)

    phases = [0, 0]

    ons = [on, second_on]
    periods = [period, second_period]
    density = _density(periods, ons, phases, ctx.duration_frames)
    if not DENSITY_MIN <= density <= DENSITY_MAX:
        raise PlanError(
            f"phased-pair density {density:.3f} is outside [{DENSITY_MIN}, {DENSITY_MAX}]",
            preset=ctx.preset,
            seed=ctx.seed,
        )

    partials = [Partial(ratio=ratio, amplitude_millibels=-3000, detune_cents=0) for ratio in card.partial_ratios]

    voices = [
        PolyPeriodVoice(period_frames=period, on_frames=on, phase_frames=0, midi=pitch),
        PolyPeriodVoice(period_frames=second_period, on_frames=second_on, phase_frames=0, midi=pitch),
    ]

    event = PolyPeriodEvent(
        kind="poly_period",
        instrument="poly_period",
        start_frame=0,
        duration_frames=ctx.duration_frames,
        midi=pitch,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=ctx.attack_frames,
        release_frames=ctx.release_frames,
        voices=voices,
        partials=partials,
    )
    return [event]


# Aliases for callers that name the function differently.
plan_reich_phasing = plan_phasing = plan_phased = plan_t2 = plan_phased_pair
