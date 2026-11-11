"""Measurement tests for issue #12 slice 3 (modal mixture + CP distance)."""

from __future__ import annotations

import json

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import Plan, PluckEvent, Rational
from indiegen.spectrum import modal_mixture_permille


def test_modal_mixture_helper_empty() -> None:
    assert modal_mixture_permille([], [60, 62, 64], 0, 100) == 0


def test_modal_mixture_helper_all_on_scale() -> None:
    ev = PluckEvent(
        kind="pluck",
        instrument="pluck",
        start_frame=0,
        duration_frames=100,
        midi=60,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=997, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=320,
        detune_cents=0,
        excitation_seed=1,
    )
    assert modal_mixture_permille([ev], [60, 62, 64], 0, 100) == 0


def test_modal_mixture_helper_mixed() -> None:
    on = PluckEvent(
        kind="pluck",
        instrument="pluck",
        start_frame=0,
        duration_frames=100,
        midi=60,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=997, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=320,
        detune_cents=0,
        excitation_seed=1,
    )
    off = PluckEvent(
        kind="pluck",
        instrument="pluck",
        start_frame=0,
        duration_frames=100,
        midi=61,
        pan_permille=0,
        amplitude_millibels=0,
        attack_frames=0,
        release_frames=0,
        feedback=Rational(numerator=997, denominator=1000),
        brightness=Rational(numerator=1, denominator=2),
        pluck_position_permille=320,
        detune_cents=0,
        excitation_seed=2,
    )
    # 1 off out of 2 => 500 permille
    assert modal_mixture_permille([on, off], [60, 62, 64], 0, 100) == 500


def test_default_off_zeros() -> None:
    preset = load_preset("motorik")
    preset = preset.model_copy(update={"station": preset.station.model_copy(update={"harmony_cp_enabled": False})})
    plan: Plan = director(compose(preset, 1042, 60 * 44100))
    assert plan.modal_mixture_permille == 0
    assert plan.harmony_cp_solution_count == 0
    for s in plan.sections:
        assert s.modal_mixture_permille == 0
        assert s.harmony_voice_leading_distance == 0
        assert s.harmony_cp_enabled == 0


def test_enabled_measures() -> None:
    preset = load_preset("motorik")
    preset = preset.model_copy(update={"station": preset.station.model_copy(update={"harmony_cp_enabled": True})})
    plan: Plan = director(compose(preset, 1042, 60 * 44100))
    assert plan.harmony_cp_enabled == 1
    assert plan.harmony_cp_solution_count > 0
    # modal mixture field is an int in range
    assert isinstance(plan.modal_mixture_permille, int)
    assert 0 <= plan.modal_mixture_permille <= 1000
    for s in plan.sections:
        assert isinstance(s.modal_mixture_permille, int)
        assert isinstance(s.harmony_voice_leading_distance, int)
    # canonical bytes include the new fields
    raw = plan.model_dump_json()
    obj = json.loads(raw)
    assert "modal_mixture_permille" in obj
    assert "harmony_cp_solution_count" in obj
    assert "modal_mixture_permille" in obj["sections"][0]
    assert "harmony_voice_leading_distance" in obj["sections"][0]
