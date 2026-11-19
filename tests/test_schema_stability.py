"""c14: no Plan model field may be added or removed.

The orbit is algorithm-only: it changes VALUES in existing fields, never the
schema. This pins a digest of every Plan model's field-name set (measured on
HEAD 4937c5c) plus the exact MotifAppearance key set and the canonical-JSON
key sets of a rendered plan's top level, section and appearance objects.
"""

from __future__ import annotations

import hashlib
import json

import indiegen.plan as plan_module
from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import MotifAppearance, canonical_json

HEAD_FIELD_DIGEST = "71a56d99184130fec7b4bd7483483b07ad7481bd1f26c48de22925f01bad0974"
HEAD_MOTIF_APPEARANCE_KEYS = frozenset({"section_index", "transform", "parameter", "start_frame", "notes", "durations"})
HEAD_PLAN_KEYS = frozenset(json.loads(canonical_json(director(compose(load_preset("motorik"), 1042, 45 * 44100)))))


def test_all_plan_model_field_sets_unchanged() -> None:
    lines = []
    for name in sorted(dir(plan_module)):
        model = getattr(plan_module, name)
        if (
            isinstance(model, type)
            and issubclass(model, plan_module.BaseModel)
            and model.__module__ == plan_module.__name__
        ):
            lines.append(f"{name}:" + ",".join(sorted(model.model_fields)))
    assert hashlib.sha256("\n".join(lines).encode()).hexdigest() == HEAD_FIELD_DIGEST


def test_motif_appearance_key_set_unchanged() -> None:
    assert frozenset(MotifAppearance.model_fields) == HEAD_MOTIF_APPEARANCE_KEYS


def test_canonical_json_key_sets_unchanged() -> None:
    plan = director(compose(load_preset("motorik"), 1042, 45 * 44100))
    doc = json.loads(canonical_json(plan))
    assert frozenset(doc) == HEAD_PLAN_KEYS
    assert doc["sections"] and all(
        frozenset(section) == frozenset(plan_module.SectionPlan.model_fields) for section in doc["sections"]
    )
    assert doc["motif_appearances"] and all(
        frozenset(appearance) == HEAD_MOTIF_APPEARANCE_KEYS for appearance in doc["motif_appearances"]
    )
