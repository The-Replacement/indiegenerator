"""Tests for the wrapped mod-12 quotient geodesic voice leading (issue #13)."""

from __future__ import annotations

from itertools import permutations

import pytest
from pydantic import ValidationError

from indiegen.plan import Plan
from indiegen.theory.orbifold import (
    circular_semitone_dist,
    geodesic_distance,
    geodesic_matching,
    is_crossing,
    is_doubled,
    lead_voicing,
)

# --- circular_semitone_dist -------------------------------------------------


def test_circular_semitone_dist_boundary() -> None:
    assert circular_semitone_dist(0, 0) == 0
    assert circular_semitone_dist(0, 11) == 1
    assert circular_semitone_dist(0, 6) == 6
    assert circular_semitone_dist(0, 7) == 5


def test_circular_semitone_dist_symmetric() -> None:
    assert circular_semitone_dist(0, 7) == circular_semitone_dist(7, 0)
    assert circular_semitone_dist(3, 10) == circular_semitone_dist(10, 3)


# --- geodesic_distance ------------------------------------------------------


def test_geodesic_distance_identity_is_zero() -> None:
    assert geodesic_distance((0, 4, 7), (0, 4, 7)) == 0
    assert geodesic_distance((), ()) == 0


def test_geodesic_distance_returns_int_and_is_pure() -> None:
    a = (0, 4, 7)
    b = (2, 5, 11)
    first = geodesic_distance(a, b)
    assert isinstance(first, int)
    assert geodesic_distance(a, b) == first
    assert geodesic_distance(a, b) == first  # twice, no mutation / no state


def test_geodesic_distance_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        geodesic_distance((0,), (0, 1))


def test_geodesic_distance_is_min_over_bijections() -> None:
    """Exhaustive k=3 check: the result equals the min over all 6 pairings."""
    a = (0, 4, 7)
    b = (2, 9, 5)
    brute = min(
        sum(circular_semitone_dist(a[i], b[j]) for i, j in enumerate(perm)) for perm in permutations(range(len(b)))
    )
    assert geodesic_distance(a, b) == brute


def test_geodesic_distance_single_voice_is_circular() -> None:
    assert geodesic_distance((0,), (7,)) == 5
    assert geodesic_distance((60,), (72,)) == 0  # same pitch class, octave apart


# --- geodesic_matching ------------------------------------------------------


def test_geodesic_matching_lexicographic_tie_break() -> None:
    # Both pairings cost 0 (both voices share pitch class 0), so the
    # lexicographically-first permutation (0, 1) wins.
    assert geodesic_matching((0, 0), (0, 12)) == (0, 1)


def test_geodesic_matching_identity_preferred() -> None:
    assert geodesic_matching((0, 4, 7), (0, 4, 7)) == (0, 1, 2)


def test_geodesic_matching_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        geodesic_matching((0,), (0, 1))


# --- crossing / doubling predicates ----------------------------------------


def test_is_crossing() -> None:
    assert is_crossing((60, 64, 67)) is True
    assert is_crossing((60, 60, 67)) is False  # equal voices
    assert is_crossing((60, 67, 64)) is False  # voices cross
    assert is_crossing(()) is True  # vacuous


def test_is_doubled() -> None:
    assert is_doubled((60, 64, 67)) is False
    assert is_doubled((60, 72, 60)) is True
    assert is_doubled(()) is False  # vacuous: no doubling


# --- lead_voicing -----------------------------------------------------------


def test_lead_voicing_stays_in_register_and_ordered() -> None:
    v = lead_voicing((), (60, 64, 67), low=36, high=96)
    assert all(36 <= p <= 96 for p in v)
    assert is_crossing(v)
    assert not is_doubled(v)


def test_lead_voicing_returns_valid_target_unchanged() -> None:
    target = (60, 64, 67)
    assert lead_voicing((55, 60), target, low=36, high=96) == target


def test_lead_voicing_folds_high_target_into_window() -> None:
    # A root an octave too low gets spelled up into the window, still ordered.
    v = lead_voicing((), (24, 28, 31), low=36, high=96)
    assert all(36 <= p <= 96 for p in v)
    assert is_crossing(v)
    assert not is_doubled(v)


# --- the distance bar -------------------------------------------------------


def _absolute_per_voice(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """The current heuristic's per-voice absolute total (identity pairing)."""
    return sum(abs(x - y) for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ((60,), (65,)),
        ((0, 4, 7), (2, 5, 11)),
        ((60, 64, 67), (67, 72, 74)),
        ((55, 59, 62, 67), (48, 52, 55, 60)),
    ],
)
def test_geodesic_distance_never_exceeds_per_voice_absolute(a: tuple[int, ...], b: tuple[int, ...]) -> None:
    """Σ geodesic <= Σ |Δmidi|: the identity pairing is one bijection, and
    circular distance never exceeds absolute distance pointwise."""
    assert geodesic_distance(a, b) <= _absolute_per_voice(a, b)


# --- flag defaults ----------------------------------------------------------


def test_geodesic_flag_defaults_off(reference_plan: Plan) -> None:
    assert reference_plan.geodesic_voice_leading == 0


def test_geodesic_flag_rejects_two(reference_plan: Plan) -> None:
    payload = reference_plan.model_dump()
    payload["geodesic_voice_leading"] = 2
    with pytest.raises(ValidationError):
        Plan.model_validate(payload)


# --- flag-ON walk (register discipline) -------------------------------------


def test_geodesic_flag_on_walks_into_register() -> None:
    """With the flag on, the geodesic walk snaps plucks and bass into register.

    The flag is code-only, so enable it on the station model directly. The
    walk must land every pluck in 36..96 and every bass hit in 24..72 — the
    same register discipline the heuristic pass enforces.
    """
    from indiegen.compose import compose, director
    from indiegen.config import load_preset
    from indiegen.plan import BassEvent, PluckEvent

    preset = load_preset("motorik")
    enabled = preset.model_copy(update={"station": preset.station.model_copy(update={"geodesic_voice_leading": True})})
    plan = director(compose(enabled, 1042, 60 * 44100))
    assert plan.geodesic_voice_leading == 1
    for event in plan.events:
        if isinstance(event, PluckEvent):
            assert 36 <= event.midi <= 96
        elif isinstance(event, BassEvent):
            assert all(24 <= hit.midi <= 72 for hit in event.hits)
