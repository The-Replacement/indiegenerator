"""The radio server: generate, rotate, and keep the stream fed.

One cycle renders a fresh batch into a staging area, publishes the new tracks
into the radio's music directory, removes every track that is no longer in the
new set, and asks Liquidsoap to reload its in-memory playlist. Liquidsoap's
watch mode picks additions up on its own but keeps deletions in memory, so a
rotation without a restart leaves ghosts on air; this module does both, in
that order.

Nothing here restarts the radio stack. The only container it ever touches is
Liquidsoap, and only when a restart mechanism is configured.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from indiegen.batch import batch as run_batch
from indiegen.config import load_preset
from indiegen.writer import publish_atomically, staging_dir

log = logging.getLogger("indiegen.serve")

TRACK_SUFFIXES: tuple[str, ...] = (".flac", ".json")
CATALOG_NAME: str = "catalog.json"


@dataclass(frozen=True)
class CycleResult:
    """What one rotation did."""

    installed: list[str]
    removed: list[str]
    restarted: bool
    restart_detail: str
    seed_base: int
    requested_base: int
    batch_seconds: float


@dataclass
class ServeState:
    """Mutable state carried across cycles."""

    cycle: int = 0
    failures: int = 0
    last: CycleResult | None = field(default=None)


STATE_FILE: str = "state.json"


def state_path(work_dir: Path) -> Path:
    """Where the server persists its cycle state."""
    return work_dir / STATE_FILE


def load_state(work_dir: Path) -> ServeState:
    """Load persisted cycle state, or a fresh state if none exists."""
    path = state_path(work_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ServeState()
    except OSError, json.JSONDecodeError, ValueError, TypeError:
        log.warning("could not read state %s; starting fresh", path)
        return ServeState()
    if not isinstance(raw, dict):
        return ServeState()
    cycle = raw.get("cycle", 0)
    failures = raw.get("failures", 0)
    if not isinstance(cycle, int) or cycle < 0:
        cycle = 0
    if not isinstance(failures, int) or failures < 0:
        failures = 0
    return ServeState(cycle=cycle, failures=failures)


def save_state(work_dir: Path, state: ServeState, *, extra: dict[str, Any] | None = None) -> None:
    """Persist cycle state atomically."""
    work_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    payload: dict[str, Any] = {
        "schema": "indiegen/serve-state/1",
        "cycle": state.cycle,
        "failures": state.failures,
        "updated_at": time.time(),
    }
    if extra:
        payload.update(extra)
    target = state_path(work_dir)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)


class RestartError(RuntimeError):
    """Liquidsoap could not be restarted.

    The library was already rotated on disk; the error is reported so the
    operator can see that the playlist in memory still holds the old set.
    """


def _managed_names(music_dir: Path) -> set[str]:
    """Files in the music root that this generator owns."""
    names: set[str] = set()
    for suffix in TRACK_SUFFIXES:
        for path in music_dir.glob(f"*{suffix}"):
            if path.is_file() and path.parent == music_dir:
                names.add(path.name)
    catalog = music_dir / CATALOG_NAME
    if catalog.is_file():
        names.add(CATALOG_NAME)
    return names


def _publish_file(source: Path, target_dir: Path) -> None:
    """Copy a file into a watched directory, atomically."""
    target = target_dir / source.name
    temp_path = staging_dir(target_dir) / source.name
    try:
        shutil.copyfile(source, temp_path, follow_symlinks=False)
        publish_atomically(temp_path, target)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def rotate_library(staged_dir: Path, music_dir: Path) -> tuple[list[str], list[str]]:
    """Replace the music library with the contents of a staged batch.

    New files are published first, then every managed file that is not part
    of the new set is removed. Publishing first keeps the directory from
    going empty between the delete and the copy: Liquidsoap is ``mksafe``,
    but an empty window is still silence.
    """
    music_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

    fresh: dict[str, Path] = {}
    for suffix in (*TRACK_SUFFIXES,):
        for path in staged_dir.glob(f"*{suffix}"):
            if path.is_file() and path.parent == staged_dir:
                fresh[path.name] = path
    catalog = staged_dir / CATALOG_NAME
    if catalog.is_file():
        fresh[CATALOG_NAME] = catalog
    if not fresh:
        raise ValueError(f"staged batch is empty: {staged_dir}")

    installed: list[str] = []
    for name in sorted(fresh):
        _publish_file(fresh[name], music_dir)
        installed.append(name)

    removed: list[str] = []
    stale = sorted(_managed_names(music_dir) - set(fresh))
    for name in stale:
        path = music_dir / name
        try:
            path.unlink()
            removed.append(name)
        except FileNotFoundError:
            continue

    return installed, removed


def restart_liquidsoap(mode: str) -> tuple[bool, str]:
    """Restart Liquidsoap so it forgets deleted tracks.

    ``mode`` is one of:
    - ``none``: do nothing (the operator restarts manually).
    - ``docker:<name>``: ``docker restart <name>`` via the Docker socket.
    - ``cmd:<command>``: run an explicit shell command.
    - ``signal:<path>``: touch a file; an out-of-band watcher acts on it.
    """
    if mode == "none" or not mode:
        return False, "restart skipped (mode=none)"
    if mode.startswith("docker:"):
        container = mode.split(":", 1)[1].strip()
        if not container:
            raise RestartError("docker restart mode needs a container name (docker:<name>)")
        cmd = ["docker", "restart", container]
        completed = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, check=False, timeout=120
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RestartError(f"docker restart {container} failed: {detail}")
        return True, f"restarted container {container}"
    if mode.startswith("cmd:"):
        command = mode.split(":", 1)[1]
        completed = subprocess.run(  # noqa: S602
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RestartError(f"restart command failed: {detail}")
        return True, f"ran restart command: {command}"
    if mode.startswith("signal:"):
        path = Path(mode.split(":", 1)[1])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(time.time()), encoding="utf-8")
        return True, f"wrote restart signal: {path}"
    raise RestartError(f"unknown restart mode: {mode!r}")


def _seed_base_for_cycle(base: int, count: int, cycle: int, strategy: str) -> int:
    if strategy == "fixed":
        return base
    if strategy == "advance":
        return base + cycle * max(count, 1)
    if strategy == "time":
        window = max(count, 1)
        return base + (int(time.time()) // 60) * window
    raise ValueError(f"unknown seed strategy: {strategy!r}")


def run_cycle(
    *,
    preset: str,
    count: int,
    seed_base: int,
    music_dir: Path,
    work_dir: Path,
    presets_dir: Path | None,
    restart: str,
    cycle: int = 0,
    seed_strategy: str = "advance",
) -> CycleResult:
    """Generate one batch and rotate the radio library."""
    run_root = work_dir / "runs" / f"cycle-{cycle:06d}-{int(time.time())}"
    stage = run_root / "batch"
    stage.mkdir(parents=True, exist_ok=True)

    requested_base = _seed_base_for_cycle(seed_base, count, cycle, seed_strategy)
    loaded = load_preset(preset, presets_dir=presets_dir)
    result = run_batch(loaded, count, requested_base, stage)

    installed, removed = rotate_library(stage, music_dir)

    # Replace catalog in music dir with the staged one (already published via
    # rotate_library if present). Remove the run staging to bound disk use.
    shutil.rmtree(run_root, ignore_errors=True)

    restarted, detail = restart_liquidsoap(restart)
    return CycleResult(
        installed=installed,
        removed=removed,
        restarted=restarted,
        restart_detail=detail,
        seed_base=result.seed_base,
        requested_base=requested_base,
        batch_seconds=result.seconds,
    )


def run_once_trigger(path: Path) -> bool:
    """Consume a trigger file if present."""
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        log.warning("could not consume trigger %s", path)
        return False
    return True


def serve(
    *,
    preset: str,
    count: int,
    seed_base: int,
    music_dir: Path,
    work_dir: Path,
    presets_dir: Path | None,
    restart: str,
    interval_seconds: int,
    trigger_file: Path | None,
    seed_strategy: str = "advance",
    run_on_start: bool = True,
    max_cycles: int = 0,
) -> None:
    """Run generation cycles forever (or until max_cycles)."""
    state = load_state(work_dir)
    next_at = time.monotonic() + (0.0 if run_on_start else float(interval_seconds))
    log.info(
        "serve start preset=%s count=%s music=%s interval=%ss restart=%s cycle=%s state=%s",
        preset,
        count,
        music_dir,
        interval_seconds,
        restart,
        state.cycle,
        state_path(work_dir),
    )
    while True:
        if max_cycles > 0 and state.cycle >= max_cycles:
            log.info("serve stop after %s cycles", state.cycle)
            return

        triggered = trigger_file is not None and run_once_trigger(trigger_file)
        now = time.monotonic()
        if not triggered and now < next_at:
            time.sleep(min(1.0, next_at - now))
            continue

        try:
            outcome = run_cycle(
                preset=preset,
                count=count,
                seed_base=seed_base,
                music_dir=music_dir,
                work_dir=work_dir,
                presets_dir=presets_dir,
                restart=restart,
                cycle=state.cycle,
                seed_strategy=seed_strategy,
            )
            state.last = outcome
            state.cycle += 1
            save_state(
                work_dir,
                state,
                extra={
                    "last_seed_base": outcome.seed_base,
                    "last_requested_base": outcome.requested_base,
                    "last_installed": len(outcome.installed),
                    "last_removed": len(outcome.removed),
                    "last_restarted": outcome.restarted,
                },
            )
            log.info(
                "cycle=%s installed=%s removed=%s restarted=%s seeds=%s.. detail=%s %.2fs",
                state.cycle,
                len(outcome.installed),
                len(outcome.removed),
                outcome.restarted,
                outcome.seed_base,
                outcome.restart_detail,
                outcome.batch_seconds,
            )
        except RestartError as exc:
            # Library rotated; restart failed. Count the cycle but surface the
            # problem loudly so the operator sees Liquidsoap is stale.
            state.cycle += 1
            state.failures += 1
            save_state(work_dir, state, extra={"restart_error": str(exc)})
            log.error("cycle=%s restart failed after rotation: %s", state.cycle, exc)
        except Exception:
            state.failures += 1
            save_state(work_dir, state, extra={"last_error": "generation failed"})
            log.exception("cycle=%s failed; will retry next interval", state.cycle)

        next_at = time.monotonic() + float(interval_seconds)
