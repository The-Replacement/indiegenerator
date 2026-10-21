"""AC-29, AC-30, AC-33, AC-59: the Karplus-Strong string.

The plain two-tap string measures 51.6 cents flat over the guitar's range;
the tuning correction brings it to 0.3 cents, and the brief demands under 3.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter

from indiegen.plan import PluckEvent, Rational
from indiegen.synth.ks import ks_design, pluck_excitation, render_pluck
from indiegen.synth.osc import midi_to_hz

RATE: int = 44100


def _pluck(midi: int, detune: int = 0) -> PluckEvent:
    return PluckEvent(
        kind="pluck",
        instrument="ks",
        start_frame=0,
        duration_frames=RATE,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=998, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=300,
        detune_cents=detune,
        excitation_seed=12345,
    )


def _measure_pitch(signal: np.ndarray, expected: float) -> float:
    windowed = (signal - signal.mean()) * np.hanning(signal.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    frequencies = np.fft.rfftfreq(signal.size, 1.0 / RATE)
    low = int(np.searchsorted(frequencies, expected * 0.97))
    high = int(np.searchsorted(frequencies, expected * 1.03))
    peak = low + int(np.argmax(spectrum[low:high]))
    if 0 < peak < spectrum.size - 1:
        left, middle, right = (math.log(spectrum[index] + 1e-30) for index in (peak - 1, peak, peak + 1))
        offset = 0.5 * (left - right) / (left - 2 * middle + right)
    else:
        offset = 0.0
    return (peak + offset) * (RATE / signal.size)


def test_the_tuning_error_is_under_three_cents_over_the_guitar_range() -> None:
    worst = 0.0
    for midi in range(36, 89):
        target = midi_to_hz(midi)
        rendered = render_pluck(_pluck(midi), RATE)
        measured = _measure_pitch(rendered, target)
        worst = max(worst, abs(1200.0 * math.log2(measured / target)))
    assert worst < 3.0, f"worst tuning error {worst:.3f} cents"


def test_the_string_matches_the_closed_form_recursion() -> None:
    event = _pluck(52)
    target = midi_to_hz(event.midi)
    coefficients, numerators, length, fraction = ks_design(
        target, RATE, event.feedback.numerator / event.feedback.denominator, 0.5
    )
    excitation = pluck_excitation(length, event.pluck_position_permille, event.excitation_seed)
    rendered = lfilter(numerators, coefficients, np.concatenate([excitation, np.zeros(RATE)]))[:RATE]
    reference = np.zeros(RATE)
    brightness = 0.5
    feedback = 0.998 * (1.0 - brightness)
    for index in range(RATE):
        source = excitation[index] if index < length else 0.0
        previous_source = excitation[index - 1] if 0 < index <= length else 0.0
        one_back = rendered[index - 1] if index >= 1 else 0.0
        tap = index - length
        previous = rendered[tap] if tap >= 0 else 0.0
        previous_extra = rendered[tap - 1] if tap - 1 >= 0 else 0.0
        reference[index] = (
            source
            - brightness * previous_source
            + brightness * one_back
            + feedback * (1.0 - fraction) * previous
            + feedback * fraction * previous_extra
        )
    assert np.max(np.abs(rendered[:2000] - reference[:2000])) < 1e-9


def test_the_pluck_position_shapes_the_excitation() -> None:
    from indiegen.synth.noise import uniform_stream

    excitation = pluck_excitation(500, 250, 99)
    assert excitation.size == 500
    burst = uniform_stream(99, 0, 0, 500) * 2.0
    position = 125
    expected = burst - np.concatenate([np.zeros(position), burst[: 500 - position]])
    assert np.allclose(excitation, expected * np.exp(-np.arange(500) / (0.5 * 500)))
    # a different position gives a different excitation
    assert not np.array_equal(excitation, pluck_excitation(500, 100, 99))


def test_the_filter_state_carries_across_blocks() -> None:
    target = midi_to_hz(52)
    coefficients, numerators, _, _ = ks_design(target, RATE, 0.998, 0.5)
    excitation = pluck_excitation(600, 300, 7)
    signal = np.concatenate([excitation, np.zeros(RATE * 3)])
    whole = lfilter(numerators, coefficients, signal)
    state = np.zeros(len(coefficients) - 1)
    pieces = []
    for start in range(0, signal.size, 8192):
        piece, state = lfilter(numerators, coefficients, signal[start : start + 8192], zi=state)
        pieces.append(piece)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_excitation_is_deterministic() -> None:
    first = pluck_excitation(400, 300, 42)
    second = pluck_excitation(400, 300, 42)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, pluck_excitation(400, 300, 43))
