"""T10: the dub chain - the bit reduction, the bandpass and the drift."""

from __future__ import annotations

import numpy as np

from indiegen.control import (
    CONTROL_RATE,
    uniform_stream,
)
from indiegen.fx.dub import bit_reduce, drift_signal, dub_chain_state, render_dub_chain
from indiegen.plan import DubChainSpec

RATE: int = 44100


def _spec(**overrides: int) -> DubChainSpec:
    """The shipped dub chain, with the fields a test wants to change."""
    fields: dict[str, int] = {
        "bit_depth": 16,
        "bandpass_hz": 450,
        "bandpass_q_num": 2,
        "bandpass_q_den": 1,
        "drift_depth_hz": 0,
        "drift_seed": 11,
        "send_millibels": 0,
        "sidechain_depth_millibels": 0,
        "sidechain_release_frames": 1,
    }
    fields.update(overrides)
    return DubChainSpec(**fields)


def _white(count: int, seed: int = 3) -> np.ndarray:
    """White noise on two channels, from the project's counter-based mixer."""
    left = uniform_stream(seed, 0, 0, count)
    right = uniform_stream(seed, 1, 0, count)
    return np.stack([left, right], axis=1)


def _centroid(signal: np.ndarray) -> float:
    """The spectral centroid of one channel, over a Hann window."""
    window = np.hanning(signal.size)
    power = np.abs(np.fft.rfft(signal * window)) ** 2
    frequencies = np.fft.rfftfreq(signal.size, 1.0 / RATE)
    return float((frequencies * power).sum() / power.sum())


def _windowed_centroids(wet: np.ndarray, window: int = RATE) -> np.ndarray:
    """The centroid of every window of the signal."""
    return np.array(
        [_centroid(wet[start : start + window, 0]) for start in range(0, wet.shape[0] - window + 1, window)]
    )


def _best_sine_fit(signal: np.ndarray, rate: float, top_hz: float) -> float:
    """The fraction of the variance a single sinusoid can explain.

    The sinusoid is allowed to be at any frequency and any phase, so a
    signal that is one sine - or a sine plus a constant - scores one.
    """
    centred = signal - float(signal.mean())
    count = centred.size
    times = np.arange(count, dtype=np.float64) / rate
    variance = float(centred.var())
    best = 0.0
    for frequency in np.arange(0.02, top_hz, 0.05):
        sine = float(centred @ np.sin(2.0 * np.pi * frequency * times))
        cosine = float(centred @ np.cos(2.0 * np.pi * frequency * times))
        best = max(best, 2.0 * (sine * sine + cosine * cosine) / (count * count * variance))
    return best


def _participation(signal: np.ndarray) -> float:
    """How many bins the energy of the signal is spread over.

    A sine puts its energy in three bins, so it scores about two. A 1/f
    signal spreads it over hundreds.
    """
    power = np.abs(np.fft.rfft(signal * np.hanning(signal.size))) ** 2
    return float(power.sum() ** 2 / (power**2).sum())


def test_the_bit_reduction_snaps_the_samples_to_the_grid() -> None:
    """Eight bits is a staircase of 1/128, and a constant stays a constant.

    The grid is checked on the quantiser and not on the chain's output: the
    bandpass takes the staircase away again, and what is left is the sound.
    """
    ramp = np.linspace(-1.0, 1.0, 256, endpoint=False)
    reduced = bit_reduce(ramp, 8)
    assert np.unique(reduced).size <= 256
    assert np.all(reduced * 128.0 == np.round(reduced * 128.0))

    constant = np.full((64, 2), 0.5)
    flat = bit_reduce(constant, 8)
    assert np.all(flat == 0.5)
    assert np.unique(flat).size == 1


