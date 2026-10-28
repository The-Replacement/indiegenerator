"""Tension: the section-level reduction of Farbood's parametric model.

Farbood (2012) predicts perceived tension from a WEIGHTED SUM OF FEATURE
SLOPES, integrated over an attentional window and a memory window, with
beta = 5 when the memory window's slope agrees with the attentional window's.
TenseMusic (Barchet, Rimmele & Pelofi, PLoS ONE 2024) refits the weights and
z-standardises the features; its ordering is loudness highest, then pitch,
roughness and tonal tension, then tempo, with onset frequency small and
negative.

This module is the reduction the Plan can carry: one attentional window per
SECTION, the previous section as the memory window, four features z-scored
against constants measured on this corpus (5 lanes x 3 seeds x 6 durations,
424 sections), and the weighted step added to a running tension in permille.

The actuator is the section's LEVEL. Material alone moves the step by about
30 permille (measured: onset 16, pitch 11, roughness 4), while the graph's
paths span up to 300, so a corridor could not be both meaningful and
reachable. The section gain is the loudness term - Farbood's strongest - and
trimming it inside a declared budget is what lets a corridor bind. The trim
is bounded by TENSION_TRIM_MILLIBELS, so a corridor can still be out of
reach: that is a PlanError, not a widened band.

The declared deviation: Farbood's windows are 3 s / 3-4 s and his integration
is continuous; this is a section walk, and the weights are this corpus's
calibration ordered after TenseMusic's refit, not Farbood's coefficients.
Tempo is the lane's and constant inside a track, so its slope is identically
zero and it carries no weight.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from indiegen.errors import PlanError
from indiegen.plan import BassEvent, DroneEvent, Event, LeadEvent, PadEvent, PluckEvent, PolyPeriodEvent, RhythmEvent

# The four features and their weights, permille of 1000.
TENSION_WEIGHTS: Mapping[str, int] = MappingProxyType({"loudness": 400, "pitch": 200, "roughness": 200, "onset": 200})

# The corpus moments the features are z-scored against, in the model's
# integer units (millibels, milli-onsets per bar, centi-MIDI, milli-roughness).
# Measured 2026-10-27 over 424 sections; re-derive with the harness in the
# handoff if the material changes.
TENSION_FEATURE_STD: Mapping[str, int] = MappingProxyType(
    {"loudness": 3637, "onset": 6660, "pitch": 905, "roughness": 2295}
)

# Where a walk starts and how far one section may move it.
TENSION_START: int = 500
TENSION_BETA: int = 5
TENSION_STEP_DIVISOR: int = 2
TENSION_STEP_SCALE: int = 1000

# The actuator's bounds. A section's level may move by at most three
# decibels from the graph's declaration, in tenths of a decibel.
TENSION_TRIM_MILLIBELS: int = 3000
TENSION_TRIM_STEP_MILLIBELS: int = 100
TENSION_LEVEL_FLOOR: int = -30000
TENSION_LEVEL_CEILING: int = -1000

# Interval-class sensory-dissonance weights (minor 2nd and major 7th worst).
ROUGHNESS_WEIGHTS: tuple[int, ...] = (0, 10, 6, 3, 2, 1, 6, 1, 2, 3, 6, 10)

# The roughness is sampled at this many instants inside a section and meaned;
# one instant can miss the material a section is built around.
ROUGHNESS_SAMPLES: int = 7

# The BassHit carries no length; the bass card's decay is the horizon a
# sustained pitch is heard over, and it is the value the calibration used.
BASS_HIT_FRAMES: int = 7000


@dataclass(frozen=True)
class FeatureSet:
    """The four features of one section, in the model's integer units."""

    loudness: int
    onset: int
    pitch: int
    roughness: int


def pitched_notes(events: Sequence[Event]) -> list[tuple[int, int, int]]:
    """(start, stop, midi) for every pitched event, bass hits included.

    A drone enters as ONE note at its segment root, not one per partial. Its
    partials are near-unison members of a JI stack, and the roughness table
    below is an interval-class model: reading 16 near-unison partials as 16
    notes would turn it into a beating model it is not. The root is the modal
    root, so a modal shift reaches the model through the same field the pad
    uses.
    """
    out: list[tuple[int, int, int]] = []
    for event in events:
        if isinstance(event, (PluckEvent, PadEvent, LeadEvent, DroneEvent)):
            out.append((event.start_frame, event.start_frame + event.duration_frames, event.midi))
        elif isinstance(event, PolyPeriodEvent):
            out.extend(
                (event.start_frame, event.start_frame + event.duration_frames, voice.midi) for voice in event.voices
            )
        elif isinstance(event, RhythmEvent):
            out.extend(
                (hit.frame, hit.frame + BASS_HIT_FRAMES, hit.midi) for hit in event.hits if isinstance(hit, BassEvent)
            )
    return out


def _roughness_at(pitched: Sequence[tuple[int, int, int]], frame: int) -> float | None:
    sounding = [midi for start, stop, midi in pitched if start <= frame < stop]
    if len(sounding) < 2:
        return None
    weights = [
        ROUGHNESS_WEIGHTS[abs(first - second) % 12]
        for index, first in enumerate(sounding)
        for second in sounding[index + 1 :]
    ]
    return sum(weights) / len(weights)


