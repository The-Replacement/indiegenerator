"""The formant choir: breath noise filtered through parallel formant bandpasses.

Each formant is an RBJ biquad bandpass at a fixed integer frequency. The
voices are summed and scaled by the event's amplitude. State is threaded
across render blocks through the filter carries.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from indiegen.gain import millibels_to_gain
from indiegen.plan import FormantEvent
from indiegen.synth.filter import apply_biquad, bandpass_sos, initial_state


@dataclass(frozen=True)
class FormantState:
    """The filter carries for every formant bandpass."""

    carries: tuple[np.ndarray, ...]


def formant_state(event: FormantEvent, sample_rate: int = 44100) -> FormantState:
    """The zero state of a formant choir voice."""
    carries: list[np.ndarray] = []
    for freq in event.formants:
        low = max(20, int(freq) - 100)
        high = int(freq) + 100
        if high <= low:
            high = low + 1
        sos = bandpass_sos(low, high, sample_rate)
        carries.append(initial_state(sos, 1))
    if not carries:
        carries.append(np.zeros((1, 2), dtype=np.float64))
    return FormantState(carries=tuple(carries))


def render_formant_block(
    event: FormantEvent,
    sample_rate: int,
    start: int,
    stop: int,
    state: FormantState,
) -> tuple[np.ndarray, FormantState]:
    """One formant choir voice, over the local frames [start, stop)."""
    count = stop - start
    voice = np.zeros(count, dtype=np.float64)
    if count <= 0:
        return voice, state
    indices = np.arange(count, dtype=np.uint64) + np.uint64((int(event.noise_seed) + int(start)) & 0xFFFFFFFF)
    noise_state = (indices * np.uint64(6364136223846793005) + np.uint64(1442695040888963407)) & np.uint64(
        0xFFFFFFFFFFFFFFFF
    )
    noise = (noise_state.astype(np.float64) / np.float64(2**63)) - np.float64(1.0)
    carries = list(state.carries)
    max_voices = max(1, int(event.voice_count_max))
    formants = (list(event.formants) or [650, 1100, 2850])[:max_voices]
    for index, freq in enumerate(formants):
        freq = int(freq) + int(event.detune_cents) * index // max(1, len(formants))
        low = max(20, int(freq) - 100)
        high = int(freq) + 100
        if high <= low:
            high = low + 1
        sos = bandpass_sos(low, high, sample_rate)
        if index >= len(carries):
            carries.append(initial_state(sos, 1))
        filtered, new_carry = apply_biquad(sos, noise, carries[index])
        voice += np.asarray(filtered, dtype=np.float64).reshape(count)
        carries[index] = new_carry
    breath = max(0, min(1000, int(event.breath_permille))) / 1000.0
    voice = voice * (0.5 + 0.5 * breath)
    amplitude = millibels_to_gain(event.amplitude_millibels)
    voice = voice * amplitude
    return voice, FormantState(carries=tuple(carries))


def render_formant(event: FormantEvent, sample_rate: int) -> np.ndarray:
    """One formant choir voice, as a mono buffer."""
    voice, _ = render_formant_block(event, sample_rate, 0, event.duration_frames, formant_state(event))
    return voice
