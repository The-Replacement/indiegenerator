"""c30: the per-voice shaper and the drum snap.

The shaper is output-side odd-harmonic distortion: at drive 0 it is the
identity, so the default render cannot move; above 0 it puts harmonics where
a sum of sines had none. The snap is a four millisecond transient on a drum
attack, zero at snap 0.
"""

from __future__ import annotations

import numpy as np

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import HatEvent
from indiegen.render import render_plan
from indiegen.synth.drums import render_hat
from indiegen.synth.grit import MAX_DRIVE, drive_gain, waveshape

RATE = 44100


def test_drive_zero_is_the_identity_object() -> None:
    signal = np.linspace(-1.0, 1.0, 1000)
    assert waveshape(signal, 0) is signal


def test_drive_one_thousand_stays_bounded() -> None:
    signal = np.linspace(-1.0, 1.0, 1000)
    shaped = waveshape(signal, 1000)
    assert np.max(np.abs(shaped)) <= 1.0 / drive_gain(1000)
    assert drive_gain(1000) == 1.0 + MAX_DRIVE


def test_the_shaper_adds_odd_harmonics() -> None:
    # 441 Hz is bin 441 at 44100 for a one-second window: no leakage. The
    # phase is taken modulo one to keep sin()'s argument small.
    fundamental = 441.0
    cycles = np.arange(RATE, dtype=np.float64) * fundamental / RATE
    sine = np.sin(2.0 * np.pi * (cycles % 1.0)) * 0.9

    def third_over_first(signal: np.ndarray) -> float:
        spectrum = np.abs(np.fft.rfft(signal))
        freqs = np.fft.rfftfreq(signal.size, 1.0 / RATE)
        first = float(spectrum[np.argmin(np.abs(freqs - fundamental))])
        third = float(spectrum[np.argmin(np.abs(freqs - 3.0 * fundamental))])
        return third / first

    assert third_over_first(sine) < 1e-3
    assert third_over_first(waveshape(sine, 1000)) > 0.01


def test_the_snap_enlarges_a_drum_attack() -> None:
    from indiegen.plan import DrumHit

    def hat(snap: int) -> np.ndarray:
        event = HatEvent(
            kind="hat",
            instrument="hat",
            start_frame=0,
            duration_frames=4000,
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
            snap_permille=snap,
            cutoff_hz=7000,
            decay_frames=2600,
        )
        return render_hat(event, event.hits[0], RATE, 1.0)

    quiet = hat(0)
    snapped = hat(1000)
    assert np.max(np.abs(snapped)) > np.max(np.abs(quiet))


def test_a_lane_stamps_its_drive_and_snap_on_events() -> None:
    plan = director(compose(load_preset("motorik"), 1042, 5 * RATE))
    drives = {event.drive_permille for event in plan.events}
    snaps = {event.snap_permille for event in plan.events if event.kind in {"kick", "snare", "hat", "bass"}}
    assert 300 in drives
    assert snaps == {400}


def test_drive_zero_events_are_the_old_events() -> None:
    from indiegen.compose.planner import _apply_timbre

    plan = compose(load_preset("motorik"), 1042, 5 * RATE)
    assert _apply_timbre(list(plan.events), 0, 0) == list(plan.events)


def test_a_driven_lane_differs_from_a_cold_one() -> None:
    warm = render_plan(director(compose(load_preset("motorik"), 1042, 5 * RATE)))
    preset = load_preset("motorik")
    lanes = [
        entry.model_copy(
            update={"parameters": entry.parameters.model_copy(update={"drive_permille": 0, "snap_permille": 0})}
        )
        for entry in preset.lanes
    ]
    cold = render_plan(director(compose(preset.model_copy(update={"lanes": lanes}), 1042, 5 * RATE)))
    assert not np.array_equal(warm, cold)
    assert abs(float(np.mean(np.abs(warm))) - float(np.mean(np.abs(cold)))) > 0.0
