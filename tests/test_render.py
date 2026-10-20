"""AC-26, AC-28, AC-29, AC-30, AC-49: the render path is pure and honest."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from indiegen.plan import Plan
from indiegen.render import BLOCK_SIZE, render_plan, schedule
from indiegen.synth.filter import apply_biquad, initial_state, lowpass_sos

PACKAGE: Path = Path(__file__).resolve().parents[1] / "src" / "indiegen"


def test_block_size_is_8192() -> None:
    assert BLOCK_SIZE == 8192


def test_block_size_is_defined_once_in_the_package() -> None:
    found: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "BLOCK_SIZE":
                        found.append(path.name)
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "BLOCK_SIZE":
                    found.append(path.name)
    assert len(found) == 1


def test_threaded_filtering_is_bit_identical_to_one_call() -> None:
    generator = np.random.default_rng(0)
    signal = generator.standard_normal(BLOCK_SIZE * 3)
    sos = lowpass_sos(1200, 1, 1, 44100)
    whole, _ = apply_biquad(sos, signal, initial_state(sos, 1))
    state = initial_state(sos, 1)
    pieces: list[np.ndarray] = []
    for start in range(0, signal.size, BLOCK_SIZE):
        piece, state = apply_biquad(sos, signal[start : start + BLOCK_SIZE], state)
        pieces.append(piece)
    assert np.array_equal(np.concatenate(pieces), whole)


def test_the_same_block_twice_from_the_same_state_is_identical() -> None:
    generator = np.random.default_rng(1)
    signal = generator.standard_normal(BLOCK_SIZE)
    sos = lowpass_sos(800, 1, 1, 44100)
    state = initial_state(sos, 1)
    first, _ = apply_biquad(sos, signal, state)
    second, _ = apply_biquad(sos, signal, state)
    assert np.array_equal(first, second)


def test_schedule_is_stable_and_sorted(reference_plan: Plan) -> None:
    events = schedule(reference_plan)
    assert [event.start_frame for event in events] == sorted(event.start_frame for event in events)
    assert len(events) == len(reference_plan.events)


def test_the_pad_declares_three_partials_with_small_detunes(reference_plan: Plan) -> None:
    for event in reference_plan.events:
        assert event.partials == 3
        for detune in event.partial_detune_cents:
            assert isinstance(detune, int)
            assert -5 <= detune <= 5
        assert event.lfo_rate.numerator > 0
        assert event.lfo_rate.denominator > 0
        assert isinstance(event.lfo_depth_cents, int)


def test_the_fundamental_is_coherent_across_the_channels(reference_plan: Plan) -> None:
    stereo = render_plan(reference_plan)
    mono = stereo.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(mono.size)))
    frequencies = np.fft.rfftfreq(mono.size, 1.0 / reference_plan.sample_rate)
    fundamental = float(frequencies[int(np.argmax(spectrum))])
    band = (frequencies > fundamental * 0.99) & (frequencies < fundamental * 1.01)
    left = np.sum(np.abs(np.fft.rfft(stereo[:, 0] * np.hanning(mono.size)))[band] ** 2)
    right = np.sum(np.abs(np.fft.rfft(stereo[:, 1] * np.hanning(mono.size)))[band] ** 2)
    difference = 10.0 * np.log10(max(left, 1e-30) / max(right, 1e-30))
    assert abs(difference) <= 1.0


def test_no_gate_module_and_no_gate_failure_type() -> None:
    assert not (PACKAGE / "validate.py").exists()
    for path in PACKAGE.rglob("*.py"):
        assert "GateFailure" not in path.read_text(encoding="utf-8")


def test_the_render_path_imports_nothing_from_compose() -> None:
    for path in PACKAGE.rglob("*.py"):
        if path.parent.name == "compose" or path.name == "cli.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("indiegen.compose")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("indiegen.compose")


def test_compose_imports_no_render_package() -> None:
    for path in (PACKAGE / "compose").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")
                assert not (len(module) > 1 and module[0] == "indiegen" and module[1] in {"synth", "mix", "master"})
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    assert not (len(parts) > 1 and parts[0] == "indiegen" and parts[1] in {"synth", "mix", "master"})
