"""The pad: a fundamental from the lane's scale plus partials 2..N.

Each partial carries its own integer cent detune, and a slow rational LFO
drifts that detune. The drifting frequency is integrated into a phase, so
the result is a true frequency modulation rather than a chirp.

The pad is rendered a block at a time. The phase is the sum of the drifting
frequency, so every partial carries a running total.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain
from indiegen.plan import PadEvent
from indiegen.synth.osc import cumulative_sum, midi_to_hz, sine_from_phase, zero_block, zero_carries


@dataclass(frozen=True)
class PadState:
    """The running phase of every partial."""

    carries: tuple[float, ...]


def pad_state(event: PadEvent) -> PadState:
    """The zero state of the pad."""
    return PadState(carries=zero_carries(len(event.partials)))


def render_pad_block(
    event: PadEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: PadState,
) -> tuple[np.ndarray, PadState]:
    """The pad, over the local frames ``[start, stop)``.

    If the event declares envelope segments, the partial weights are
    permuted by a vector that is a pure function of the absolute frame:
    segment boundaries are fixed by the plan, so a restart at any block
    boundary renders the same audio (the switch touches weights, never the
    phase carries).
    """
    count = stop - start
    if not event.envelope_segments:
        return _render_pad_run(event, sample_rate, start, stop, state, list(range(len(event.partials))))

    # Segment boundaries as absolute frames: delta k runs from the previous
    # boundary (the first from the event start); the last segment runs to the
    # event's end.
    boundaries: list[int] = []
    cursor = event.start_frame
    for segment in event.envelope_segments:
        cursor += segment.delta_frames
        boundaries.append(cursor)

    voice = zero_block(count)
    carries = list(state.carries)
    run_start = start
    segment_index = 0
    # Segments whose boundary already passed before this block: the last of
    # them owns run_start. Boundaries are strictly increasing (delta >= 1).
    while segment_index < len(boundaries) and boundaries[segment_index] <= run_start:
        segment_index += 1
    while run_start < stop:
        # Absolute frame where the current segment ends; past every boundary
        # the final segment runs to the block's end.
        edge = boundaries[segment_index] if segment_index < len(boundaries) else stop
        run_stop = min(stop, edge)
        if run_stop <= run_start:
            run_stop = stop
        permutation = event.envelope_segments[min(segment_index, len(event.envelope_segments) - 1)].permutation
        block, carried = _render_pad_run(
            event, sample_rate, run_start, run_stop, PadState(carries=tuple(carries)), permutation
        )
        voice[run_start - start : run_stop - start] = block
        carries = list(carried.carries)
        run_start = run_stop
        segment_index += 1
    return voice, PadState(carries=tuple(carries))


def _render_pad_run(
    event: PadEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: PadState,
    permutation: list[int],
) -> tuple[np.ndarray, PadState]:
    """The pad over ``[start, stop)`` with one weight permutation applied."""
    count = stop - start
    times = np.arange(start, stop, dtype=np.float64) / sample_rate
    rate = event.lfo_rate.numerator / event.lfo_rate.denominator
    lfo = np.sin(2.0 * np.pi * rate * times)
    base = midi_to_hz(event.midi)
    voice = zero_block(count)
    carries = list(state.carries)
    for index, partial in enumerate(event.partials):
        ratio = partial.ratio.numerator / partial.ratio.denominator
        drift = partial.detune_cents + event.lfo_depth_cents * lfo
        frequency = base * ratio * np.power(2.0, drift / 1200.0)
        phase, carries[index] = cumulative_sum(carries[index], frequency)
        weight = event.partials[permutation[index]].amplitude_millibels
        partial_amp = millibels_to_gain(weight)
        voice += partial_amp * sine_from_phase(phase, sample_rate)
    amplitude = millibels_to_gain(event.amplitude_millibels)
    return voice * amplitude, PadState(carries=tuple(carries))


def render_pad(event: PadEvent, sample_rate: int) -> np.ndarray:
    """The pad, as a mono buffer."""
    voice, _ = render_pad_block(event, sample_rate, 0, event.duration_frames, pad_state(event))
    return voice
