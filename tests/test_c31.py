"""c31: the hat's upper corner and the masking duck.

Two mechanisms, one charge each:

- the HAT's upper corner, because a hat is high-passed noise (synth/drums.py)
  and a dense hat wall otherwise owns the mix's >14 kHz content, which
  BRIEF 6's MP3 128 codec rule forbids. Measured: without it the indie-noise
  lane fails gate 12 outright (0.925 LU against a 0.5 limit) and
  dub-electronic misses it by 0.0006 LU;
- the DUCK, because the bass and the sustained pad share the 200-500 Hz band.

Every knob is a strict no-op at its default, and the band split carries its
filter state, so a block-wise render is the same audio as a whole-track one.

A station-wide >12 kHz shelf was built and then CUT by measurement: across the
three sweep seeds, the 45 s interlude and the 900 s longform it turned no
failing case into a passing one, and it broke gate 7 on indie-noise by
flattening the novelty curve.
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.gain import millibels_to_gain
from indiegen.mix.masking import (
    DUCK_HIGH_HZ,
    DUCK_LOW_HZ,
    apply_duck,
    duck_band,
    duck_envelope,
)
from indiegen.plan import DrumHit, DuckSpec, HatEvent
from indiegen.render import render_plan
from indiegen.synth.drums import _band_limit, render_hat
from indiegen.synth.filter import bandpass_sos, initial_state

RATE = 44100
SEED = 1042
DUCK = DuckSpec(depth_millibels=-6000, release_frames=8820)


def absolute_energy(signal: np.ndarray, low_hz: float, high_hz: float) -> float:
    """The energy between two corners, in absolute terms.

    Not a share of the whole: a share rises everywhere else as soon as one
    band loses energy, which makes it useless for asking whether a stage
    touched a region it should not have.
    """
    mono = signal if signal.ndim == 1 else signal.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(mono.shape[0], 1.0 / RATE)
    return float(spectrum[(freqs >= low_hz) & (freqs < high_hz)].sum())


def band_energy(signal: np.ndarray, low_hz: float, high_hz: float) -> float:
    """The share of the signal's energy between two corners."""
    mono = signal if signal.ndim == 1 else signal.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(mono.shape[0], 1.0 / RATE)
    total = float(spectrum.sum())
    if total <= 0.0:
        return 0.0
    return float(spectrum[(freqs >= low_hz) & (freqs < high_hz)].sum()) / total


def high_energy(signal: np.ndarray, above_hz: float = 14000.0) -> float:
    """The share of the signal's energy above a corner."""
    return band_energy(signal, above_hz, RATE)


def make_hat(lowpass_hz: int) -> HatEvent:
    return HatEvent(
        kind="hat",
        instrument="hat",
        start_frame=0,
        duration_frames=8000,
        midi=57,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        hits=[DrumHit(frame=0, velocity_millibels=0)],
        noise_seed=7,
        velocity_depth_millibels=0,
        micro_timing_frames=0,
        pan_drift_permille=0,
        cutoff_hz=7000,
        decay_frames=6000,
        lowpass_hz=lowpass_hz,
    )


# --- the hat's upper corner -------------------------------------------------


def test_the_hats_upper_corner_at_zero_is_the_identity_object() -> None:
    """0 means there is no corner, so the voice is the exact object."""
    voice = np.linspace(-0.5, 0.5, 1000)
    assert _band_limit(voice, 0, RATE) is voice


def test_the_hats_upper_corner_removes_the_high_energy() -> None:
    event = make_hat(0)
    open_hat = render_hat(event, event.hits[0], RATE, 1.0)
    limited = render_hat(make_hat(14000), event.hits[0], RATE, 1.0)
    assert high_energy(open_hat) > 0.05
    assert high_energy(limited) < high_energy(open_hat) / 3.0


def test_the_hats_body_survives_its_upper_corner() -> None:
    """A band limit is not a mute: the hat keeps its level."""
    event = make_hat(0)
    open_hat = render_hat(event, event.hits[0], RATE, 1.0)
    limited = render_hat(make_hat(14000), event.hits[0], RATE, 1.0)
    assert float(np.sqrt(np.mean(limited**2))) > 0.5 * float(np.sqrt(np.mean(open_hat**2)))


# --- the duck's envelope ----------------------------------------------------


def test_the_duck_envelope_is_unity_without_hits() -> None:
    assert np.array_equal(duck_envelope(0, 500, [], DUCK), np.ones(500))


def test_the_duck_envelope_is_at_its_depth_on_a_hit() -> None:
    envelope = duck_envelope(0, 500, [0], DUCK)
    assert envelope[0] == pytest.approx(millibels_to_gain(DUCK.depth_millibels))
    assert envelope[-1] > envelope[0]
    assert np.all(envelope <= 1.0)


def test_the_duck_envelope_is_the_same_worked_block_by_block() -> None:
    """No state: every value is a function of the absolute frame index.

    This is what makes the duck safe to render a block at a time.
    """
    hits = [0, 1000, 4001, 9999]
    whole = duck_envelope(0, 12000, hits, DUCK)
    first = duck_envelope(0, 4099, hits, DUCK)
    second = duck_envelope(4099, 12000 - 4099, hits, DUCK)
    assert np.array_equal(np.concatenate([first, second]), whole)


