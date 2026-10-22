"""AC-12, AC-39, AC-46, AC-47, AC-48, AC-50, AC-51: the architecture, enforced
at the source level so that violations in unexecuted paths are caught too."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

from tests.support.ast_scan import (
    PACKAGE_DIR,
    attribute_chains,
    builtin_calls,
    imported_names,
    iter_modules,
    module_level_mutables,
    relative_to_package,
)

THREAD_CAPS: tuple[str, ...] = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def test_no_print_call_in_the_package() -> None:
    for path, tree in iter_modules():
        assert builtin_calls(tree, "print") == [], f"print() in {relative_to_package(path)}"


def test_no_random_source_outside_compose() -> None:
    for path, tree in iter_modules():
        if path.parent.name == "compose":
            continue
        for name in imported_names(tree):
            assert name != "random"
            assert not name.startswith("numpy.random")
        for chain in attribute_chains(tree):
            assert "random" not in chain.split(".")


def test_no_module_level_mutable_container() -> None:
    for path, tree in iter_modules():
        assert module_level_mutables(tree) == [], f"module level mutable in {relative_to_package(path)}"


def test_the_thread_caps_live_in_exactly_one_file() -> None:
    found: list[str] = []
    for path in PACKAGE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for cap in THREAD_CAPS:
            if cap in text:
                found.append(f"{relative_to_package(path)}:{cap}")
    assert len(found) == len(THREAD_CAPS)
    assert all(entry.startswith("__init__.py:") for entry in found)


def test_the_package_init_imports_nothing_numpy_dependent() -> None:
    tree = ast.parse((PACKAGE_DIR / "__init__.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "numpy"
                assert not alias.name.startswith("numpy.")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "numpy"
            assert not module.startswith("indiegen.")


def test_importing_the_package_does_not_import_numpy() -> None:
    code = (
        "import os, sys\n"
        "import indiegen\n"
        "assert 'numpy' not in sys.modules, sorted(m for m in sys.modules if 'numpy' in m)\n"
        "assert all(os.environ[k] == '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS',"
        " 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'))\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_no_todo_or_fixme_without_an_issue() -> None:
    root = Path(__file__).resolve().parents[1]
    this_file = Path(__file__).resolve()
    targets = [*PACKAGE_DIR.rglob("*.py"), *(root / "tests").rglob("*.py"), *(root / "presets").iterdir()]
    markers = ("TO" + "DO", "FIX" + "ME")
    for path in targets:
        if path.resolve() == this_file:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not any(marker in line for marker in markers):
                continue
            assert re.search(r"#\d+", line), f"{path.name}:{number} has an unlinked TODO"


def test_the_render_path_does_not_import_compose() -> None:
    """cli.py is the orchestrator and legitimately calls compose()."""
    for path, tree in iter_modules():
        relative = relative_to_package(path)
        if relative.startswith("compose/") or path.name in {"cli.py", "batch.py"}:
            continue
        for name in imported_names(tree):
            assert not name.startswith("indiegen.compose")
            assert not name.startswith("compose.")


def test_compose_does_not_import_the_render_path() -> None:
    for path, tree in iter_modules():
        if not relative_to_package(path).startswith("compose/"):
            continue
        for name in imported_names(tree):
            parts = name.split(".")
            if len(parts) > 1 and parts[0] == "indiegen":
                assert parts[1] not in {"synth", "mix", "master", "fx"}
