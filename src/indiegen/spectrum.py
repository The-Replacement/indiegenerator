"""The centroid a section DECLARES: a weighted mean of its additive partials.

The number this module returns is what the Plan says its own material sounds
like, not what the audio measures. It is the amplitude- and duration-weighted
centroid, in integer millihz, of every partial of every additive event that
overlaps a section window. It is:

* not gate 6's target. Gate 6's planned curve is ``centroid_hz``, which comes
  from the lane's timbre table keyed on the section's function (planner.py);
  the two are different questions and the table is not replaced here.
* not a render measurement. Nothing here reads audio, applies an envelope,
  filters, mixes or renders. A section that declares a spectrum it never lets
  through the mix still declares it.

Units: millihz, an ``int``. The smallest value a legal plan can produce is
midi 0 at ratio 1/1, which is 8176 mHz, so ``0`` is unambiguously the sentinel
for "this section declares no additive spectrum" (no pad, lead, poly_period or
drone event overlaps it). 166 of the 427 sections of the c41 corpus are exactly
this.

The frequency of a partial is the renderer's own arithmetic, three factors and
no more: ``midi_to_hz(midi) * ratio * 2 ** (detune_cents / 1200)``. The tuning
and the millibel conversion are imported rather than restated, so this module
cannot drift from what ``synth/`` will actually play.

Three omissions are declared, not bugs:

1. ``DriftingPartial``'s LFO excursions (detune and amplitude drift). The
   nominal, declared values are used. Both LFOs are symmetric and clipped, so
   the nominal value is the time mean and the excursion is a variance this
   field does not claim.
2. The poly-period duty cycle (period, on-window, phase). A poly-period event
   contributes its partials for the whole overlap, not only while a voice is
   on. That is why ambient's field is a stable ~370 Hz rather than a moving
   number.
3. ``PadEnvelopeSegment`` weight permutations. The declared base weights are
   used. No shipped preset declares ``envelope_segments``, so this is inert
   today; it is written down so it is not later rediscovered as a defect.

Summation order is fixed and documented: events in plan order, then the
``Partial`` list in declaration order, then voices in declaration order for a
poly-period event. Float64, one accumulation per term, no reordering tricks.
The leaf is ``int(round(1000 * weighted / total))`` with Python's round
(half-to-even) on the float64 quotient, so the integer is reproducible from the
formula and the summation order alone.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Final

from indiegen.errors import PlanError
from indiegen.gain import millibels_to_gain
from indiegen.plan import (
    BassEvent,
    DroneEvent,
    Event,
    LeadEvent,
    PadEvent,
    PluckEvent,
    PolyPeriodEvent,
)
from indiegen.synth.osc import midi_to_hz

# The voices whose spectrum is declared as partial ratios. A tuple, because a
# module-level mutable container is not allowed in this package (test_hygiene).
ADDITIVE: Final = (PadEvent, LeadEvent, PolyPeriodEvent, DroneEvent)


def _partial_pairs(event: Event) -> Iterator[tuple[float, int]]:
    """(frequency_hz, weight_millibels) for every partial one event declares.

    The weight is the integer SUM of the event's own level and the partial's
    offset, because millibels are a level (negative is quieter) and linear
    gains multiply: the renderer applies the event level to the whole voice and
    the partial offset inside it. ``synth/drone.py`` and ``synth/poly_period.py``
    apply only the partial offset because their event level is 0, so the sum is
    the same number there.
    """
    if isinstance(event, PadEvent | LeadEvent | DroneEvent):
        base = midi_to_hz(event.midi)
        for partial in event.partials:
            ratio = partial.ratio.numerator / partial.ratio.denominator
            yield (
                base * ratio * 2.0 ** (partial.detune_cents / 1200.0),
                (event.amplitude_millibels + partial.amplitude_millibels),
            )
    elif isinstance(event, PolyPeriodEvent):
        for voice in event.voices:
            base = midi_to_hz(voice.midi)
            for partial in event.partials:
                ratio = partial.ratio.numerator / partial.ratio.denominator
                yield (
                    base * ratio * 2.0 ** (partial.detune_cents / 1200.0),
                    (event.amplitude_millibels + partial.amplitude_millibels),
                )


def declared_centroid_millihz(events: Sequence[Event], start_frame: int, stop_frame: int) -> int:
    """The centroid of the partials the section ``[start_frame, stop_frame)`` declares.

    0 when no additive event overlaps the window. Raises :class:`PlanError` for
    a non-positive window: the reduction divides by a duration-weighted total,
    and a public function may not divide by zero. That case is unreachable from
    ``compose()`` (section boundaries strictly increase).
    """
    if stop_frame <= start_frame:
        raise PlanError(f"declared centroid needs a positive section window, got [{start_frame}, {stop_frame})")
    total = 0.0
    weighted = 0.0
    for event in events:
        if not isinstance(event, ADDITIVE):
            continue
        overlap = min(event.start_frame + event.duration_frames, stop_frame) - max(event.start_frame, start_frame)
        if overlap <= 0:
            continue
        for hz, weight_millibels in _partial_pairs(event):
            weight = millibels_to_gain(weight_millibels) * overlap
            total += weight
            weighted += hz * weight
    if total <= 0.0:
        return 0
    return int(round(1000 * weighted / total))


def modal_mixture_permille(  # noqa: C901
    events: Sequence[Event], scale: Sequence[int], start_frame: int, stop_frame: int
) -> int:
    """Fraction (permille) of pitched notes in ``[start_frame, stop_frame)`` that
    are NOT members of ``scale`` (borrowed/off-scale, i.e. modal mixture).

    Counts pitched note instances: PadEvent/LeadEvent/DroneEvent/PluckEvent each
    contribute their ``midi``; PolyPeriodEvent contributes each voice's ``midi``;
    BassEvent contributes each hit's ``midi``. Drum events (kick/snare/hat) carry
    no pitch and are ignored. An event contributes only if it overlaps the window.
    Returns 0 when there are no pitched notes or an empty scale.
    """
    if stop_frame <= start_frame:
        return 0
    scale_set = set(int(x) for x in scale)
    if not scale_set:
        return 0
    total = 0
    off = 0
    for event in events:
        overlap = min(event.start_frame + event.duration_frames, stop_frame) - max(event.start_frame, start_frame)
        if overlap <= 0:
            continue
        midis: list[int] = []
        if isinstance(event, (PadEvent, LeadEvent, DroneEvent, PluckEvent)):
            midis.append(int(event.midi))
        elif isinstance(event, PolyPeriodEvent):
            for voice in event.voices:
                midis.append(int(voice.midi))
        elif isinstance(event, BassEvent):
            for hit in event.hits:
                if start_frame <= hit.frame < stop_frame:
                    midis.append(int(hit.midi))
        else:
            continue
        for midi in midis:
            total += 1
            if midi not in scale_set:
                off += 1
    if total == 0:
        return 0
    return int(round(1000 * off / total))
