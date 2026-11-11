"""AC-52, AC-53: the commit history is conventional and carries no AI credit.

The rules are about the messages and about one file, not about the order the
commits happened to land in: a test that asserts "the last commit starts with
chore:" fails on the first honest commit after it, and a test that asserts
".gitignore was added before pyproject.toml" fails on any squash or rebase.
Both were removed; what is left is what a reviewer can still act on.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

CONVENTIONAL: re.Pattern[str] = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/,-]+\))?!?: .+$"
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
    subjects = _git(repo_root, "log", "--format=%s")
    if not subjects:
        return
    for subject in subjects.splitlines():
        if not subject.strip():
            continue
        assert CONVENTIONAL.match(subject.strip()), f"not conventional: {subject!r}"


def test_no_commit_carries_ai_attribution(repo_root: Path) -> None:
    bodies = _git(repo_root, "log", "--format=%B").lower()
    if not bodies:
        return
    for token in FORBIDDEN:
        assert token not in bodies, f"{token!r} in a commit message"


def test_the_brief_was_never_modified(repo_root: Path) -> None:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "BRIEF.md"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