def test_the_bit_reduction_runs_before_the_bandpass() -> None:
    """The quantiser is the first stage: the dry stabs are the ones reduced."""
    spec = _spec(bit_depth=8)
    steps = np.linspace(-1.0, 1.0, 256, endpoint=False)
    block = np.stack([steps, steps], axis=1)
    reduced = bit_reduce(block, 8)
    assert np.unique(reduced[:, 0]).size <= 256
    assert np.all(reduced * 128.0 == np.round(reduced * 128.0))

    wet, _ = render_dub_chain(block, dub_chain_state(spec, RATE), spec, RATE)
    assert wet.shape == block.shape
    # The wet is the bandpassed dry, not the dry: the quantiser's staircase
    # is still the staircase, but the band has taken the rest of it away.
    assert not np.array_equal(wet, block)
    assert float(np.max(np.abs(wet))) < float(np.max(np.abs(block)))


def test_the_bandpass_sits_on_the_declared_centre() -> None:
    """White noise through the chain comes out around the declared centre."""
    spec = _spec(drift_depth_hz=0)
    noise = _white(RATE * 4)
    wet, _ = render_dub_chain(noise, dub_chain_state(spec, RATE), spec, RATE)
    measured = _centroid(wet[:, 0])
    low = 0.4 * spec.bandpass_hz
    high = 1.6 * spec.bandpass_hz
    assert low <= measured <= high, f"centroid {measured:.1f}Hz outside the band {low:.0f}-{high:.0f}Hz"
    assert spec.bandpass_hz / 2.0 <= measured <= spec.bandpass_hz * 2.0


def test_the_bandpass_is_twelve_decibels_an_octave() -> None:
    """Two second-order sections in series: the state carries two of them."""
    spec = _spec(drift_depth_hz=0)
    state = dub_chain_state(spec, RATE)
    assert state.sos.shape == (2, 6)
    assert state.zi[0].shape == (2, 2)


