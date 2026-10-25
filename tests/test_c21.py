"""c21 smoke tests: envelope_curve rise ratio and bit-distinctness."""

from __future__ import annotations

import numpy as np

from indiegen.plan import EventBase
from indiegen.synth.env import note_envelope
from indiegen.theory.scales import MODE_INTERVALS


def _event(attack: int, curve: int) -> EventBase:
    return EventBase(
        instrument="pad",
        start_frame=0,
        duration_frames=1000,
        midi=60,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=attack,
        release_frames=100,
        envelope_curve=curve,
    )


def test_envelope_curve_exp_rise_0_575() -> None:
    attack = 200
    env = note_envelope(_event(attack, 1))
    # 90% rise point: first index where envelope >= 0.9
    idx = int(np.searchsorted(env, 0.9))
    assert abs(idx / attack - 0.575) < 0.05


def test_envelope_curve_bit_distinct_from_linear() -> None:
    a = note_envelope(_event(200, 0))
    b = note_envelope(_event(200, 1))
    assert not np.array_equal(a, b)


def test_envelope_curve_default_linear_unchanged() -> None:
    e = EventBase(
        instrument="pad",
        start_frame=0,
        duration_frames=1000,
        midi=60,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=200,
        release_frames=100,
    )
    assert e.envelope_curve == 0
    assert np.array_equal(note_envelope(e), note_envelope(_event(200, 0)))


def test_ambient_dorian_beat_rate_le_6hz() -> None:
    f0 = 220.0
    # pool with 5/4 dropped
    pool = [(1, 1), (9, 8), (4, 3), (3, 2)]
    scale = [f0 * (2 ** (i / 12.0)) for i in MODE_INTERVALS["dorian"]]
    max_beat = 0.0
    for num, den in pool:
        partial = f0 * num / den
        # nearest scale tone
        nearest = min(scale, key=lambda s: abs(s - partial))
        beat = abs(partial - nearest)
        if beat > max_beat:
            max_beat = beat
    # baseline reference: 5/4 partial beats at 13.37 Hz (recorded, not asserted)
    baseline_5_4_beat = abs(f0 * 5 / 4 - (f0 * (2 ** (3 / 12.0))))
    assert abs(baseline_5_4_beat - 13.37) < 0.01  # the 13.37 Hz the bound below comes from
    assert max_beat <= 6.0


def test_pad_n9_cpu_budget_measured() -> None:
    import time

    from indiegen.plan import PadEvent, Partial, Rational
    from indiegen.synth.pad import pad_state, render_pad_block

    partials = [
        Partial(ratio=Rational(numerator=k, denominator=1), amplitude_millibels=0, detune_cents=0) for k in range(1, 10)
    ]
    event = PadEvent(
        instrument="pad",
        kind="pad",
        start_frame=0,
        duration_frames=131072,
        midi=60,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        partials=partials,
        lfo_rate=Rational(numerator=1, denominator=10),
        lfo_depth_cents=0,
    )
    state = pad_state(event)
    t0 = time.perf_counter()
    render_pad_block(event, 44100, 0, 131072, state)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # reference annotation: ~95.3 ms measured on the machine this was written
    # on. 200 ms keeps 2x headroom for a loaded box; the bound that means
    # something is the realtime one - 131072 samples at 44.1 kHz are 2.97 s of
    # audio, and a block has to be cheaper than the audio it produces.
    block_ms = 131072 / 44100 * 1000.0
    assert elapsed_ms <= 200.0, f"pad N=9 block took {elapsed_ms:.2f} ms; reference ~95.3 ms"
    assert elapsed_ms < block_ms, f"pad N=9 block took {elapsed_ms:.2f} ms for {block_ms:.2f} ms of audio"
    print(f"pad N=9 block time: {elapsed_ms:.2f} ms")
