"""In-memory variant planners for the CP domain consonance measurement pass.

This helper reads ``src/indiegen/compose/planner.py`` (and, for V3, the
harmony CP solver) and applies anchored textual patches to FRESH in-memory
copies. The repository's production files are never written.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_PLANNER_PATH = _REPO_ROOT / "src" / "indiegen" / "compose" / "planner.py"
_HARMONY_CP_PATH = _REPO_ROOT / "src" / "indiegen" / "theory" / "harmony_cp.py"

VARIANTS: tuple[str, ...] = ("V0", "V1", "V2", "V3")
PLAN_SEEDS_DEFAULT: tuple[int, ...] = (1042, 2000, 3005, 4002, 5000)
GATE_SEEDS_DEFAULT: tuple[int, ...] = (1042, 2000, 3005)
LANES_DEFAULT: tuple[str, ...] = (
    "motorik",
    "kosmische",
    "dub-electronic",
    "indie-noise",
    "ambient",
)

_ORIGINAL_DOMAIN_LINE = "        domain = roots if roots else list(lane.scale_midi)"
_ORIGINAL_TONIC_LINE = "        tonic = root_midi if root_midi in domain else (domain[0] if domain else None)"
_GLOBALS_LINE = '        globals()["_LAST_CP_DOMAIN"] = list(domain)'


def _assert_count(text: str, needle: str, expected: int, label: str) -> None:
    count = text.count(needle)
    if count != expected:
        raise AssertionError(f"{label}: expected {expected} occurrence(s), found {count}")


def _exec_module(source: str, name: str, package: str, origin: Path) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = str(origin)
    module.__package__ = package
    exec(compile(source, str(origin), "exec"), module.__dict__)  # noqa: S102
    return module


def patched_planner(variant: str) -> types.ModuleType:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant!r}")

    source = _PLANNER_PATH.read_text()

    if variant == "V1":
        replacement = "        domain = list(drawn_pool) if drawn_pool else (roots if roots else list(lane.scale_midi))"
        _assert_count(source, _ORIGINAL_DOMAIN_LINE, 1, "V1 domain anchor")
        source = source.replace(_ORIGINAL_DOMAIN_LINE, replacement, 1)
        domain_assignment = replacement
    elif variant == "V2":
        replacement = (
            "        domain = sorted({r for (_, r) in pairs}) if pairs else (roots if roots else list(lane.scale_midi))"
        )
        _assert_count(source, _ORIGINAL_DOMAIN_LINE, 1, "V2 domain anchor")
        source = source.replace(_ORIGINAL_DOMAIN_LINE, replacement, 1)
        domain_assignment = replacement
    elif variant == "V3":
        replacement = (
            "        _cdv_voices = _lane_voices(lane)\n"
            "        from indiegen.theory.scales import chord_pool as _cdv_chord_pool\n"
            "        from indiegen.theory.consonance import chord_dissonance as _cdv_chord_dissonance\n"
            "        _cdv_base = roots if roots else list(lane.scale_midi)\n"
            "        def _cdv_score(_r):\n"
            "            _t = _cdv_chord_pool(lane.scale_midi, _r, intervals, station.chromatic_budget_permille)\n"
            "            return (_cdv_chord_dissonance(_t, _cdv_voices) if _t else 10**9, _r)\n"
            "        domain = sorted(_cdv_base, key=_cdv_score)"
        )
        _assert_count(source, _ORIGINAL_DOMAIN_LINE, 1, "V3 domain anchor")
        source = source.replace(_ORIGINAL_DOMAIN_LINE, replacement, 1)
        _assert_count(source, _ORIGINAL_TONIC_LINE, 1, "V3 tonic anchor")
        source = source.replace(
            _ORIGINAL_TONIC_LINE,
            "        tonic = domain[0] if domain else None",
            1,
        )
        domain_assignment = "        domain = sorted(_cdv_base, key=_cdv_score)"
    else:
        domain_assignment = _ORIGINAL_DOMAIN_LINE

    _assert_count(source, domain_assignment, 1, f"{variant} domain assignment")
    source = source.replace(
        domain_assignment,
        domain_assignment + "\n" + _GLOBALS_LINE,
        1,
    )
    _assert_count(source, _GLOBALS_LINE, 1, f"{variant} globals capture")

    return _exec_module(
        source,
        f"indiegen.compose._cp_domain_planner_{variant.lower()}",
        "indiegen.compose",
        _PLANNER_PATH,
    )


def patched_harmony_cp() -> types.ModuleType:
    source = _HARMONY_CP_PATH.read_text()
    replacements = (
        (
            "    domain_sorted = sorted(set(int(x) for x in domain))",
            "    domain_sorted = list(dict.fromkeys(int(x) for x in domain))",
        ),
        (
            "    domain_sorted = sorted(set(domain_filtered))",
            "    domain_sorted = list(dict.fromkeys(domain_filtered))",
        ),
    )
    for old, new in replacements:
        _assert_count(source, old, 1, "harmony_cp anchor")
        source = source.replace(old, new, 1)
    for _old, new in replacements:
        _assert_count(source, new, 1, "harmony_cp replacement")
    return _exec_module(
        source,
        "indiegen.theory._cp_domain_harmony_cp",
        "indiegen.theory",
        _HARMONY_CP_PATH,
    )


def compose(
    preset: Any,
    seed: int,
    frames: int,
    variant: str = "V0",
) -> tuple[Any, list[int]]:
    import sys as _sys

    module = patched_planner(variant)

    patched_solver = None
    if variant == "V3":
        patched_solver = patched_harmony_cp()

    original_solver = _sys.modules.get("indiegen.theory.harmony_cp")
    try:
        if variant == "V3" and patched_solver is not None:
            _sys.modules["indiegen.theory.harmony_cp"] = patched_solver
        plan = module.compose(preset, seed, frames)
    finally:
        if variant == "V3":
            if original_solver is None:
                _sys.modules.pop("indiegen.theory.harmony_cp", None)
            else:
                _sys.modules["indiegen.theory.harmony_cp"] = original_solver

    domain = list(getattr(module, "_LAST_CP_DOMAIN", []))
    return plan, domain


def director(plan: Any) -> Any:
    from indiegen.compose.director import director as _director

    return _director(plan)


def run_cell(preset: Any, seed: int, frames: int, variant: str = "V0") -> tuple[Any, list[int]]:
    plan, domain = compose(preset, seed, frames, variant)
    return director(plan), domain
