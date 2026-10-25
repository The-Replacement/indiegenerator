# mypy: disable-error-code=import-untyped
"""BRIEF §11: the two DSP unit tests the audit found missing.

Oscillator aliasing is measured as THD at fundamentals of 0.1 and 0.4 of the
sample rate; the biquads' measured frequency response is compared against the
closed-form |H(e^jw)| of their own coefficients. Every limit below was set
from a measurement taken while writing this file - the measured values are
recorded in the comments and reported in the assertion messages.

The disable-error-code line is needed only because the editable install ships
no py.typed: a standalone ``mypy tests/test_brief11_dsp.py`` resolves
``indiegen`` as an untyped library, while ``mypy .`` sees it as source.
"""

from __future__ import annotations

import math

import numpy as np

from indiegen.synth.filter import (
    BUTTERWORTH_Q_DEN,
    BUTTERWORTH_Q_NUM,
    apply_biquad,
    bandpass_sos,
    highpass_sos,
    initial_state,
    lowpass_sos,
)
from indiegen.synth.osc import cumulative_sum, sine, sine_from_phase

RATE: int = 44100

FUNDAMENTALS: tuple[int, ...] = (RATE // 10, 2 * RATE // 5)
# 0.1*fs = 4410 Hz and 0.4*fs = 17640 Hz, both exact integers so the FFT
# bins land on the tone.

# Measured worst |measured / analytic - 1| over the sweeps below: 4.3e-13
# (the bandpass at 100 Hz). 1e-9 keeps three decades of headroom over that
# roundoff floor; a real coefficient bug shows up at 1e-3 or worse.
RESPONSE_TOLERANCE: float = 1e-9

# Measured worst THD: 4.6e-12 (sine() at 0.4*fs); the phase-accumulator path
# measured 4.5e-12 - both at the np.sin/FFT roundoff floor, with the harmonic
# bins empty at 0.4*fs where any harmonic would fold back below Nyquist.
# 1e-9 is still -180 dB; a table, polynomial or fixed-point oscillator lands
# at 1e-4 or worse.
THD_LIMIT: float = 1e-9


def _analytic_gain(row: np.ndarray, frequency: int) -> float:
    """|H(e^jw)| in closed form for one biquad row ``b0 b1 b2 1 a1 a2``.

    The transfer function evaluated at z = e^jw: textbook math over the
    coefficients, a different path from the time-domain recursion that
    ``apply_biquad`` runs through scipy.
    """
    b0, b1, b2, _normaliser, a1, a2 = (float(value) for value in row)
    z = np.exp(-2j * math.pi * frequency / RATE)
    numerator = b0 + b1 * z + b2 * z * z
    denominator = 1.0 + a1 * z + a2 * z * z
    return float(abs(numerator / denominator))


def _cutoff_hz(row: np.ndarray) -> int:
    """The cutoff a section was designed at, read back from its own coefficients.

    For an RBJ section ``a1 = -2cos(w0)/(1+alpha)`` and ``a2 = (1-alpha)/(1+alpha)``,
    hence ``cos(w0) = -a1/(1+a2)``. The sweep frequencies come from here, not
    from a hand-picked list.
    """
    a1 = float(row[4])
    a2 = float(row[5])
    exact = math.acos(-a1 / (1.0 + a2)) * RATE / (2.0 * math.pi)
    assert abs(exact - round(exact)) < 1e-6, f"coefficients do not encode a whole-Hz cutoff: {exact}"
    return int(round(exact))


def _octave_sweep(cutoff: int) -> list[int]:
    """Octave multiples of a cutoff: two below, one at it, three above."""
    candidates = (cutoff // 4, cutoff // 2, cutoff, 2 * cutoff, 4 * cutoff, 8 * cutoff)
    return [frequency for frequency in candidates if 0 < frequency <= RATE // 2]


def _bandpass_sweep(low: int, high: int) -> list[int]:
    """Below the low corner, at both corners, inside the band, and above the high one."""
    candidates = (low // 4, low // 2, low, 2 * low, high, 2 * high, 4 * high)
    return [frequency for frequency in candidates if 0 < frequency <= RATE // 2]


def _measured_gain(sos: np.ndarray, frequency: int) -> float:
    """The measured steady-state gain at ``frequency``: unit sine in, amplitude out.

    The sine runs 65536 samples through ``apply_biquad`` from silence; the
    first 16384 are the transient and are dropped (the slowest pole of these
    designs decays by about e^-330 over them). What remains is projected onto
    sine and cosine over a whole number of periods, so the double-frequency
    term integrates to exactly zero and the amplitude is exact for a pure
    steady tone.
    """
    total = 65536
    discard = 16384
    time = np.arange(total, dtype=np.float64)
    drive = np.sin(2.0 * np.pi * frequency * time / RATE)
    filtered: np.ndarray = apply_biquad(sos, drive, initial_state(sos))[0]
    period = RATE // math.gcd(frequency, RATE)
    stop = discard + (total - discard) // period * period
    segment = filtered[discard:stop]
    angle = 2.0 * math.pi * frequency / RATE
    index = np.arange(discard, stop, dtype=np.float64)
    sine_sum = float(np.sum(segment * np.sin(angle * index)))
    cosine_sum = float(np.sum(segment * np.cos(angle * index)))
    return 2.0 * math.hypot(sine_sum, cosine_sum) / segment.size


def _compare_to_analytic(sos: np.ndarray, frequencies: list[int]) -> tuple[float, int, float]:
    """The worst relative error of measured vs analytic gain, its frequency, and the quietest gain."""
    worst = 0.0
    worst_at = 0
    quietest = math.inf
    for frequency in frequencies:
        analytic = 1.0
        for row in sos:
            analytic *= _analytic_gain(row, frequency)
        measured = _measured_gain(sos, frequency)
        error = abs(measured - analytic) / analytic
        quietest = min(quietest, analytic)
        if error > worst:
            worst, worst_at = error, frequency
    return worst, worst_at, quietest


def _phase_oscillator(frequency: int, count: int) -> np.ndarray:
    """The voice's oscillator: a blockwise accumulated phase through ``sine_from_phase``.

    The block size 4099 is an awkward one so the carry across the block
    boundary is exercised on the way to the measurement.
    """
    steps = np.full(count, float(frequency), dtype=np.float64)
    pieces: list[np.ndarray] = []
    carry = 0.0
    for start in range(0, count, 4099):
        values, carry = cumulative_sum(carry, steps[start : start + 4099])
        pieces.append(values)
    phase = np.concatenate(pieces)
    signal: np.ndarray = sine_from_phase(phase, RATE)
    return signal


def _thd(signal: np.ndarray, frequency: int) -> tuple[float, float]:
    """THD at ``frequency``: (total non-fundamental ratio, in-band harmonic ratio).

    A periodic Hann window (denominator N, not N-1 - ``np.hanning``'s symmetric
    form leaks about 4e-6 into the far bins and would swamp this floor) over a
    coherent-length segment: the fundamental owns bins k0-2..k0+2, the Hann
    main lobe, and everything else - harmonics below Nyquist, folded-back
    aliases, quantisation junk - is measured against it.
    """
    size = signal.size
    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(size, dtype=np.float64) / size)
    spectrum = np.abs(np.fft.rfft(signal * window)) ** 2
    centre = frequency * size / RATE
    assert abs(centre - round(centre)) < 1e-9, f"tone at {frequency} Hz is off-bin for {size} samples"
    peak = int(round(centre))
    fundamental = np.zeros(spectrum.size, dtype=bool)
    fundamental[max(0, peak - 2) : peak + 3] = True
    harmonics = np.zeros(spectrum.size, dtype=bool)
    for harmonic in range(2, peak + 1):
        bin_index = harmonic * peak
        if bin_index > size // 2:
            break
        harmonics[bin_index - 2 : bin_index + 3] = True
    fundamental_energy = float(spectrum[fundamental].sum())
    harmonic_energy = float(spectrum[harmonics & ~fundamental].sum())
    other_energy = float(spectrum[~fundamental].sum())
    return math.sqrt(other_energy / fundamental_energy), math.sqrt(harmonic_energy / fundamental_energy)


def test_the_lowpass_matches_the_analytic_magnitude_response() -> None:
    """The measured lowpass gain equals |H(e^jw)| of its own coefficients.

    Three designs: the Butterworth, a resonant Q=4 (analytic gain 4.0 right
    at the cutoff), and the Q=1 5 kHz send the ambient preset uses. The sweep
    is octave multiples of the cutoff recovered from the coefficients, from
    two octaves below to three above - including 8 kHz at 0.0124 gain and
    20 kHz at 0.0030 gain, so the stopband is checked, not just the passband.
    """
    designs = [
        ("butterworth fc=1000", lowpass_sos(1000, BUTTERWORTH_Q_NUM, BUTTERWORTH_Q_DEN, RATE)),
        ("resonant q=4 fc=1000", lowpass_sos(1000, 4, 1, RATE)),
        ("preset q=1 fc=5000", lowpass_sos(5000, 1, 1, RATE)),
    ]
    worst = 0.0
    worst_at = 0
    quietest = math.inf
    for label, sos in designs:
        error, at, gain = _compare_to_analytic(sos, _octave_sweep(_cutoff_hz(sos[0])))
        print(f"lowpass {label}: worst relative error {error:.3e} at {at} Hz, quietest gain {gain:.6f}")
        if error > worst:
            worst, worst_at = error, at
        quietest = min(quietest, gain)
    assert quietest < 0.1, f"the sweep never reached a strongly attenuated gain: {quietest:.6f}"
    assert worst < RESPONSE_TOLERANCE, (
        f"measured vs analytic lowpass gain differs by {worst:.3e} at {worst_at} Hz "
        f"(tolerance {RESPONSE_TOLERANCE:.0e})"
    )


def test_the_highpass_matches_the_analytic_magnitude_response() -> None:
    """The measured highpass gain equals |H(e^jw)| of its own coefficients.

    The Butterworth at 300 Hz, swept two octaves below (75 Hz, analytic gain
    0.062 - the strongly attenuated point) to two octaves above.
    """
    sos: np.ndarray = highpass_sos(300, BUTTERWORTH_Q_NUM, BUTTERWORTH_Q_DEN, RATE)
    error, at, quietest = _compare_to_analytic(sos, _octave_sweep(_cutoff_hz(sos[0])))
    print(f"highpass fc=300: worst relative error {error:.3e} at {at} Hz, quietest gain {quietest:.6f}")
    assert quietest < 0.1, f"the sweep never reached a strongly attenuated gain: {quietest:.6f}"
    assert error < RESPONSE_TOLERANCE, (
        f"measured vs analytic highpass gain differs by {error:.3e} at {at} Hz (tolerance {RESPONSE_TOLERANCE:.0e})"
    )


def test_the_bandpass_matches_the_analytic_magnitude_response() -> None:
    """The measured bandpass gain equals the PRODUCT of the two sections' |H(e^jw)|.

    ``bandpass_sos`` is a highpass and a lowpass in series - the duck's own
    200..500 Hz filter. Both corners are recovered from their section's
    coefficients; the sweep runs below the band (50 Hz at 0.062 gain, the
    strongly attenuated point), through it, and four times above it.
    """
    sos: np.ndarray = bandpass_sos(200, 500, RATE)
    low = _cutoff_hz(sos[0])
    high = _cutoff_hz(sos[1])
    error, at, quietest = _compare_to_analytic(sos, _bandpass_sweep(low, high))
    print(f"bandpass {low}..{high}: worst relative error {error:.3e} at {at} Hz, quietest gain {quietest:.6f}")
    assert quietest < 0.1, f"the sweep never reached a strongly attenuated gain: {quietest:.6f}"
    assert error < RESPONSE_TOLERANCE, (
        f"measured vs analytic bandpass gain differs by {error:.3e} at {at} Hz (tolerance {RESPONSE_TOLERANCE:.0e})"
    )


def test_the_phase_accumulator_oscillator_does_not_alias_at_high_fundamentals() -> None:
    """The voice oscillator stays a pure tone at 0.1 and 0.4 of the sample rate.

    The phase accumulates blockwise (block 4099) and ``sine_from_phase``
    turns it into samples; a windowed FFT over the steady second measures
    everything that is not the fundamental. Measured while writing this
    file: THD 1.1e-12 at 4410 Hz and 4.5e-12 at 17640 Hz - the np.sin/FFT
    roundoff floor. At 0.4*fs no harmonic fits below Nyquist, so all folded
    energy would land outside the fundamental, and the harmonic bins there
    read exactly 0; at 0.1*fs the harmonics at 2-5*f0 read 6.3e-15. A sine
    table, a polynomial or a fixed-point phase would show 1e-4 or worse here.
    """
    for frequency in FUNDAMENTALS:
        steady: np.ndarray = _phase_oscillator(frequency, RATE + RATE // 10)[RATE // 10 :]
        thd, harmonic = _thd(steady, frequency)
        print(f"phase-accumulator THD at {frequency} Hz: {thd:.3e} (harmonics {harmonic:.3e})")
        assert thd < THD_LIMIT, f"THD {thd:.3e} at {frequency} Hz exceeds the {THD_LIMIT:.0e} limit"


def test_the_direct_sine_does_not_alias_at_high_fundamentals() -> None:
    """``sine()`` - the direct helper - is a pure tone at 0.1 and 0.4 of the sample rate.

    Same measurement as the phase-accumulator path, on the other oscillator
    entry point: measured 1.2e-12 at 4410 Hz and 4.7e-12 at 17640 Hz.
    """
    for frequency in FUNDAMENTALS:
        steady: np.ndarray = sine(float(frequency), RATE + RATE // 10, RATE)[RATE // 10 :]
        thd, harmonic = _thd(steady, frequency)
        print(f"direct sine THD at {frequency} Hz: {thd:.3e} (harmonics {harmonic:.3e})")
        assert thd < THD_LIMIT, f"THD {thd:.3e} at {frequency} Hz exceeds the {THD_LIMIT:.0e} limit"
