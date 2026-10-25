"""L07 (graduated spike): pad envelope segments - amplitude-permutation switch.

Spike evidence (/tmp/opencode/spike_l07.py): mean |centroid delta| 76.29 Hz
(epsilon 20) with gate 6 green - row survives. These tests pin the landed
mechanism: default no-op bit-identity, plan-log shape validation, and the
carry-state determinism the report demands (the switch touches weights only;
phase carries cross block boundaries unchanged).
"""

from __future__ import annotations

import numpy as np
import pytest

from indiegen.compose.director import director
from indiegen.compose.planner import compose
from indiegen.config import Preset, load_preset
from indiegen.errors import PlanError
from indiegen.plan import PadEnvelopeSegment, PadEvent, Plan
from indiegen.synth.pad import pad_state, render_pad_block


def _make_segmented_preset() -> Preset:
    preset = load_preset("motorik")
    lanes = list(preset.lanes)
    entry = lanes[0]
    cards = [
        c if c.kind != "pad" else c.model_copy(update={"envelope_segments": 4}) for c in entry.parameters.techniques
    ]
    new_entry = entry.model_copy(update={"parameters": entry.parameters.model_copy(update={"techniques": cards})})
    lanes[0] = new_entry
    return preset.model_copy(update={"lanes": lanes})


def _segmented_pad(plan: Plan) -> PadEvent:
    return next(e for e in plan.events if isinstance(e, PadEvent) and e.envelope_segments)


def test_default_presets_declare_no_segments() -> None:
    plan = director(compose(load_preset("motorik"), 1042, 5 * 44100))
    pads = [e for e in plan.events if isinstance(e, PadEvent)]
    assert pads and all(not p.envelope_segments for p in pads)


def test_segmented_plan_has_permutations_and_weighted_partials() -> None:
    plan = director(compose(_make_segmented_preset(), 1042, 10 * 44100))
    event = _segmented_pad(plan)
    assert len(event.envelope_segments) == 4
    size = len(event.partials)
    for segment in event.envelope_segments:
        assert sorted(segment.permutation) == list(range(size))
        assert segment.delta_frames >= 1
    assert event.partials[-1].amplitude_millibels < event.partials[0].amplitude_millibels


def test_bad_permutation_rejected() -> None:
    plan = director(compose(load_preset("motorik"), 1042, 5 * 44100))
    pad = next(e for e in plan.events if isinstance(e, PadEvent))
    broken = PadEnvelopeSegment(delta_frames=100, permutation=[0, 0])
    with pytest.raises((PlanError, ValueError)):
        type(pad).model_validate({**pad.model_dump(), "envelope_segments": [broken.model_dump()]})


def test_segmented_restart_from_stated_block_bit_identical() -> None:
    plan = director(compose(_make_segmented_preset(), 1042, 10 * 44100))
    event = _segmented_pad(plan)
    total = event.duration_frames
    for cut in (1, 1000, total // 5, total // 2):
        full, _ = render_pad_block(event, plan.sample_rate, 0, total, pad_state(event))
        first, state = render_pad_block(event, plan.sample_rate, 0, cut, pad_state(event))
        second, _ = render_pad_block(event, plan.sample_rate, cut, total, state)
        split = np.concatenate([first, second])
        assert np.array_equal(full, split), f"split at {cut} not bit-identical"


def test_no_segments_path_bit_identical_to_plain_sine_stack() -> None:
    plan = director(compose(load_preset("motorik"), 1042, 5 * 44100))
    pad = next(e for e in plan.events if isinstance(e, PadEvent))
    voice, _ = render_pad_block(pad, plan.sample_rate, 0, 4096, pad_state(pad))
    assert np.all(np.isfinite(voice))
    assert not pad.envelope_segments
