"""Audit: bass oscillator aliasing (issue #28).

Measures the alias tone of the naive saw vs the bandlimited (Fourier) saw.
The naive path is the S0-frozen default; the bandlimited path is opt-in via
``oscillator="bandlimited"``.
"""

from __future__ import annotations

import numpy as np

from indiegen.plan import BassEvent, BassHit
from indiegen.synth.drums import render_bass


def _bass(oscillator: str, midi: int = 72) -> np.ndarray:
    event = BassEvent(
        kind="bass",
        instrument="bass",
        start_frame=0,
        duration_frames=4096,
        midi=midi,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        noise_seed=1,
        velocity_depth_millibels=0,
        micro_timing_frames=0,
        pan_drift_permille=0,
        snap_permille=0,
        hits=[BassHit(frame=0, velocity_millibels=0, drift_frames=0, midi=midi)],
        cutoff_hz=4000,
        decay_frames=4096,
        oscillator=oscillator,
    )
    hit = event.hits[0]
    return render_bass(event, hit, 44100, 1.0)


def _high_band_energy(signal: np.ndarray, sample_rate: int, cutoff_hz: float) -> float:
    spectrum = np.abs(np.fft.rfft(signal)) ** 2
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)
    mask = freqs >= cutoff_hz
    return float(np.sum(spectrum[mask]))


def test_bandlimited_has_less_high_band_energy_than_naive() -> None:
    naive = _bass("naive", midi=72)
    bandlimited = _bass("bandlimited", midi=72)
    naive_hf = _high_band_energy(naive, 44100, 10000.0)
    bandlimited_hf = _high_band_energy(bandlimited, 44100, 10000.0)
    print(f"naive HF(>10k): {naive_hf:.3e}  bandlimited HF(>10k): {bandlimited_hf:.3e}")
    assert bandlimited_hf < naive_hf


def test_naive_is_s0_default() -> None:
    """Default oscillator must be 'naive' (S0 frozen)."""
    from indiegen.plan import BassEvent

    defaults = BassEvent.model_fields["oscillator"].default
    assert defaults == "naive"
