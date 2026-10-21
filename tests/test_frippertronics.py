"""T3: the Frippertronics loop.

A long feedback delay whose passes darken and die. Everything here is
synthetic - an impulse, a chirp, a tone. No render, no golden hash, no
random number generator: the numbers below are measured, not planted.

What the tests pin down, and what they measured:

* the wet is silent for the whole delay, and the first repeat arrives
  after it;
* the tail is still there eight delays later, at 0.045 against the first
  repeat's 0.844;
* the tail darkens: the spectral centroid of a chirp's repeat falls from
  4714 Hz at the first repeat to 3267 Hz at the fifth (4389, 3989, 3614
  in between), and a single click falls from 11025 Hz - the click itself,
  still unfiltered - to 1434 Hz;
* a block render is bit-identical to a single shot, with the wow on and
  off;
* the state is a value: two states never share a buffer;
* the wow moves the read position: the repeats arrive hundreds of samples
  early or late, and the tail's zero crossings stop being evenly spaced;
* without feedback the loop repeats nothing: the impulse comes back once,
  at the delay, and never again.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from indiegen.fx.frippertronics import frippertronics_state, render_frippertronics, wow_span
from indiegen.plan import FrippertronicsSpec, Rational

RATE: int = 44100
DELAY: int = 4410  # a tenth of a second: a delay, and short enough to render

SPEC: FrippertronicsSpec = FrippertronicsSpec(
    delay_frames=DELAY,
    feedback_permille=900,
    cutoff_start_hz=4000,
    cutoff_step_hz=200,
    cutoff_floor_hz=200,
    saturation_permille=300,
    wow_depth_permille=0,
    wow_rate=Rational(numerator=1, denominator=2),
    send_millibels=0,
)


def _chirp(samples: int, f0: float, f1: float) -> np.ndarray:
    """A linear sweep, so the tail has something to lose."""
    t = np.arange(samples) / RATE
    return np.sin(2.0 * math.pi * (f0 * t + 0.5 * (f1 - f0) / (samples / RATE) * t * t))


def _centroid(window: np.ndarray) -> float:
    """The spectral centroid of a window, in hertz."""
    spectrum = np.abs(np.fft.rfft(window * np.hanning(window.size)))
    freqs = np.fft.rfftfreq(window.size, 1.0 / RATE)
    return float(np.sum(freqs * spectrum) / np.sum(spectrum))


def _crossings(signal: np.ndarray) -> np.ndarray:
    """The distances between the zero crossings of a signal."""
    sign = np.signbit(signal)
    return np.diff(np.nonzero(sign[1:] != sign[:-1])[0]).astype(float)


def _arrival(wet: np.ndarray, period: int) -> int:
    """Where the loudest sample of a repeat lands, counted from the delay."""
    window = wet[period * DELAY : (period + 1) * DELAY, 0]
    return int(np.argmax(np.abs(window)))


def _impulse(frames: int) -> np.ndarray:
    """A single click in the left channel."""
    signal = np.zeros((frames, 2), dtype=np.float64)
    signal[0, 0] = 1.0
    return signal


def test_the_wet_is_silent_until_the_delay() -> None:
    """There is no zero-delay path: the loop is a delay before it is a loop."""
    wet, _ = render_frippertronics(np.ones((DELAY * 4, 2)), frippertronics_state(SPEC), SPEC, RATE)
    assert np.all(wet[:DELAY] == 0.0)
    assert np.any(wet[DELAY:] != 0.0)


def test_the_tail_is_still_there_after_eight_delays() -> None:
    """A click fed into a nine-hundred-permille loop keeps coming back."""
    wet, _ = render_frippertronics(_impulse(DELAY * 9), frippertronics_state(SPEC), SPEC, RATE)
    levels = [float(np.max(np.abs(wet[period * DELAY : (period + 1) * DELAY, 0]))) for period in range(1, 9)]
    assert levels[0] > 0.5
    assert levels[-1] > 1e-3
    assert levels[-1] < levels[0]


def test_the_tail_darkens_with_every_pass() -> None:
    """The fifth repeat is darker than the first.

    Measured on a 20 ms chirp from 200 Hz to 8 kHz, over a 1024-sample
    window: 4714 Hz at the first repeat, then 4389, 3989, 3614 and 3267
    Hz at the fifth. The first repeat is the dry chirp; the fifth has been
    through the falling lowpass four times, and the lowpass is what takes
    the top off.

    The same thing on a single click: 11025 Hz at the first repeat - the
    click, still unfiltered - and 1434 Hz at the fifth.
    """
    chirp = _chirp(int(RATE * 0.02), 200.0, 8000.0)
    signal = np.zeros((DELAY * 8, 2), dtype=np.float64)
    signal[: chirp.size, 0] = chirp
    wet, _ = render_frippertronics(signal, frippertronics_state(SPEC), SPEC, RATE)
    centroids = [_centroid(wet[period * DELAY : period * DELAY + 1024, 0]) for period in range(1, 6)]
    assert centroids[0] > 4000.0
    assert centroids[4] < centroids[0] * 0.8
    assert all(earlier > later for earlier, later in zip(centroids, centroids[1:], strict=False))

    clicked, _ = render_frippertronics(_impulse(DELAY * 8), frippertronics_state(SPEC), SPEC, RATE)
    first = _centroid(clicked[DELAY : DELAY + 1024, 0])
    fifth = _centroid(clicked[5 * DELAY : 5 * DELAY + 1024, 0])
    assert fifth < first * 0.5


@pytest.mark.parametrize("wow_depth", [0, 200])
def test_a_block_render_is_bit_identical_to_a_single_shot(wow_depth: int) -> None:
    """The project's central invariant, with the wow on and off.

    The block size is 997 and the signal is 5000 samples long, so the
    blocks do not divide the signal and the last one is a stub.
    """
    spec = SPEC.model_copy(update={"wow_depth_permille": wow_depth})
    signal = np.stack([_chirp(5000, 200.0, 4000.0), _chirp(5000, 300.0, 5000.0)], axis=1)
    whole, _ = render_frippertronics(signal, frippertronics_state(spec), spec, RATE)
    state = frippertronics_state(spec)
    pieces = []
    for start in range(0, signal.shape[0], 997):
        piece, state = render_frippertronics(signal[start : start + 997], state, spec, RATE)
        pieces.append(piece)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_state_is_a_value() -> None:
    """Two states never share a buffer, and a state is not eaten by a render."""
    first = frippertronics_state(SPEC)
    second = frippertronics_state(SPEC)
    first.buffers[0][0] = 42.0
    assert second.buffers[0][0] == 0.0

    signal = _chirp(2000, 200.0, 3000.0)[:, np.newaxis] * np.ones((1, 2))
    state = frippertronics_state(SPEC)
    _, after = render_frippertronics(signal, state, SPEC, RATE)
    after.buffers[0][0] = 42.0
    after.pass_counts[0][0] = 7
    assert state.buffers[0][0] == 0.0
    assert int(state.pass_counts[0][0]) == 0

    one, _ = render_frippertronics(signal, state, SPEC, RATE)
    two, _ = render_frippertronics(signal, state, SPEC, RATE)
    assert np.array_equal(one, two)


def test_the_wow_moves_the_read_position() -> None:
    """The repeats arrive early or late, and the tail stops being a clean tone.

    The depth is twenty per cent, a test-only exaggeration: the station's
    card asks for five permille, and that is half a per cent of the delay -
    the pitch wobble BRIEF T3 asks for. The exaggeration is what makes the
    wobble measurable on a delay of a tenth of a second.
    """
    plain = SPEC.model_copy(update={"wow_depth_permille": 0})
    wowed = SPEC.model_copy(update={"wow_depth_permille": 20000})

    wet_plain, _ = render_frippertronics(_impulse(DELAY * 8), frippertronics_state(plain), plain, RATE)
    wet_wow, _ = render_frippertronics(_impulse(DELAY * 8), frippertronics_state(wowed), wowed, RATE)
    assert not np.array_equal(wet_plain, wet_wow)
    assert float(np.max(np.abs(wet_wow))) <= 2.0
    assert float(np.max(np.abs(wet_wow - wet_plain))) <= 2.0

    plain_arrivals = [_arrival(wet_plain, period) for period in range(1, 7)]
    wow_arrivals = [_arrival(wet_wow, period) for period in range(1, 7)]
    plain_drift = max(plain_arrivals) - min(plain_arrivals)
    wow_drift = max(wow_arrivals) - min(wow_arrivals)
    # The read position may move by the span and no further in one period,
    # and the move has to be visible: the repeats do not land on the same
    # samples. The drift over six periods accumulates, because the wow is
    # slower than the delay.
    per_period = max(abs(wow_arrivals[index + 1] - wow_arrivals[index]) for index in range(len(wow_arrivals) - 1))
    assert per_period <= wow_span(wowed) + 2
    assert wow_drift > 2 * plain_drift

    tone = np.zeros((DELAY * 8, 2), dtype=np.float64)
    t = np.arange(tone.shape[0]) / RATE
    tone[:, 0] = np.sin(2.0 * math.pi * 1000.0 * t)
    tail_plain, _ = render_frippertronics(tone, frippertronics_state(plain), plain, RATE)
    tail_wow, _ = render_frippertronics(tone, frippertronics_state(wowed), wowed, RATE)
    plain_spacings = _crossings(tail_plain[DELAY:, 0])
    wow_spacings = _crossings(tail_wow[DELAY:, 0])
    assert float(wow_spacings.std()) > 4.0 * float(plain_spacings.std())


def test_without_feedback_there_is_no_tail() -> None:
    """A loop with no gain repeats nothing.

    The wet is the read, so the impulse still comes back once, at the
    delay - the loop is a delay even with the feedback at zero - but it is
    never repeated, and everything after it is exactly zero.
    """
    spec = SPEC.model_copy(update={"feedback_permille": 0})
    wet, _ = render_frippertronics(_impulse(DELAY * 4), frippertronics_state(spec), spec, RATE)
    assert np.all(wet[:DELAY] == 0.0)
    loud = np.nonzero(np.abs(wet[:, 0]) > 0.0)[0]
    assert loud.size > 0
    assert int(loud.max()) < DELAY + 4
    assert np.all(wet[DELAY + 4 :] == 0.0)
    # the click comes back whole: the two samples the interpolation splits
    # it into add up to the click, up to the wow's slow breathing.
    assert float(np.sum(np.abs(wet[DELAY : DELAY + 4, 0]))) == pytest.approx(1.0, rel=1e-3)
