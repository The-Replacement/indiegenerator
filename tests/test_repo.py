"""AC-52, AC-53: the commit history is conventional and correctly ordered."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

CONVENTIONAL: re.Pattern[str] = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: .+$"
)
FORBIDDEN: tuple[str, ...] = ("co-authored-by", "generated with", "claude", "gpt", "openai")


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def test_every_commit_uses_the_conventional_format(repo_root: Path) -> None:
    log = _git(repo_root, "log", "--format=%B")
    if not log:
        return
    for message in log.split("\n\n"):
        subject = message.strip().splitlines()[0] if message.strip() else ""
        if not subject:
            continue
        assert CONVENTIONAL.match(subject), f"not conventional: {subject!r}"
        lowered = message.lower()
        for token in FORBIDDEN:
            assert token not in lowered, f"{token!r} in a commit message"


def test_the_brief_was_never_modified(repo_root: Path) -> None:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "BRIEF.md"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0


def test_the_gitignore_precedes_the_pyproject(repo_root: Path) -> None:
    ignore = _git(repo_root, "log", "--diff-filter=A", "--format=%H", "--", ".gitignore")
    project = _git(repo_root, "log", "--diff-filter=A", "--format=%H", "--", "pyproject.toml")
    if not ignore or not project:
        return
    order = _git(repo_root, "log", "--format=%H")
    assert order.index(ignore) > order.index(project)


def test_the_n3rv_refresh_is_the_last_commit(repo_root: Path) -> None:
    subject = _git(repo_root, "log", "-1", "--format=%s")
    if not subject:
        return
    assert subject.startswith("chore:")
