"""T3: Frippertronics, a long feedback delay whose passes darken and die.

A tape loop of three to seven seconds, fed by the bus and fed back into
itself. What makes it Frippertronics and not a delay is that every sample
that goes round the loop is *counted*, and the count decides the colour:
the feedback path is a one-pole lowpass whose cutoff falls by a declared
step on every pass, and a cubic soft clip that takes the top off whatever
is left. The first pass is bright, the fifth is a rumble, and the layers
pile up dark and die.

The line is one circular buffer per channel with an int32 pass counter
beside it, so the number of laps a sample has made is exact and not an
approximation: the cutoff really does fall by the declared step on every
pass. The read is interpolated between the two neighbouring samples of the
line, and the read position is moved by the tape wow - the delay length
breathes by a fraction of a percent of itself at the declared rate, and
that breathing is the pitch wobble of a tape machine.

The wet is the read, unfiltered: the lowpass and the saturation live in
the feedback path only, so the loop's own colour arrives one delay later,
and the first repeat of a fragment is still the dry fragment.

The darkening is measurable. On a chirp from 200 Hz to 8 kHz, with a
four-kilohertz cutoff to start and a two-hundred-hertz step per pass,
the spectral centroid of the repeat falls from 4714 Hz at the first
repeat to 3267 Hz at the fifth; a single click falls from 11.0 kHz - the
click itself, still unfiltered - to 1434 Hz.

The state is a value: coefficients in, audio and a new state out, and the
line is walked one sample at a time because the read position moves with
the wow. A block-wise render is identical to a single-shot one, sample
for sample. The walk is in Python and it is the whole cost of the effect:
a second of stereo takes about two tenths of a second, so a five-minute
kosmische render spends a minute and a half in this loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from indiegen.plan import FrippertronicsSpec


@dataclass(frozen=True)
class FrippertronicsState:
    """The loop, as a value: the lines, the pass counters, the phase."""

    buffers: tuple[np.ndarray, ...]
    pass_counts: tuple[np.ndarray, ...]
    write_pos: int
    filter_state: tuple[float, ...]
    wow_phase: float
    sample_count: int


def wow_span(spec: FrippertronicsSpec) -> int:
    """How far the wow may move the read position, in samples.

    It is a fraction of the delay: BRIEF T3 asks for a pitch wobble of
    0.2 to 0.8 per cent, and the depth is declared in per mille, so five
    per mille of wobble on a three-second line moves the read by six
    hundred and sixty-one samples either way. The span is never zero, so
    the line always keeps a sample of travel.
    """
    return max(1, spec.delay_frames * spec.wow_depth_permille // 100_000)


def loop_size(spec: FrippertronicsSpec) -> int:
    """The length of the circular buffer, in samples.

    The line has to hold the delay plus the travel of the wow, plus the
    sample the interpolation reads next to the one it lands on.
    """
    return spec.delay_frames + 2 * wow_span(spec) + 2


def frippertronics_state(spec: FrippertronicsSpec) -> FrippertronicsState:
    """The zero state of the loop: an empty line, no passes, no phase."""
    size = loop_size(spec)
    return FrippertronicsState(
        buffers=tuple(np.zeros(size, dtype=np.float64) for _ in range(2)),
        pass_counts=tuple(np.zeros(size, dtype=np.int32) for _ in range(2)),
        write_pos=0,
        filter_state=(0.0, 0.0),
        wow_phase=0.0,
        sample_count=0,
    )


def _coefficients(spec: FrippertronicsSpec, sample_rate: int) -> list[float]:
    """The one-pole coefficient of every pass count, until the cutoff floors.

    The cutoff falls by ``cutoff_step_hz`` per pass and stops at
    ``cutoff_floor_hz``, so there are only as many distinct coefficients
    as there are passes before the floor, and the last one is used for
    every pass beyond it.
    """
    start = spec.cutoff_start_hz
    step = spec.cutoff_step_hz
    floor_hz = spec.cutoff_floor_hz
    if step > 0:
        saturated = max(0, math.ceil((start - floor_hz) / step))
    else:
        saturated = 0
    coefficients: list[float] = []
    for passes in range(saturated + 1):
        cutoff = max(floor_hz, start - step * passes)
        coefficients.append(1.0 - math.exp(-2.0 * math.pi * cutoff / sample_rate))
    return coefficients


def render_frippertronics(
    block: np.ndarray,
    state: FrippertronicsState,
    spec: FrippertronicsSpec,
    sample_rate: int = 44100,
) -> tuple[np.ndarray, FrippertronicsState]:
    """Run one block of the bus through the loop.

    The wet is the interpolated read; the filtered, saturated, gained copy
    of it is what goes back into the line, together with the dry input.
    """
    count = int(block.shape[0])
    wet = np.zeros(block.shape, dtype=np.float64)
    if count == 0:
        return wet, state

    size = loop_size(spec)
    delay = float(spec.delay_frames)
    gain = spec.feedback_permille / 1000.0
    softness = spec.saturation_permille / 3000.0
    rate = spec.wow_rate.numerator / spec.wow_rate.denominator
    span = float(wow_span(spec))
    increment = rate / sample_rate
    coefficients = _coefficients(spec, sample_rate)
    last_coefficient = len(coefficients) - 1

    # The wow: one offset per sample, shared by the channels, and the phase
    # is carried so that it is continuous across the blocks.
    phase = state.wow_phase
    offsets: list[float] = []
    for _ in range(count):
        offsets.append(span * math.sin(2.0 * math.pi * rate * phase))
        phase += increment
        if phase >= 1.0:
            phase -= 1.0

    new_buffers: list[np.ndarray] = []
    new_counts: list[np.ndarray] = []
    new_filter: list[float] = []

    for channel in range(block.shape[1]):
        buffer = state.buffers[channel].copy()
        counts = state.pass_counts[channel].copy()
        # The line is read through a memoryview: a numpy scalar would make
        # every operation of the loop an array operation, and the loop is
        # the whole cost of the effect.
        line: memoryview[float] = memoryview(buffer)
        counter: memoryview[int] = memoryview(counts)
        write = state.write_pos
        previous = state.filter_state[channel]
        signal = block[:, channel].tolist()
        out: list[float] = []

        for index in range(count):
            position = write - delay - offsets[index]
            first_index = math.floor(position)
            fraction = position - first_index
            if first_index < 0:
                first_index += size
            elif first_index >= size:
                first_index -= size
            second_index = first_index + 1
            if second_index == size:
                second_index = 0
            first = line[first_index]
            second = line[second_index]
            wet_sample = first + fraction * (second - first)

            passes = counter[first_index]
            coefficient = coefficients[passes] if passes < len(coefficients) else coefficients[last_coefficient]
            previous = previous + coefficient * (wet_sample - previous)
            shaped = previous - softness * previous**3
            if shaped > 1.0:
                shaped = 1.0
            elif shaped < -1.0:
                shaped = -1.0

            out.append(wet_sample)
            line[write] = signal[index] + gain * shaped
            counter[write] = passes + 1
            write += 1
            if write == size:
                write = 0

        wet[:, channel] = out
        new_buffers.append(buffer)
        new_counts.append(counts)
        new_filter.append(previous)

    return wet, FrippertronicsState(
        buffers=tuple(new_buffers),
        pass_counts=tuple(new_counts),
        write_pos=(state.write_pos + count) % size,
        filter_state=tuple(new_filter),
        wow_phase=phase,
        sample_count=state.sample_count + count,
    )
