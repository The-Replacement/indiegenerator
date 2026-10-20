"""AST helpers. The hygiene gates are source-level, so they catch violations
in code paths the tests never execute."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

PACKAGE_DIR: Path = Path(__file__).resolve().parents[2] / "src" / "indiegen"
RENDER_PATH_MODULES: tuple[str, ...] = (
    "render.py",
    "plan.py",
    "synth",
    "mix",
    "master",
    "metadata.py",
    "writer.py",
)


def source_files(package_dir: Path = PACKAGE_DIR) -> list[Path]:
    """Every python file of the package."""
    return sorted(package_dir.rglob("*.py"))


def parse(path: Path) -> ast.Module:
    """The parsed module of a file."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def iter_modules(package_dir: Path = PACKAGE_DIR) -> Iterator[tuple[Path, ast.Module]]:
    """Every module of the package with its tree."""
    for path in source_files(package_dir):
        yield path, parse(path)


def builtin_calls(tree: ast.Module, name: str) -> list[ast.Call]:
    """Calls to a builtin function, e.g. print."""
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id == name:
            found.append(node)
    return found


def imported_names(tree: ast.Module) -> set[str]:
    """Every name imported by the module, as written in the import statement."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
            for alias in node.names:
                names.add(f"{module}.{alias.name}" if module else alias.name)
    return names


def attribute_chains(tree: ast.Module) -> set[str]:
    """Every dotted attribute chain, e.g. numpy.random.default_rng."""
    chains: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        parts: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            chains.add(".".join(reversed(parts)))
    return chains


def module_level_mutables(tree: ast.Module) -> list[tuple[str, str]]:
    """Module-scope assignments of a mutable container."""
    found: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
            value: ast.expr | None = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id in {"list", "dict", "set", "bytearray"}:
                mutable = value.func.id
            else:
                continue
        elif isinstance(value, ast.List | ast.Dict | ast.Set):
            mutable = type(value).__name__.lower()
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found.append((target.id, mutable))
    return found


def relative_to_package(path: Path, package_dir: Path = PACKAGE_DIR) -> str:
    """The module path of a file, relative to the package root."""
    return path.relative_to(package_dir).as_posix()


def imports_compose(tree: ast.Module) -> bool:
    """Whether the module imports anything from the compose package."""
    for name in imported_names(tree):
        if name.startswith("indiegen.compose") or name.startswith("compose"):
            return True
    return False


def imports_render_packages(tree: ast.Module) -> list[str]:
    """Whether the module imports synth, mix or master."""
    hits: set[str] = set()
    for name in imported_names(tree):
        parts = name.split(".")
        if len(parts) > 1 and parts[0] == "indiegen" and parts[1] in {"synth", "mix", "master"}:
            hits.add(parts[1])
        elif len(parts) > 1 and parts[0] in {"synth", "mix", "master"}:
            hits.add(parts[0])
    return sorted(hits)
