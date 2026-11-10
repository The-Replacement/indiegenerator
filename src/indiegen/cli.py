"""The CLI: render, batch, validate, catalog, install, explain.

Six commands, and the write path is the same for all of them: a temp file,
an fsync and an atomic rename, because Liquidsoap is watching the directory
the tracks land in.

Every domain failure leaves through ``_fail``: plan errors, render errors and
files that will not decode are one line on stderr and a non-zero status, never
a traceback. ``validate`` exits 2 when a gate failed and 1 when a file could
not be read at all.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError

from indiegen import __version__
from indiegen.batch import batch as run_batch
from indiegen.batch import render_track
from indiegen.catalog import build_catalog, write_catalog
from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.errors import DecodeError, PlanError, RenderError
from indiegen.filecheck import check_file
from indiegen.install import install as run_install
from indiegen.plan import SAMPLE_RATE, Plan, canonical_json, plan_sha256
from indiegen.serve import RestartError
from indiegen.serve import run_cycle as run_rotation_cycle
from indiegen.serve import serve as run_server

app = typer.Typer(add_completion=False, name="indiegen", no_args_is_help=True)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Print the version and exit.")] = False,
) -> None:
    """Batch, offline, deterministic music generation."""
    if version:
        typer.echo(f"indiegen {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    """The console script entry point."""
    app()


def _fail(exc: Exception) -> NoReturn:
    """Report an error on stderr and leave with a non-zero status."""
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=1)


def _frames(minutes: float | None, seconds: int | None) -> int | None:
    """The requested duration in frames. --seconds wins over --minutes."""
    if seconds is not None:
        return round(seconds * SAMPLE_RATE)
    if minutes is not None:
        return round(minutes * 60 * SAMPLE_RATE)
    return None


MAX_PLAN_BYTES: int = 10 * 1024 * 1024


def _reject_json_constant(value: str) -> Any:
    raise PlanError(f"invalid JSON constant in plan file: {value}")


def _plan_from_file(path: Path) -> Plan:
    """Read a plan from a sidecar, or from a bare plan document."""
    try:
        if path.stat().st_size > MAX_PLAN_BYTES:
            raise PlanError(f"plan file too large: {path.stat().st_size} bytes")
        text = path.read_text(encoding="utf-8")
        raw: Any = json.loads(text, parse_constant=_reject_json_constant)
    except OSError as exc:
        raise PlanError(f"cannot read plan file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"invalid plan file: {exc}") from exc
    except PlanError:
        raise
    payload = raw.get("plan", raw) if isinstance(raw, dict) else raw
    try:
        plan = Plan.model_validate(payload)
    except ValidationError as exc:
        raise PlanError(f"invalid plan: {exc}") from exc
    stored = raw.get("plan_sha256") if isinstance(raw, dict) else None
    if stored is not None and stored != plan_sha256(plan):
        raise PlanError("plan file does not match its recorded hash")
    return plan


def _composed_plan(
    preset: str | None,
    seed: int | None,
    frames: int | None,
    presets_dir: Path | None,
) -> Plan:
    """Compose and direct a plan, or fail with a message that says why."""
    name = preset if preset is not None else "station"
    if seed is None:
        raise PlanError("a seed is required", preset=name)
    try:
        loaded = load_preset(name, presets_dir=presets_dir)
    except PlanError as exc:
        raise exc.with_context(preset=name, seed=seed) from exc
    return director(compose(loaded, seed, frames))


@app.command()
def render(
    preset: Annotated[str | None, typer.Option("--preset", help="Preset name. Defaults to station.")] = None,
    seed: Annotated[int | None, typer.Option("--seed", help="Seed. Required unless --from-plan is used.")] = None,
    minutes: Annotated[float | None, typer.Option("--minutes", help="Duration in minutes, fractional.")] = None,
    seconds: Annotated[int | None, typer.Option("--seconds", help="Duration in seconds, exact.")] = None,
    out: Annotated[Path, typer.Option("--out", help="Output directory.")] = Path("out"),
    from_plan: Annotated[Path | None, typer.Option("--from-plan", help="Render from a plan sidecar.")] = None,
    presets_dir: Annotated[Path | None, typer.Option("--presets-dir", help="Directory holding the presets.")] = None,
) -> None:
    """Render a track."""
    try:
        _render(preset, seed, minutes, seconds, out, from_plan, presets_dir)
    except (PlanError, RenderError) as exc:
        _fail(exc)


def _render(
    preset: str | None,
    seed: int | None,
    minutes: float | None,
    seconds: int | None,
    out: Path,
    from_plan: Path | None,
    presets_dir: Path | None,
) -> None:
    frames = _frames(minutes, seconds)
    if from_plan is not None:
        plan = _plan_from_file(from_plan)
        if preset is not None and preset != plan.preset:
            raise PlanError(
                f"preset {preset!r} disagrees with the plan's {plan.preset!r}",
                preset=preset,
                seed=plan.seed,
            )
        if seed is not None and seed != plan.seed:
            raise PlanError(
                f"seed {seed} disagrees with the plan's {plan.seed}",
                preset=preset,
                seed=seed,
            )
    else:
        plan = _composed_plan(preset, seed, frames, presets_dir)

    started = time.perf_counter()
    rendered = render_track(plan, out)
    render_seconds = time.perf_counter() - started
    if rendered.failure is not None or rendered.outcome is None:
        for result in rendered.failure.failures if rendered.failure else []:
            typer.echo(
                f"gate {result.gate}: {result.check}: measured {result.measured:.6f} limit {result.limit:.6f}",
                err=True,
            )
        raise typer.Exit(code=2)
    outcome = rendered.outcome

    typer.echo(f"path: {outcome.path}")
    typer.echo(f"sidecar: {outcome.sidecar}")
    typer.echo(f"duration: {plan.duration_frames / plan.sample_rate:.6f}")
    typer.echo(f"format: FLAC {plan.sample_rate}Hz PCM_16 {plan.channels}ch")
    typer.echo(f"form: {plan.form}")
    typer.echo(f"peak: {outcome.sample_peak_dbfs:.3f} dBFS")
    typer.echo(f"true_peak: {outcome.true_peak_dbtp:.3f} dBTP")
    typer.echo(f"loudness: {outcome.integrated_lufs:.3f} LUFS")
    typer.echo(f"loudness_range: {outcome.loudness_range_lu:.3f} LU")
    typer.echo(f"sections: {plan.section_count}")
    typer.echo(f"techniques: {','.join(plan.techniques)}")
    typer.echo(f"plan_sha256: {plan_sha256(plan)}")
    typer.echo(f"pcm_sha256: {outcome.pcm_sha256}")
    typer.echo(f"render_seconds: {render_seconds:.3f}")


@app.command()
def batch(
    preset: Annotated[str, typer.Option("--preset", help="Preset name.")] = "station",
    count: Annotated[int, typer.Option("--count", help="How many tracks.")] = 10,
    seed_base: Annotated[int, typer.Option("--seed-base", help="The first seed.")] = 1000,
    out: Annotated[Path, typer.Option("--out", help="Output directory.")] = Path("out"),
    presets_dir: Annotated[Path | None, typer.Option("--presets-dir", help="Directory holding the presets.")] = None,
) -> None:
    """Render a batch of tracks and write the catalog."""
    try:
        loaded = load_preset(preset, presets_dir=presets_dir)
        result = run_batch(loaded, count, seed_base, out)
    except (DecodeError, PlanError, RenderError, OSError) as exc:
        _fail(exc)
    for track in result.tracks:
        typer.echo(
            f"track: {track.path.name} seed={track.seed} lane={track.lane} form={track.form} "
            f"duration={track.duration_seconds:.1f}s loudness={track.integrated_lufs:.3f}LUFS"
        )
    typer.echo(f"tracks: {len(result.tracks)}")
    typer.echo(f"seeds: {result.seed_base}..{result.seed_base + count - 1}")
    if result.seed_base != result.requested_base:
        typer.echo(f"seed_base: moved from {result.requested_base}; that window did not cover every lane")
    typer.echo(f"catalog: {out / 'catalog.json'}")
    typer.echo(f"total_bytes: {result.catalog.total_bytes}")
    typer.echo(f"duplicate_hashes: {len(result.catalog.duplicate_hashes)}")
    typer.echo(f"batch_seconds: {result.seconds:.3f}")


@app.command()
def catalog(
    directory: Annotated[Path, typer.Option("--dir", help="The directory holding the tracks.")] = Path("out"),
) -> None:
    """Read the sidecars of a directory and write its catalog."""
    if not directory.is_dir():
        typer.echo(f"error: {directory} is not a directory", err=True)
        raise typer.Exit(code=1)
    try:
        built = build_catalog(directory)
        path = write_catalog(directory, built)
    except (PlanError, RenderError, OSError) as exc:
        _fail(exc)
    typer.echo(f"catalog: {path}")
    typer.echo(f"tracks: {len(built.entries)}")
    typer.echo(f"total_bytes: {built.total_bytes}")
    typer.echo(f"duplicate_seeds: {len(built.duplicate_seeds)}")
    typer.echo(f"duplicate_hashes: {len(built.duplicate_hashes)}")
    if built.unsided:
        typer.echo(f"no_sidecar: {len(built.unsided)} flac(s) cannot be catalogued", err=True)
        for name in built.unsided:
            typer.echo(f"  {name}", err=True)
    for duplicate in built.duplicate_hashes:
        typer.echo(f"duplicate: {duplicate['pcm_sha256']} seeds={duplicate['seeds']}")


@app.command()
def validate(
    files: Annotated[list[Path], typer.Argument(help="The tracks to check.")],
    no_codec: Annotated[bool, typer.Option("--no-codec", help="Skip the gates that need ffmpeg.")] = False,
) -> None:
    """Check tracks that are already on disk."""
    failed = False
    broken = False
    for path in files:
        try:
            check = check_file(path, with_codec=not no_codec)
        except (DecodeError, OSError) as exc:
            typer.echo(f"error: {path.name}: {exc}", err=True)
            broken = True
            continue
        for reason in check.skipped:
            typer.echo(f"skipped: {path.name}: {reason}")
        for failure in check.failures:
            typer.echo(
                f"gate {failure.gate}: {path.name}: {failure.check}: "
                f"measured {failure.measured:.6f} limit {failure.limit:.6f}",
                err=True,
            )
        if check.ok:
            typer.echo(f"ok: {path.name}")
        else:
            failed = True
    if failed:
        raise typer.Exit(code=2)
    if broken:
        raise typer.Exit(code=1)


@app.command()
def install(
    directory: Annotated[Path, typer.Option("--dir", help="The directory holding the tracks.")] = Path("out"),
    to: Annotated[Path, typer.Option("--to", help="The directory to install into.")] = Path("out/installed"),
    no_codec: Annotated[bool, typer.Option("--no-codec", help="Skip the gates that need ffmpeg.")] = False,
) -> None:
    """Validate the tracks of a directory and copy the valid ones into the target."""
    try:
        result = run_install(directory, to, with_codec=not no_codec)
    except (DecodeError, PlanError, RenderError, OSError) as exc:
        _fail(exc)
    for path, reason in result.refused:
        typer.echo(f"refused: {path.name}: {reason}", err=True)
    for path, reason in result.skipped:
        typer.echo(f"skipped: {path.name}: {reason}", err=True)
    for path in result.installed:
        typer.echo(f"installed: {path}")
    typer.echo(f"installed: {len(result.installed)}")
    typer.echo(f"refused: {len(result.refused)}")
    typer.echo(f"skipped: {len(result.skipped)}")
    if not result.ok:
        raise typer.Exit(code=2)


@app.command()
def explain(
    preset: Annotated[str | None, typer.Option("--preset", help="Preset name. Defaults to station.")] = None,
    seed: Annotated[int | None, typer.Option("--seed", help="Seed.")] = None,
    minutes: Annotated[float | None, typer.Option("--minutes", help="Duration in minutes, fractional.")] = None,
    seconds: Annotated[int | None, typer.Option("--seconds", help="Duration in seconds, exact.")] = None,
    presets_dir: Annotated[Path | None, typer.Option("--presets-dir", help="Directory holding the presets.")] = None,
) -> None:
    """Print the plan and its hash, and render nothing."""
    try:
        plan = _composed_plan(preset, seed, _frames(minutes, seconds), presets_dir)
    except (PlanError, RenderError) as exc:
        _fail(exc)
    payload = canonical_json(plan)
    typer.echo(payload.decode("utf-8"), nl=False)
    typer.echo(f"plan_sha256: {plan_sha256(plan)}", err=True)


@app.command()
def cycle(
    music_dir: Annotated[Path, typer.Option("--music-dir", help="Radio music directory to replace.")] = Path("/music"),
    preset: Annotated[str, typer.Option("--preset", help="Preset name.")] = "station",
    count: Annotated[int, typer.Option("--count", help="Tracks per cycle.")] = 10,
    seed_base: Annotated[int, typer.Option("--seed-base", help="Base seed.")] = 1000,
    seed_strategy: Annotated[
        str, typer.Option("--seed-strategy", help="Seed strategy: advance, fixed, time.")
    ] = "advance",
    cycle_index: Annotated[int, typer.Option("--cycle-index", help="Cycle index (for advance strategy).")] = 0,
    work_dir: Annotated[Path, typer.Option("--work-dir", help="Working directory for staging.")] = Path(
        "/var/lib/indiegen"
    ),
    restart: Annotated[
        str,
        typer.Option(
            "--restart",
            help="Liquidsoap restart: none | docker:<container> | cmd:<command> | signal:<path>.",
        ),
    ] = "docker:radio-liquidsoap",
    presets_dir: Annotated[Path | None, typer.Option("--presets-dir", help="Directory holding the presets.")] = None,
) -> None:
    """Generate a fresh batch, replace the radio library, and restart Liquidsoap."""
    try:
        result = run_rotation_cycle(
            preset=preset,
            count=count,
            seed_base=seed_base,
            music_dir=music_dir,
            work_dir=work_dir,
            presets_dir=presets_dir,
            restart=restart,
            cycle=cycle_index,
            seed_strategy=seed_strategy,
        )
    except RestartError as exc:
        typer.echo(f"error: library rotated but restart failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except (DecodeError, PlanError, RenderError, OSError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"installed: {len(result.installed)}")
    typer.echo(f"removed: {len(result.removed)}")
    typer.echo(f"seeds: base={result.seed_base} requested={result.requested_base}")
    typer.echo(f"restarted: {result.restarted}")
    typer.echo(f"restart: {result.restart_detail}")
    typer.echo(f"batch_seconds: {result.batch_seconds:.3f}")


@app.command()
def serve(
    music_dir: Annotated[Path, typer.Option("--music-dir", help="Radio music directory to replace.")] = Path("/music"),
    preset: Annotated[str, typer.Option("--preset", help="Preset name.")] = "station",
    count: Annotated[int, typer.Option("--count", help="Tracks per cycle.")] = 10,
    seed_base: Annotated[int, typer.Option("--seed-base", help="Base seed.")] = 1000,
    seed_strategy: Annotated[
        str, typer.Option("--seed-strategy", help="Seed strategy: advance, fixed, time.")
    ] = "advance",
    interval_seconds: Annotated[int, typer.Option("--interval-seconds", help="Seconds between cycles.")] = 21600,
    trigger_file: Annotated[
        Path | None, typer.Option("--trigger-file", help="If this file appears, run a cycle immediately.")
    ] = None,
    run_on_start: Annotated[
        bool,
        typer.Option(
            "--run-on-start/--no-run-on-start",
            help="Run a cycle at startup.",
            envvar="INDIEGEN_RUN_ON_START",
        ),
    ] = True,
    max_cycles: Annotated[int, typer.Option("--max-cycles", help="Stop after N cycles (0 = forever).")] = 0,
    work_dir: Annotated[Path, typer.Option("--work-dir", help="Working directory for staging.")] = Path(
        "/var/lib/indiegen"
    ),
    restart: Annotated[
        str,
        typer.Option(
            "--restart",
            help="Liquidsoap restart: none | docker:<container> | cmd:<command> | signal:<path>.",
        ),
    ] = "docker:radio-liquidsoap",
    presets_dir: Annotated[Path | None, typer.Option("--presets-dir", help="Directory holding the presets.")] = None,
    log_level: Annotated[str, typer.Option("--log-level", help="Logging level.")] = "INFO",
) -> None:
    """Run generation cycles continuously, replacing the radio library each time."""
    import logging

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        run_server(
            preset=preset,
            count=count,
            seed_base=seed_base,
            music_dir=music_dir,
            work_dir=work_dir,
            presets_dir=presets_dir,
            restart=restart,
            interval_seconds=interval_seconds,
            trigger_file=trigger_file,
            seed_strategy=seed_strategy,
            run_on_start=run_on_start,
            max_cycles=max_cycles,
        )
    except (DecodeError, PlanError, RenderError, OSError, ValueError) as exc:
        _fail(exc)


if __name__ == "__main__":
    app()
