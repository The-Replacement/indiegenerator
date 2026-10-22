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
pass. The read is interpolated between the two neighbouring samples of
the line, and the read position is moved by the tape wow - the delay length
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

The state is a value: coefficients in, audio and a new state out.

**The walk is vectorised.** The read position moves with the wow, so the
read is a gather and not a fixed offset - but the position of every read
is known before the loop runs, because the write position advances by one
sample at a time and the wow's phase is a function of the absolute sample
index. What made the old walk expensive was that it touched the line, the
counters and the filter one sample at a time.

Three facts make the vectorised walk exact:

* The read at sample ``t`` reads the value written at ``t - delay``, and the
  line holds more than ``delay`` samples of history, so every read in a
  chunk is older than the chunk. The chunk is therefore never longer than
  the delay, and the reads are a gather over the state as it was.
* The pass counter of a read is the counter of the line at the read
  position, and the counter only changes when the write passes that
  position: once per lap of the ring. The one-pole's coefficient is
  therefore constant over long stretches, and the filter is a run of
  ``lfilter`` calls over those stretches.
* The wow's phase is a function of the absolute sample index, so the same
  sample gets the same offset however the signal is cut into blocks.

A block-wise render is identical to a single-shot one, sample for sample.
The kosmische lane is the slowest in the project and this loop was the
whole of its cost: a second of stereo took about two tenths of a second,
so a five-minute kosmische render spent a minute and a half in it. It now
takes about a second and a half.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from indiegen.plan import FrippertronicsSpec

# The effect's own chunk. It is never longer than the delay, so the reads
# of a chunk are always older than the chunk.
CHUNK_FRAMES: int = 4096


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

    BRIEF T3 asks for a pitch wobble of 0.2 to 0.8 per cent at 0.3 to 1
    hertz. The pitch of the recirculating tone is the delay's length read
    as a rate, so the travel of the read position has to be scaled by the
    wow's own rate: the faster the wow, the shorter the travel that gives
    the same wobble. A five-per-mille wobble on a three-second line at
    0.8 hertz moves the read by about a hundred and thirty samples either
    way. The span is never zero, so the line always keeps a sample of
    travel.
    """
    rate = spec.wow_rate.numerator / spec.wow_rate.denominator
    if rate <= 0.0:
        return max(1, spec.delay_frames * spec.wow_depth_permille // 100_000)
    travel = spec.delay_frames * spec.wow_depth_permille / 100_000.0 / (2.0 * math.pi * rate)
    return max(1, int(round(travel)))


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


def _one_pole(signal: np.ndarray, coefficient: np.ndarray, carry: float) -> np.ndarray:
    """A one-pole lowpass whose coefficient changes rarely.

    The recursion is ``y[n] = y[n-1] + a * (x[n] - y[n-1])``, which is
    ``a * x[n] + (1 - a) * y[n-1]`` - the filter ``a / (1 - (1 - a) z^-1)``.
    The coefficient is the pass count's cutoff, and the pass count only
    changes when the write laps the ring, so the signal is a run of
    stretches of constant coefficient and each stretch is one ``lfilter``
    call.
    """
    out = np.empty(signal.size, dtype=np.float64)
    edges = np.flatnonzero(coefficient[1:] != coefficient[:-1]) + 1
    bounds = np.concatenate(([0], edges, [signal.size]))
    state = np.array([carry], dtype=np.float64)
    for start, stop in zip(bounds[:-1], bounds[1:], strict=True):
        value = float(coefficient[start])
        out[start:stop], state = lfilter([value], [1.0, -(1.0 - value)], signal[start:stop], zi=state)
    return out


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
    coefficients = np.asarray(_coefficients(spec, sample_rate), dtype=np.float64)
    last_coefficient = coefficients.size - 1
    chunk = max(1, min(CHUNK_FRAMES, int(spec.delay_frames)))

    buffers = [state.buffers[channel].copy() for channel in range(block.shape[1])]
    counters = [state.pass_counts[channel].copy() for channel in range(block.shape[1])]
    previous = list(state.filter_state)

    for start in range(0, count, chunk):
        stop = min(count, start + chunk)
        length = stop - start
        offset_index = np.arange(length, dtype=np.float64)

        # The wow: the phase is a function of the absolute sample index, so
        # the same sample gets the same offset however the signal is cut.
        absolute = state.sample_count + start + offset_index
        phases = (state.wow_phase + absolute * increment) % 1.0
        offsets = span * np.sin(2.0 * math.pi * rate * phases)

        # The read positions: the write position advances by one sample at a
        # time, and the wow moves the read away from it.
        write_index = (state.write_pos + start + np.arange(length)) % size
        position = write_index - delay - offsets
        first_index = np.mod(np.floor(position).astype(np.int64), size)
        fraction = position - np.floor(position)
        second_index = (first_index + 1) % size

        for channel in range(block.shape[1]):
            line = buffers[channel]
            counter = counters[channel]
            first = line[first_index]
            second = line[second_index]
            wet_sample = first + fraction * (second - first)

            passes = counter[first_index]
            coefficient = coefficients[np.minimum(passes, last_coefficient)]
            filtered = _one_pole(wet_sample, coefficient, previous[channel])
            previous[channel] = float(filtered[-1])
            shaped = filtered - softness * filtered**3
            shaped = np.clip(shaped, -1.0, 1.0)

            wet[start:stop, channel] = wet_sample
            line[write_index] = block[start:stop, channel] + gain * shaped
            counter[write_index] = passes + 1

    return wet, FrippertronicsState(
        buffers=tuple(buffers),
        pass_counts=tuple(counters),
        write_pos=(state.write_pos + count) % size,
        filter_state=tuple(previous),
        wow_phase=state.wow_phase,
        sample_count=state.sample_count + count,
    )
