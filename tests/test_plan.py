"""AC-31, AC-34, AC-35, AC-36: the Plan is data, integer only, and reproducible."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from indiegen.errors import PlanError
from indiegen.plan import Plan, canonical_json, plan_sha256, reject_non_integer_leaves
from tests.conftest import GOLDEN_DIR


def test_canonical_json_recipe(reference_plan: Plan) -> None:
    expected = json.dumps(
        reference_plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    assert canonical_json(reference_plan) == expected
    assert plan_sha256(reference_plan) == hashlib.sha256(expected).hexdigest()


def test_hashes_are_functions_not_fields(reference_plan: Plan) -> None:
    dumped = reference_plan.model_dump()
    assert "plan_sha256" not in dumped
    assert "pcm_sha256" not in dumped


def test_golden_canonical_bytes(reference_plan: Plan) -> None:
    golden = GOLDEN_DIR / "plan_station_1042.json"
    digest_file = GOLDEN_DIR / "plan_station_1042.sha256"
    assert golden.is_file()
    assert digest_file.is_file()
    assert canonical_json(reference_plan) == golden.read_bytes()
    assert plan_sha256(reference_plan) == digest_file.read_text().strip()


@pytest.mark.parametrize("bad", [1.0, True, "4"])
def test_strict_int_fields_reject_non_ints(reference_plan: Plan, bad: Any) -> None:
    payload = reference_plan.model_dump()
    payload["seed"] = bad
    with pytest.raises(ValidationError):
        Plan.model_validate(payload)


def test_walker_rejects_float_leaf() -> None:
    with pytest.raises(PlanError):
        reject_non_integer_leaves({"a": {"b": 1.0}})


def test_walker_rejects_bool_leaf() -> None:
    with pytest.raises(PlanError):
        reject_non_integer_leaves({"a": [True]})


def test_walker_rejects_decimal_leaf() -> None:
    with pytest.raises(PlanError):
        reject_non_integer_leaves({"a": Decimal("1.5")})


def test_walker_accepts_ints_and_strings() -> None:
    reject_non_integer_leaves({"a": 1, "b": "text", "c": [1, 2], "d": (3, 4)})


def test_plan_declares_no_clock_field(reference_plan: Plan) -> None:
    for name in type(reference_plan).model_fields:
        assert not re.search(r"date|time|clock|today|now|timestamp", name, re.IGNORECASE)


def test_two_dumps_are_byte_identical(reference_plan: Plan) -> None:
    assert canonical_json(reference_plan) == canonical_json(reference_plan)
