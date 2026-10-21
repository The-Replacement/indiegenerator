"""AC-61: the note envelope.

Monotonically non-decreasing over the attack, monotonically non-increasing
over the release, and exactly zero at the first and the last frame - even
for a note that declares no attack or release, such as a plucked string.
"""

from __future__ import annotations

import numpy as np

from indiegen.plan import EventBase
from indiegen.synth.env import note_envelope


def _event(attack: int, release: int, count: int = 1000) -> EventBase:
    return EventBase(
        instrument="pad",
        start_frame=0,
        duration_frames=count,
        midi=60,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=attack,
        release_frames=release,
    )


def test_the_edges_are_exactly_zero() -> None:
    for attack, release in ((0, 0), (100, 100), (0, 50), (50, 0)):
        envelope = note_envelope(_event(attack, release))
        assert envelope[0] == 0.0
        assert envelope[-1] == 0.0


def test_the_attack_rises_monotonically() -> None:
    envelope = note_envelope(_event(200, 200))
    attack = envelope[:200]
    assert np.all(np.diff(attack) >= 0.0)


def test_the_release_falls_monotonically() -> None:
    envelope = note_envelope(_event(200, 200))
    release = envelope[-200:]
    assert np.all(np.diff(release) <= 0.0)


def test_the_sustain_is_unity() -> None:
    envelope = note_envelope(_event(200, 200))
    assert envelope[500] == 1.0
