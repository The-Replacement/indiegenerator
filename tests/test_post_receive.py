"""Regression checks for the mainframe receive hook of this repo.

infra#12: ``receive.denyCurrentBranch=updateInstead`` moves the worktree only
when the pushed ref is the branch checked out on the box. The hook must fail
loudly — naming the checked-out branch — for any other branch, for a detached
HEAD, and it must never write deploy evidence for a push that deployed
nothing (a tag).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "scripts" / "post-receive"

DOCKER_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    # Minimal docker stub: every call the hook makes, answered with success.
    case "$*" in
      *" compose "*build*|*" compose "*up*) exit 0 ;;
      *) exit 0 ;;
    esac
    """
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True, check=True)


def _log_line(radio: Path, needle: str) -> bool:
    log = radio / "data" / "indiegen" / "deploy.log"
    if not log.exists():
        return False
    return any(needle in line for line in log.read_text(encoding="utf-8").splitlines())


@pytest.fixture()
def deployment(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A sandbox: bare hub, seed clone, worktree clone with ``updateInstead``
    and the real hook installed; a radio dir with ``.env`` and a docker stub.
    RADIO_DIR is pinned to the sandbox for the duration of the test: the hook
    defaults to $HOME/servers/radio, which on this workstation does not exist
    and must never be created by a test."""
    bare = tmp_path / "hub.git"
    seed = tmp_path / "seed"
    target = tmp_path / "servers" / "indiegenerator"
    radio = tmp_path / "servers" / "radio"
    subprocess.run(("git", "init", "--bare", "-b", "main", str(bare)), capture_output=True, check=True)
    _git("clone", str(bare), str(seed), cwd=tmp_path)
    _git("config", "user.email", "test@example.test", cwd=seed)
    _git("config", "user.name", "post-receive test", cwd=seed)
    (seed / "README.md").write_text("# indiegenerator sandbox\n", encoding="utf-8")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("push", "origin", "main", cwd=seed)
    _git("clone", str(bare), str(target), cwd=tmp_path)
    _git("config", "receive.denyCurrentBranch", "updateInstead", cwd=target)
    hooks = target / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    shutil.copy(HOOK, hooks / "post-receive")
    (hooks / "post-receive").chmod(0o755)

    radio.mkdir(parents=True)
    (radio / "data" / "indiegen").mkdir(parents=True)
    (radio / ".env").write_text("INDIEGEN_AUTO_TRIGGER=0\n", encoding="utf-8")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "docker"
    stub.write_text(DOCKER_STUB, encoding="utf-8")
    stub.chmod(0o755)
    old_path = os.environ["PATH"]
    old_radio_dir = os.environ.get("RADIO_DIR")
    os.environ["PATH"] = f"{stub_dir}{os.pathsep}{old_path}"
    os.environ["RADIO_DIR"] = str(radio)
    yield seed, target, radio
    os.environ["PATH"] = old_path
    if old_radio_dir is None:
        os.environ.pop("RADIO_DIR", None)
    else:
        os.environ["RADIO_DIR"] = old_radio_dir


def _push(seed: Path, target: Path, ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", "push", str(target), ref), cwd=seed, capture_output=True, text=True)


def test_push_to_wrong_branch_fails_the_hook_and_names_checked_out_branch(
    deployment: tuple[Path, Path, Path],
) -> None:
    seed, target, radio = deployment
    _git("checkout", "-b", "feature", cwd=seed)
    (seed / "README.md").write_text("# feature\n", encoding="utf-8")
    _git("commit", "-am", "feature", cwd=seed)
    _git("push", "origin", "feature", cwd=seed)
    pushed = _push(seed, target, "feature")
    # The ref itself lands (a post-receive failure cannot un-land it); the
    # deploy must not happen and the checked-out branch must be named.
    assert pushed.returncode == 0
    assert _log_line(radio, "FAIL: pushed refs/heads/feature but HEAD is on refs/heads/main")
    assert not _log_line(radio, "deploy ready")
    assert not _log_line(radio, "worktree moved to")
    worktree_sha = _git("rev-parse", "HEAD", cwd=target).stdout.strip()
    feature_sha = _git("rev-parse", "feature", cwd=seed).stdout.strip()
    assert worktree_sha != feature_sha


def test_push_to_checked_out_branch_deploys_and_logs_worktree_commit(
    deployment: tuple[Path, Path, Path],
) -> None:
    seed, target, radio = deployment
    (seed / "README.md").write_text("# second\n", encoding="utf-8")
    _git("commit", "-am", "second", cwd=seed)
    _git("push", "origin", "main", cwd=seed)
    pushed = _push(seed, target, "main")
    assert pushed.returncode == 0
    new_sha = _git("rev-parse", "main", cwd=seed).stdout.strip()
    assert _log_line(radio, f"worktree moved to {new_sha}")
    assert _log_line(radio, "deploy ready (no cycle; INDIEGEN_AUTO_TRIGGER=0)")
    assert _git("rev-parse", "HEAD", cwd=target).stdout.strip() == new_sha


def test_push_to_detached_head_fails_loudly(deployment: tuple[Path, Path]) -> None:
    seed, target, radio = deployment
    _git("checkout", "--detach", cwd=target)
    (seed / "README.md").write_text("# third\n", encoding="utf-8")
    _git("commit", "-am", "third", cwd=seed)
    _git("push", "origin", "main", cwd=seed)
    _push(seed, target, "main")
    assert _log_line(radio, "FAIL: HEAD is detached")
    assert not _log_line(radio, "deploy ready")


def test_tag_push_is_not_a_deploy(deployment: tuple[Path, Path]) -> None:
    seed, target, radio = deployment
    _git("tag", "v0-test", cwd=seed)
    _git("push", "origin", "v0-test", cwd=seed)
    _push(seed, target, "v0-test")
    assert not _log_line(radio, "worktree moved to")
    assert not _log_line(radio, "deploy ready")
