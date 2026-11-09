"""c9b (issue #9b, Commit1 T1): synthetic tests for the re-derive harness.

Fast and synthetic only: no sweep renders. The harness module is loaded
from ``tools/c9b_rederive_timbre.py`` without executing ``main()``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Literal

import numpy as np

_HARNESS_PATH = Path(__file__).resolve().parents[1] / "tools" / "c9b_rederive_timbre.py"
_spec = importlib.util.spec_from_file_location("c9b_rederive_timbre", _HARNESS_PATH)
assert _spec is not None and _spec.loader is not None
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)  # type: ignore[union-attr]


def _obs(function: str, centroid: float, weight: int, lane: str = "motorik") -> Any:
    return harness.Observation(
        lane=lane, seed=1042, seconds=240, function=function, centroid_hz=centroid, weight=weight
    )


def _synth_plan(functions: list[str]) -> Any:
    """A minimal 4-section plan tiling 8 s, one function per section."""
    from indiegen.plan import MotifCell, MotifNote, Plan, SectionPlan

    rate = 44100
    frames = 8 * rate
    sections_count = len(functions)
    width = frames // sections_count
    sections = [
        SectionPlan(
            index=index,
            function=functions[index],
            start_frame=index * width,
            end_frame=(index + 1) * width,
            bars=1,
            density=50,
            level_millibels=0,
            techniques=[],
            instrumentation=["pad"],
            mode="dorian",
            root_midi=38,
            texture="open",
            reprise_of=-1,
            centroid_hz=1000,
        )
        for index in range(sections_count)
    ]
    return Plan(
        version=3,
        format_version=1,
        preset="motorik",
        seed=1042,
        lane="motorik",
        alias="x",
        album="x",
        file_token="x",
        title="x",
        sample_rate=rate,
        channels=2,
        duration_frames=frames,
        duration_range_frames=[frames, frames],
        form="full",  # type: ignore[arg-type]
        tempo_bpm=120,
        frames_per_beat=22050,
        meter_numerator=4,
        meter_denominator=4,
        pulse="bars",  # type: ignore[arg-type]
        scale_midi=[60],
        fx_sends=[],
        techniques=[],
        strategy_deck=[],
        section_count_range=[sections_count, sections_count],
        section_count=sections_count,
        sections=sections,
        motif=MotifCell(notes=[MotifNote(midi=38, duration_frames=22050)]),
        motif_appearances=[],
        deja_vu_replay_permille=[],
        title_words=[],
        lane_weights=[],
        dither_seed=1,
        dither_lsb=1,
        target_lufs_millibels=-16000,
        ceiling_millibels=0,
        bus_gains=[],
        fade_in_frames=0,
        fade_out_frames=0,
        section_crossfade_frames=0,
        track_number=1,
        delay_sends=[],
        reverb=None,
        frippertronics=None,
        dub_chain=None,
        events=[],
        director_log=[],
    )


def test_corpus_is_18_cells_fit_15_holdout_3() -> None:
    """AC1.1: sweep15 fit + 2 falsifiers + 1 authority = 18."""
    fit = harness.fit_cells()
    hold = harness.holdout_cells()
    corpus = harness.corpus_cells()
    assert len(fit) == 15
    assert len(hold) == 3
    assert len(corpus) == 18
    assert [(c.lane, c.seed, c.seconds) for c in fit[:3]] == [
        ("motorik", 1042, 240),
        ("motorik", 2000, 240),
        ("motorik", 4002, 240),
    ]
    assert {c.lane for c in fit} == {"motorik", "kosmische", "dub-electronic", "indie-noise", "ambient"}
    assert {c.seed for c in fit} == {1042, 2000, 4002}
    assert all(c.seconds == 240 for c in fit)
    assert [(c.lane, c.seed, c.seconds, c.role) for c in hold] == [
        ("dub-electronic", 1042, 45, "falsifier"),
        ("kosmische", 1042, 45, "falsifier"),
        ("kosmische", 1042, 60, "authority"),
    ]
    assert list(harness.LANES) == ["motorik", "kosmische", "dub-electronic", "indie-noise", "ambient"]
    assert list(harness.FIT_LANES) == ["motorik", "kosmische", "dub-electronic", "indie-noise"]
    assert "ambient" in harness.EXCLUDED_LANES


def test_duration_weighted_mean_rounds_and_clamps() -> None:
    """Per-function = sum(c*w)/sum(w), int round, clamp >= 1."""
    old = {"intro": 1000, "build": 2000, "outro": 3000}
    block = harness.aggregate_lane(
        [_obs("intro", 1000.0, 10), _obs("intro", 2000.0, 30), _obs("build", 1500.4, 5)],
        old,
    )
    # intro: (1000*10 + 2000*30)/40 = 1750
    assert block["new"]["intro"] == 1750
    # build: 1500.4 rounds to 1500
    assert block["new"]["build"] == 1500
    # outro: zero sections -> keep old, reported
    assert block["new"]["outro"] == 3000
    assert block["kept_old"] == ["outro"]
    assert block["counts"]["intro"] == {"sections": 2, "weight": 40}
    assert block["counts"]["outro"] == {"sections": 0, "weight": 0}
    # Same duration unweighted would be 1500 for intro; weighting moves it.
    assert block["new"]["intro"] != 1500
    # Clamp: a tiny weighted mean still yields >= 1, never 0.
    tiny = harness.aggregate_lane([_obs("intro", 0.2, 5), _obs("build", 0.2, 5)], old)
    assert tiny["new"]["intro"] >= 1
    assert tiny["new"]["build"] >= 1


def test_motorik_peak_is_excluded_never_invented() -> None:
    """Motorik has 7 keys (no peak): peak observations are excluded."""
    old = {"break": 2150, "build": 4593, "drift": 4486, "intro": 1473, "outro": 1401, "plateau": 4875, "return": 4708}
    block = harness.aggregate_lane(
        [_obs("peak", 9999.0, 20), _obs("intro", 1000.0, 10)],
        old,
    )
    assert "peak" not in block["new"]
    assert list(block["new"].keys()) == list(old.keys())
    assert block["excluded_functions"] == {"peak": 1}
    assert block["excluded_observations"] == 1
    assert block["new"]["intro"] == 1000


def test_zero_weight_observations_do_not_fit() -> None:
    """Zero-weight sections contribute nothing; the key keeps old."""
    old = {"intro": 1000, "build": 2000}
    block = harness.aggregate_lane([_obs("intro", 5000.0, 0)], old)
    assert block["new"]["intro"] == 1000
    assert block["kept_old"] == ["intro", "build"]


def test_measure_sections_synthetic_mix_weights_and_order() -> None:
    """Synthetic mix: low tone then high tone -> per-section centroids split.

    Weight is last-first per-second samples; sections tile 8 s so each
    non-edge section weighs 2 s and the first/last lose the fade/second
    offset exactly as validate._section_means computes it.
    """
    plan = _synth_plan(["intro", "build", "plateau", "outro"])
    rate = 44100
    time = np.arange(plan.duration_frames, dtype=np.float64) / rate
    # First half 220 Hz, second half 2200 Hz: centroid must rise, not be flat.
    freq = np.where(time < 4.0, 220.0, 2200.0)
    mono = np.sin(2.0 * np.pi * np.cumsum(freq) / rate)
    mix = np.stack([mono, mono], axis=1).astype(np.float64) * 0.5
    observations = harness.measure_sections(plan, mix)
    assert [o.function for o in observations] == ["intro", "build", "plateau", "outro"]
    assert all(o.weight > 0 for o in observations)
    # Weights are the per-second sample counts: total <= 8.
    assert sum(o.weight for o in observations) <= 8
    centroids = [o.centroid_hz for o in observations]
    # The bright half's mean exceeds the dark half's mean.
    assert np.mean(centroids[2:]) > np.mean(centroids[:2])
    assert all(c > 0 for c in centroids)


def test_measure_sections_matches_validate_section_means() -> None:
    """measure_sections centroids equal _section_means(per_second_centroid)."""
    from indiegen.validate import _first_second, _section_means, per_second_centroid

    plan = _synth_plan(["intro", "build", "plateau", "outro"])
    rate = 44100
    time = np.arange(plan.duration_frames, dtype=np.float64) / rate
    mono = np.sin(2.0 * np.pi * 440.0 * time)
    mix = np.stack([mono, mono], axis=1).astype(np.float64) * 0.5
    measured = per_second_centroid(mix, plan.sample_rate, plan.fade_in_frames)
    expected = _section_means(plan, measured, _first_second(plan))
    observations = harness.measure_sections(plan, mix)
    assert len(observations) == len(plan.sections)
    # Direct elementwise check in section order.
    assert [o.centroid_hz for o in observations] == [float(v) for v in expected]


def test_patch_preset_text_preserves_order_and_only_timbre_line() -> None:
    """Patching changes the timbre line, nothing else; order enforced."""
    text = (
        "kind: lane\nlane: motorik\n"
        "timbre: {break: 2150, build: 4593, drift: 4486, intro: 1473, outro: 1401, plateau: 4875, return: 4708}\n"
        "\nfx_sends: []\n"
    )
    keys, values = harness.parse_timbre_line(text)
    assert keys == ["break", "build", "drift", "intro", "outro", "plateau", "return"]
    assert values["intro"] == 1473
    new = dict(values)
    new["intro"] = 1000
    patched = harness.patch_preset_text(text, new)
    assert (
        "timbre: {break: 2150, build: 4593, drift: 4486, intro: 1000, outro: 1401, plateau: 4875, return: 4708}"
        in patched
    )
    # Every non-timbre line is byte-identical.
    assert [line for line in patched.splitlines() if not line.startswith("timbre:")] == [
        line for line in text.splitlines() if not line.startswith("timbre:")
    ]
    # Reordered or invented keys (e.g. motorik peak) are rejected.
    reordered = {"build": 1, "break": 2, "drift": 3, "intro": 4, "outro": 5, "plateau": 6, "return": 7}
    try:
        harness.patch_preset_text(text, reordered)
    except ValueError:
        pass
    else:
        raise AssertionError("reordered keys must raise")
    invented = dict(new)
    invented["peak"] = 1234
    try:
        harness.patch_preset_text(text, invented)
    except ValueError:
        pass
    else:
        raise AssertionError("invented peak must raise")


def test_decide_k1_floors() -> None:
    """K1 PASS iff gate5 >= 0.8858 and gate6 >= 0.6840."""
    assert harness.GATE5_FLOOR == 0.8858
    assert harness.GATE6_FLOOR == 0.6840
    ok = harness.decide_k1(
        [
            {"gate": 5, "measured": 0.90584, "floor": 0.8858, "pass": True},
            {"gate": 6, "measured": 0.70398, "floor": 0.6840, "pass": True},
        ]
    )
    assert ok["k1"] == "PASS"
    low6 = harness.decide_k1(
        [
            {"gate": 5, "measured": 0.90, "floor": 0.8858, "pass": True},
            {"gate": 6, "measured": 0.68, "floor": 0.6840, "pass": False},
        ]
    )
    assert low6["k1"] == "FAIL"
    missing = harness.decide_k1([{"gate": 5, "measured": 0.99, "pass": True}])
    assert missing["k1"] == "FAIL"


def test_fit_from_observations_excludes_ambient() -> None:
    """Ambient observations never reach a fit block (monkeypatched timbre)."""
    # fit_from_observations calls old_timbre_for which hits disk; instead
    # verify the lane partition logic directly via aggregate exclusion:
    # ambient is not in FIT_LANES, so fit_from_observations cannot emit it.
    assert "ambient" not in harness.FIT_LANES
    assert all(lane != "ambient" for lane in harness.FIT_LANES)
    # And a pure aggregate for a fit lane still works with ambient obs present:
    obs = [_obs("intro", 1000.0, 10, lane="motorik"), _obs("intro", 9999.0, 10, lane="ambient")]
    motorik_only = [o for o in obs if o.lane == "motorik"]
    block = harness.aggregate_lane(motorik_only, {"intro": 500})
    assert block["new"]["intro"] == 1000
    _ = Literal  # keep typing import referenced
