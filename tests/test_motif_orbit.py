"""c14: the motif orbit's recorded element round-trips to its own notes.

Scope note (evidence-driven deviation from the literal AC6 wording): the
geodesic voice-leading pass is ON by default (``config.py:747``) and rewrites
motif pluck notes - and the recorded ``MotifAppearance.notes`` with them -
after composition (``planner._appearance_notes``). Even on unmodified HEAD the
final plan's notes do NOT round-trip from the recorded transform (checked:
motorik 1042 @ 45 s, HEAD worktree). The contract therefore belongs at the
``plan_motif`` boundary, before the voice-leading pass, and is tested there.
"""

from __future__ import annotations

from indiegen.compose.context import TechniqueContext
from indiegen.compose.rng import SplitMix64
from indiegen.compose.techniques.t14_motif import StringVoice, plan_motif
from indiegen.plan import Rational
from indiegen.theory.motif import TRANSFORMS, Cell, orbit, orbit_element, transform

# Canonical transform names the orbit may record (T_n / I_n / R / RI families).
CANONICAL = frozenset(
    {
        "transpose",
        "T",
        "T_n",
        "transpose_n",
        "invert",
        "I",
        "I_n",
        "retrograde",
        "R",
        "retrograde_inversion",
        "RI",
        "retrograde_invert",
    }
)
DURATION_FRAMES = 45 * 44100

# Non-degenerate base cell: a constant cell would make inversion and
# retrograde indistinguishable and weaken the round-trip proof.
BASE_CELL: Cell = [(60, 100), (64, 200), (67, 100), (71, 200)]


def _appearances():  # type: ignore[no-untyped-def]
    """The un-voice-led appearances produced by plan_motif at 45 s."""
    roots = [48, 50, 52, 53, 55, 57, 59, 60]
    boundaries = [DURATION_FRAMES * index // len(roots) for index in range(len(roots) + 1)]
    boundaries[-1] = DURATION_FRAMES
    ctx = TechniqueContext(
        preset="motorik",
        seed=1042,
        lane="motorik",
        scale_midi=list(range(48, 72)),
        root_midi=48,
        sample_rate=44100,
        duration_frames=DURATION_FRAMES,
        frames_per_beat=0,
        frames_per_bar=0,
        attack_frames=0,
        release_frames=0,
        section_boundaries=boundaries,
        section_densities=[1000] * len(roots),
        section_scales=[list(range(48, 72)) for _ in roots],
        section_roots=roots,
        section_functions=["a"] * len(roots),
        section_ic_bands=[],
    )
    string = StringVoice(
        feedback_numerator=1,
        feedback_denominator=1,
        brightness=Rational(numerator=1, denominator=1),
        pluck_position_permille=500,
        detune_cents=0,
    )
    appearances, _ = plan_motif(BASE_CELL, string, ctx, SplitMix64(1042))
    return appearances, ctx


def test_composed_string_roundtrip() -> None:
    """Amended AC6: orbit-derived strings are canonical; augment/fragment keep HEAD strings."""
    appearances, ctx = _appearances()
    assert len(appearances) >= 6

    non_identity = [app for app in appearances if app.transform != "identity"]
    assert len(non_identity) >= 5
    for app in non_identity:
        axis = ctx.section_roots[app.section_index]
        recorded = list(zip(app.notes, app.durations, strict=True))
        # Every non-identity appearance round-trips exactly - notes AND durations.
        assert transform(app.transform, BASE_CELL, app.parameter, axis) == recorded
        if app.transform in ("augment", "fragment"):
            # Non-invertible: never an orbit generator, keeps its HEAD string.
            continue
        assert app.transform in CANONICAL, app.transform

    # The recorded strings are the composed canonical elements: invert and
    # retrograde bases are recorded as T_n and I_n respectively, while the
    # non-invertible augment/fragment statements keep their HEAD strings.
    assert [app.transform for app in non_identity[:5]] == [
        "transpose",
        "transpose",
        "I_n",
        "augment",
        "fragment",
    ]


def test_single_identity() -> None:
    """AC4: statement 0 is the only identity; no step-6 second identity."""
    appearances, _ = _appearances()
    identities = [app for app in appearances if app.transform == "identity"]
    assert len(identities) == 1
    assert appearances[0].transform == "identity"

    # For every orbit the helper uses, no returned cell equals the base.
    final, name, parameter, axis = orbit_element(BASE_CELL, "transpose", 0, 48, 6)
    assert name in CANONICAL
    assert final != BASE_CELL
    for generator in (("transpose", 2, 0), ("I_n", 3, 0), ("RI", 0, 4)):
        tail = orbit(BASE_CELL, *generator)[1:]
        assert BASE_CELL not in tail
    assert TRANSFORMS[0] == "transpose"


def test_statement_zero_is_verbatim() -> None:
    """The identity statement records the cell unchanged."""
    appearances, _ = _appearances()
    first = appearances[0]
    assert first.transform == "identity"
    assert first.parameter == 0
    assert list(zip(first.notes, first.durations, strict=True)) == BASE_CELL
