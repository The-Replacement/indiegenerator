"""c38: the tension walk tracks arrangement fullness (#38).

A quiet, sparse section must read as a tension dip, not a peak. Before the fix
the 240 s motorik-1042 break read T=693 (above its build's 551) because a
single dissonant interval's roughness spike was amplified by beta=5. The fix
confines beta=5 to loudness and drops roughness from the model, so the quiet
sections fall below the 550 admission threshold c9b keys on.
"""

from __future__ import annotations

from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.plan import SAMPLE_RATE

SEED = 1042
SECONDS = 240


def test_the_quiet_sections_are_tension_dips_not_peaks() -> None:
    """motorik 1042 @240s: break and outro sit below build, not above it."""
    plan = director(compose(load_preset("motorik"), SEED, SECONDS * SAMPLE_RATE))
    by_function = {section.function: section for section in plan.sections}

    build = by_function["build"].tension_permille
    assert by_function["break"].tension_permille < build
    assert by_function["outro"].tension_permille < build


def test_the_quiet_sections_stay_below_the_admission_threshold() -> None:
    """motorik 1042 @240s: break/outro < 550, so c9b admits them by density, not 'all'."""
    plan = director(compose(load_preset("motorik"), SEED, SECONDS * SAMPLE_RATE))
    by_function = {section.function: section for section in plan.sections}

    assert by_function["break"].tension_permille < 550
    assert by_function["outro"].tension_permille < 550