def section_features(
    events: Sequence[Event],
    start: int,
    stop: int,
    bars: int,
    level_millibels: int,
    pitched: Sequence[tuple[int, int, int]] | None = None,
) -> FeatureSet:
    """The four features of one section, from the material inside it."""
    if stop <= start:
        raise PlanError(f"tension features need a positive section window, got [{start}, {stop})")
    bars = max(1, bars)
    onsets = 0
    for event in events:
        if isinstance(event, RhythmEvent):
            onsets += sum(1 for hit in event.hits if start <= hit.frame < stop)
        elif start <= event.start_frame < stop:
            onsets += 1
    sounding = pitched if pitched is not None else pitched_notes(events)
    duration = 0
    weighted = 0
    for note_start, note_stop, midi in sounding:
        overlap = min(note_stop, stop) - max(note_start, start)
        if overlap > 0:
            duration += overlap
            weighted += midi * overlap
    rough: list[float] = []
    span = stop - start
    for index in range(1, ROUGHNESS_SAMPLES + 1):
        value = _roughness_at(sounding, start + span * index // (ROUGHNESS_SAMPLES + 1))
        if value is not None:
            rough.append(value)
    return FeatureSet(
        loudness=level_millibels,
        onset=1000 * onsets // bars,
        pitch=int(round(100 * weighted / duration)) if duration else 6000,
        roughness=int(round(1000 * sum(rough) / len(rough))) if rough else 0,
    )


def step(current: FeatureSet, previous: FeatureSet, signs: Mapping[str, int]) -> tuple[int, dict[str, int]]:
    """The tension a section spends, and the slope directions it leaves.

    ``signs`` is the memory window: the previous section's slope DIRECTIONS,
    which is all Farbood's beta needs. The returned dict is a new value, so
    a candidate level can be tried without consuming the walk's memory.
    """
    total = 0
    out: dict[str, int] = {}
    for name, weight in TENSION_WEIGHTS.items():
        delta = 100 * (getattr(current, name) - getattr(previous, name)) // TENSION_FEATURE_STD[name]
        sign = (delta > 0) - (delta < 0)
        beta = TENSION_BETA if sign and signs.get(name) == sign else 1
        out[name] = sign
        total += weight * beta * delta
    return total // (TENSION_STEP_SCALE * TENSION_STEP_DIVISOR), out


def _clamped(tension: int) -> int:
    return max(0, min(1000, tension))


def solve(
    previous: FeatureSet | None,
    previous_tension: int,
    signs: Mapping[str, int],
    material: FeatureSet,
    declared_level: int,
    low: int,
    high: int,
) -> tuple[int, int, int, dict[str, int]]:
    """The level, tension, step and slopes a section lands on.

    With no previous section there is no slope to take, so the tension is
    the walk's start and the level stays as declared. Otherwise the level is
    scanned inside the trim budget and the candidate that lands in the
    corridor and is nearest the declared level wins; when none lands, the
    candidate nearest the corridor wins, so the caller's assertion can say
    what it missed by.
    """
    if previous is None:
        return declared_level, TENSION_START, 0, dict(signs)

    low_level = max(TENSION_LEVEL_FLOOR, declared_level - TENSION_TRIM_MILLIBELS)
    high_level = min(TENSION_LEVEL_CEILING, declared_level + TENSION_TRIM_MILLIBELS)
    best: tuple[tuple[int, int, int], int, int, dict[str, int]] | None = None
    for level in range(low_level, high_level + 1, TENSION_TRIM_STEP_MILLIBELS):
        candidate = FeatureSet(loudness=level, onset=material.onset, pitch=material.pitch, roughness=material.roughness)
        delta, candidate_signs = step(candidate, previous, signs)
        inside = low <= delta <= high
        # Inside the corridor first, then nearest the declared level: a
        # deterministic order with no taste in it.
        miss = 0 if inside else min(abs(delta - low), abs(delta - high))
        key = (0 if inside else 1, miss, abs(level - declared_level))
        if best is None or key < best[0]:
            best = (key, level, delta, candidate_signs)
    if best is None:
        raise PlanError(
            f"no level candidate in [{low_level}, {high_level}] for the section's tension corridor",
        )
    _, level, delta, chosen_signs = best
    return level, _clamped(previous_tension + delta), delta, chosen_signs


def walk(
    materials: Sequence[FeatureSet],
    declared_levels: Sequence[int],
    corridors: Sequence[tuple[int, int]],
) -> tuple[list[int], list[int], list[int]]:
    """The tension curve, the per-section step, and the solved levels."""
    values: list[int] = []
    steps: list[int] = []
    levels: list[int] = []
    signs: dict[str, int] = {}
    previous: FeatureSet | None = None
    current = TENSION_START
    for material, declared, (low, high) in zip(materials, declared_levels, corridors, strict=True):
        level, current, delta, signs = solve(previous, current, signs, material, declared, low, high)
        values.append(current)
        steps.append(delta)
        levels.append(level)
        previous = FeatureSet(loudness=level, onset=material.onset, pitch=material.pitch, roughness=material.roughness)
    return values, steps, levels


def band_is_declared(min_permille: int, max_permille: int) -> bool:
    """Whether a node declares a real corridor (the default is the whole range)."""
    return min_permille > -1000 or max_permille < 1000