def test_the_drift_is_not_a_sine() -> None:
    """The cutoff wanders on 1/f: no single sinusoid explains the drift."""
    spec = _spec(drift_depth_hz=500)
    drift = drift_signal(spec, RATE, RATE * 5)
    control = drift[:: RATE // CONTROL_RATE]
    assert float(drift.std()) > 0.05
    assert _best_sine_fit(control, CONTROL_RATE, 40.0) < 0.2
    assert _participation(control) > 50.0


def test_the_drift_moves_the_cutoff() -> None:
    """The cutoff moves with the drift, and it does not move on a short cycle."""
    spec = _spec(drift_depth_hz=500)
    noise = _white(RATE * 8)
    state = dub_chain_state(spec, RATE)
    track: list[np.ndarray] = []
    for start in range(0, noise.shape[0], CONTROL_RATE):
        _, state = render_dub_chain(noise[start : start + CONTROL_RATE], state, spec, RATE)
        track.append(state.sos.copy())
    assert len({sos.tobytes() for sos in track}) >= len(track) * 0.9

    drift = drift_signal(spec, RATE, noise.shape[0])
    centres = spec.bandpass_hz + spec.drift_depth_hz * drift[::CONTROL_RATE]
    assert float(centres.std()) > 10.0
    assert _best_sine_fit(centres, RATE / CONTROL_RATE, 5.0) < 0.3


def test_the_cutoff_stays_put_without_a_drift() -> None:
    """With no depth declared, the band is the same band all the way through."""
    spec = _spec(drift_depth_hz=0)
    noise = _white(RATE * 4)
    state = dub_chain_state(spec, RATE)
    track: list[np.ndarray] = []
    for start in range(0, noise.shape[0], CONTROL_RATE):
        _, state = render_dub_chain(noise[start : start + CONTROL_RATE], state, spec, RATE)
        track.append(state.sos.copy())
    assert len({sos.tobytes() for sos in track}) == 1


def test_the_drift_is_heard_in_the_output() -> None:
    """The drifting band and the fixed band are not the same sound."""
    noise = _white(RATE * 20)
    still = _spec(drift_depth_hz=0)
    moving = _spec(drift_depth_hz=500)
    fixed, _ = render_dub_chain(noise, dub_chain_state(still, RATE), still, RATE)
    drifted, _ = render_dub_chain(noise, dub_chain_state(moving, RATE), moving, RATE)
    assert not np.array_equal(fixed, drifted)
    fixed_centroids = _windowed_centroids(fixed)
    drifted_centroids = _windowed_centroids(drifted)
    assert abs(float(drifted_centroids.mean()) - float(fixed_centroids.mean())) > 1.0
    assert float(drifted_centroids.std()) > 2.0 * float(fixed_centroids.std())
    assert float(drifted_centroids.max() - drifted_centroids.min()) > 2.0 * float(
        fixed_centroids.max() - fixed_centroids.min()
    )


def test_a_block_wise_render_is_bit_identical_to_a_single_shot() -> None:
    """The invariant: the same signal, the same bytes, whatever the blocks."""
    spec = _spec(bit_depth=8, drift_depth_hz=500)
    noise = _white(20000)
    whole, _ = render_dub_chain(noise, dub_chain_state(spec, RATE), spec, RATE)
    state = dub_chain_state(spec, RATE)
    pieces: list[np.ndarray] = []
    for start in range(0, noise.shape[0], 3333):
        piece, state = render_dub_chain(noise[start : start + 3333], state, spec, RATE)
        pieces.append(piece)
    assert np.array_equal(whole, np.concatenate(pieces))


def test_the_same_block_twice_from_the_same_state_is_identical() -> None:
    spec = _spec(drift_depth_hz=500)
    block = _white(4096)
    state = dub_chain_state(spec, RATE)
    first, _ = render_dub_chain(block, state, spec, RATE)
    second, _ = render_dub_chain(block, state, spec, RATE)
    assert np.array_equal(first, second)


def test_the_state_is_a_value() -> None:
    """Two states share no buffer, and rendering does not touch the state."""
    spec = _spec(drift_depth_hz=500)
    one = dub_chain_state(spec, RATE)
    other = dub_chain_state(spec, RATE)
    assert one.sos is not other.sos
    assert one.zi[0] is not other.zi[0]

    before = one.sos.copy()
    render_dub_chain(_white(1024), one, spec, RATE)
    assert np.array_equal(before, one.sos)

    one.zi[0][0, 0] = 1.0
    assert other.zi[0][0, 0] == 0.0


def test_the_chain_does_not_blow_up() -> None:
    """A full-scale input stays finite, and the chain does not amplify it.

    The band is a resonator with unit gain at its centre and less everywhere
    else, so full-scale noise comes out at 0.44 of the input's peak and
    never above the input.

    A full-scale sine at the centre is the worst case: the cutoff moves
    under it, the filter's state is briefly out of step with the new
    coefficients, and the resonance rings past unity. Measured at 1.44 with
    a drift of five hundred hertz, and at 1.08 without one.
    """
    spec = _spec(bit_depth=16, drift_depth_hz=500)
    loud = _white(RATE * 8) * 2.0
    wet, _ = render_dub_chain(loud, dub_chain_state(spec, RATE), spec, RATE)
    assert bool(np.all(np.isfinite(wet)))
    assert float(np.max(np.abs(wet))) <= 1.0

    times = np.arange(RATE * 4, dtype=np.float64) / RATE
    tone = np.stack([np.sin(2.0 * np.pi * 450.0 * times)] * 2, axis=1)
    ringing, _ = render_dub_chain(tone, dub_chain_state(spec, RATE), spec, RATE)
    assert bool(np.all(np.isfinite(ringing)))
    assert float(np.max(np.abs(ringing))) <= 1.5

    still = _spec(bit_depth=16, drift_depth_hz=0)
    quiet, _ = render_dub_chain(tone, dub_chain_state(still, RATE), still, RATE)
    assert float(np.max(np.abs(quiet))) <= 1.1
