"""c14: the Director registry and its delegation must not move.

The orbit lives in ``plan_motif`` only. The Director keeps its three motif
shapes, their strategy names and its delegation to ``theory.motif.transform``;
a Director pass must not apply an orbit of its own.
"""

from __future__ import annotations

import importlib
import inspect

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import Plan
from indiegen.theory import motif as motif_module

director_module = importlib.import_module("indiegen.compose.director")


def test_motif_registry_keys_and_names_unchanged() -> None:
    assert set(director_module._MOTIF_SHAPES) == {
        "transpose_motif",
        "invert_motif",
        "retrograde_motif",
    }
    assert director_module.TRANSPOSE_MOTIF == "transpose_motif"
    assert director_module.INVERT_MOTIF == "invert_motif"
    assert director_module.RETROGRADE_MOTIF == "retrograde_motif"


def test_director_delegates_to_theory_transform() -> None:
    assert director_module.motif_transform is motif_module.transform
    for name in ("_shape_transpose", "_shape_invert", "_shape_retrograde"):
        source = inspect.getsource(getattr(director_module, name))
        assert "motif_transform(" in source


def test_director_does_not_reapply_the_orbit() -> None:
    source = inspect.getsource(director_module)
    assert "orbit_element" not in source
    assert "orbit(" not in source

    # A non-motif Director move leaves every motif appearance untouched.
    plan: Plan = director(compose(load_preset("motorik"), 1042, 45 * 44100))
    before = [(a.start_frame, a.transform, a.parameter, tuple(a.notes)) for a in plan.motif_appearances]
    directed = director(plan)
    after = [(a.start_frame, a.transform, a.parameter, tuple(a.notes)) for a in directed.motif_appearances]
    assert after == before
