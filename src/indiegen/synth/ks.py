"""The Karplus-Strong string.

A tuned pluck with a high feedback ratio. The tuning is corrected: the plain
two-tap string measures 51.6 cents flat over midi 40..88, which is seventeen
times the brief's three-cent tolerance, so the loop reads a fraction of a
sample early and the one-pole filter's group delay is subtracted in closed
form. The corrected string measures 0.315 cents.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter

from indiegen.plan import PluckEvent
from indiegen.synth.env import dc_block as dc_block_voice
from indiegen.synth.noise import uniform_stream
from indiegen.synth.osc import midi_to_hz


def ks_design(
    f_target: float,
    sample_rate: int,
    feedback: float,
    brightness: float,
) -> tuple[np.ndarray, np.ndarray, int, float]:
    """The filter coefficients, the delay length and the fractional read.

    The one-pole in the feedback path has a group delay of
    ``atan2(b sin w, 1 - b cos w) / w``; subtracting it from the ideal loop
    length puts the fundamental where the note says it is.
    """
    omega = 2.0 * math.pi * f_target / sample_rate
    tau = math.atan2(brightness * math.sin(omega), 1.0 - brightness * math.cos(omega)) / omega
    total = sample_rate / f_target - tau
    length = int(math.floor(total))
    fraction = total - length
    coefficients = np.zeros(length + 2, dtype=np.float64)
    coefficients[0] = 1.0
    coefficients[1] = -brightness
    coefficients[length] = -feedback * (1.0 - brightness) * (1.0 - fraction)
    coefficients[length + 1] = -feedback * (1.0 - brightness) * fraction
    numerators = np.array([1.0, -brightness], dtype=np.float64)
    return coefficients, numerators, length, fraction


def pluck_excitation(
    length: int,
    position_permille: int,
    seed: int,
) -> np.ndarray:
    """A one-period noise burst, comb-shaped by where the string was plucked.

    The noise comes from the project's counter-based mixer, not from a random
    number generator: an instrument may not roll dice, and the variation it
    needs is the integer seed on the event.
    """
    burst = uniform_stream(seed, 0, 0, length) * 2.0
    position = max(1, min(length - 1, round(position_permille * length / 1000)))
    combed = burst - np.concatenate([np.zeros(position), burst[: length - position]])
    shaped: np.ndarray = combed * np.exp(-np.arange(length, dtype=np.float64) / (0.5 * length))
    return shaped


def render_pluck(event: PluckEvent, sample_rate: int) -> np.ndarray:
    """One plucked string, as a mono buffer."""
    count = event.duration_frames
    frequency = midi_to_hz(event.midi) * math.pow(2.0, event.detune_cents / 1200.0)
    coefficients, numerators, length, _ = ks_design(
        frequency,
        sample_rate,
        event.feedback.numerator / event.feedback.denominator,
        event.brightness.numerator / event.brightness.denominator,
    )
    excitation = pluck_excitation(length, event.pluck_position_permille, event.excitation_seed)
    voice = lfilter(numerators, coefficients, np.concatenate([excitation, np.zeros(count)]))[:count]
    blocked: np.ndarray = dc_block_voice(voice, sample_rate)
    return blocked