def test_the_duck_envelope_is_unity_before_the_first_hit() -> None:
    envelope = duck_envelope(0, 100, [500], DUCK)
    assert np.all(envelope == 1.0)


# --- the duck's band and its application ------------------------------------


def test_the_duck_band_carries_its_state_across_blocks() -> None:
    """A filter that restarts at a block boundary puts a step in the band."""
    signal = np.random.default_rng(7).standard_normal((12000, 2)) * 0.1
    zeros = initial_state(bandpass_sos(DUCK_LOW_HZ, DUCK_HIGH_HZ, RATE), 2)
    whole, _ = duck_band(signal, zeros, RATE)
    head, carry = duck_band(signal[:4099], zeros, RATE)
    tail, _ = duck_band(signal[4099:], carry, RATE)
    assert np.array_equal(np.concatenate([head, tail]), whole)


def test_the_duck_band_holds_the_declared_band() -> None:
    """It is a band, not the signal smeared: in-band passes, either side does not."""
    times = np.arange(12000, dtype=np.float64) / RATE
    in_band = np.sin(2.0 * np.pi * 350.0 * times)
    below = np.sin(2.0 * np.pi * 60.0 * times)
    above = np.sin(2.0 * np.pi * 4000.0 * times)
    zeros = initial_state(bandpass_sos(DUCK_LOW_HZ, DUCK_HIGH_HZ, RATE), 1)
    for signal, expected in ((in_band, "large"), (below, "small"), (above, "small")):
        band, _ = duck_band(signal, zeros, RATE)
        share = float(np.sum(band**2) / np.sum(signal**2))
        if expected == "large":
            assert share > 0.5
        else:
            assert share < 0.05


def test_the_duck_is_the_identity_at_none() -> None:
    signal = np.ones((10, 2))
    band = np.ones((10, 2))
    gain = np.ones(10)
    assert apply_duck(signal, gain, band, None) is signal


def test_the_duck_attenuates_only_its_band_in_a_render() -> None:
    """The rendered mix loses band energy, and it is the band that lost it."""
    plan = director(compose(load_preset("motorik"), SEED, 6 * RATE))
    assert plan.duck is not None
    ducked = render_plan(plan)
    dry = render_plan(plan.model_copy(update={"duck": None}))

    lost_in_band = absolute_energy(dry, DUCK_LOW_HZ, DUCK_HIGH_HZ) - absolute_energy(ducked, DUCK_LOW_HZ, DUCK_HIGH_HZ)
    lost_above = absolute_energy(dry, 1000.0, 12000.0) - absolute_energy(ducked, 1000.0, 12000.0)
    assert lost_in_band > 0.0
    # The carve is aimed: the band loses at least an order of magnitude more
    # than everything above it. A Butterworth band is not brick-wall, so the
    # rest is not required to be exactly zero.
    assert lost_in_band > 10.0 * max(lost_above, 0.0)


# --- the lane stamps what it declares ---------------------------------------


def test_a_lane_stamps_its_duck() -> None:
    plan = director(compose(load_preset("motorik"), SEED, 5 * RATE))
    assert plan.duck == DUCK


def test_only_a_lane_with_a_bass_declares_a_duck() -> None:
    """A duck only a lane with bass hits can consume is declared only there."""
    with_duck = []
    for lane in ("motorik", "kosmische", "ambient", "dub-electronic", "indie-noise"):
        plan = director(compose(load_preset(lane), SEED, 5 * RATE))
        if plan.duck is not None:
            with_duck.append(lane)
            assert any(event.kind == "bass" for event in plan.events), lane
    assert sorted(with_duck) == ["dub-electronic", "motorik"]


def test_every_hat_lane_carries_the_codec_corner() -> None:
    """BRIEF 6 applies to every track the station releases."""
    for lane in ("motorik", "dub-electronic", "indie-noise"):
        plan = director(compose(load_preset(lane), SEED, 5 * RATE))
        hats = [event for event in plan.events if isinstance(event, HatEvent)]
        assert hats
        assert all(hat.lowpass_hz > 0 for hat in hats), lane


# --- the block identity of the mask stage -----------------------------------


def test_a_render_with_the_mask_stage_is_the_same_in_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mask stage carries its state, so the block size cannot be heard.

    The block size here is above the longest drum voice on purpose. A drum
    voice longer than the block loses its tail past the second block - a
    PRE-EXISTING defect, recorded as ``c31-preexisting-drum-tail-block`` and
    NOT this change's, which this test would otherwise trip over instead of
    measuring its own stages.
    """
    from indiegen import render as render_module

    plan = director(compose(load_preset("motorik"), SEED, 12 * RATE))
    assert plan.duck is not None
    whole = render_module.render_plan(plan)
    monkeypatch.setattr(render_module, "RENDER_BLOCK", 16384)
    pieces = render_module.render_plan(plan)
    assert np.array_equal(pieces, whole)
