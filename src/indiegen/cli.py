"""The CLI. Four entry points: render, explain, --help, --version."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from indiegen import __version__
from indiegen.compose import compose, director
from indiegen.config import load_preset
from indiegen.errors import PlanError, RenderError
from indiegen.master.chain import master
from indiegen.master.loudness import measure
from indiegen.metadata import build_tags, filename_for
from indiegen.plan import SAMPLE_RATE, Plan, canonical_json, plan_sha256
from indiegen.render import BLOCK_SIZE, render_plan
from indiegen.validate import check_gate_10, run_gates, stereo_correlation
from indiegen.writer import pcm_sha256, read_pcm, write_flac_atomic, write_sidecar_atomic

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


def _fail(exc: Exception) -> None:
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


def _plan_from_file(path: Path) -> Plan:
    """Read a plan from a sidecar, or from a bare plan document."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanError(f"cannot read plan file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"invalid plan file: {exc}") from exc
    payload = raw.get("plan", raw) if isinstance(raw, dict) else raw
    try:
        plan = Plan.model_validate(payload)
    except ValidationError as exc:
        raise PlanError(f"invalid plan: {exc}") from exc
    stored = raw.get("plan_sha256") if isinstance(raw, dict) else None
    if stored is not None and stored != plan_sha256(plan):
        raise PlanError("plan file does not match its recorded hash")
    return plan


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
                preset=plan.preset,
                seed=seed,
            )
    else:
        name = preset if preset is not None else "station"
        if seed is None:
            raise PlanError("a seed is required", preset=name)
        try:
            loaded = load_preset(name, presets_dir=presets_dir)
        except PlanError as exc:
            raise exc.with_context(preset=name, seed=seed) from exc
        plan = director(compose(loaded, seed, frames))

    started = time.perf_counter()
    mix = render_plan(plan)
    pcm = master(plan, mix, BLOCK_SIZE)
    render_seconds = time.perf_counter() - started

    failure = run_gates(plan, mix, pcm)
    if failure is not None:
        for result in failure.failures:
            typer.echo(
                f"gate {result.gate}: {result.check}: measured {result.measured:.6f} limit {result.limit:.6f}",
                err=True,
            )
        raise typer.Exit(code=2)

    # The gates have looked at the mix; from here on the master is the only
    # copy of the audio that has to be held, and at fifteen minutes the mix
    # is 605 MB of it.
    del mix

    filename = filename_for(plan)
    tags = build_tags(plan)
    path = write_flac_atomic(out, filename, pcm, plan.sample_rate, tags, preset=plan.preset, seed=plan.seed)
    decoded = read_pcm(path)
    measurements = measure(decoded, plan.sample_rate)
    digest = pcm_sha256(decoded)

    # Gate 10: the file on disk has to be the audio that was rendered. The
    # re-run half of the gate is in the tests, where two processes render
    # the same plan and compare their hashes.
    mismatched = check_gate_10(pcm_sha256(pcm), digest)
    if mismatched:
        for result in mismatched:
            typer.echo(
                f"gate {result.gate}: {result.check}: measured {result.measured:.6f} limit {result.limit:.6f}",
                err=True,
            )
        raise typer.Exit(code=2)

    sidecar = write_sidecar_atomic(
        out,
        filename,
        {
            "schema": "indiegen/sidecar/1",
            "preset": plan.preset,
            "seed": plan.seed,
            "lane": plan.lane,
            "plan": plan.model_dump(mode="json"),
            "plan_sha256": plan_sha256(plan),
            "pcm_sha256": digest,
            "measurements": {
                "duration_seconds": plan.duration_frames / plan.sample_rate,
                "integrated_lufs": measurements["integrated_lufs"],
                "sample_peak_dbfs": measurements["sample_peak_dbfs"],
                "true_peak_dbtp": measurements["true_peak_dbtp"],
                "loudness_range_lu": measurements["loudness_range_lu"],
                "stereo_correlation": stereo_correlation(decoded),
                "render_seconds": render_seconds,
            },
        },
        preset=plan.preset,
        seed=plan.seed,
    )

    typer.echo(f"path: {path}")
    typer.echo(f"sidecar: {sidecar}")
    typer.echo(f"duration: {plan.duration_frames / plan.sample_rate:.6f}")
    typer.echo(f"format: FLAC {plan.sample_rate}Hz PCM_16 {plan.channels}ch")
    typer.echo(f"peak: {measurements['sample_peak_dbfs']:.3f} dBFS")
    typer.echo(f"true_peak: {measurements['true_peak_dbtp']:.3f} dBTP")
    typer.echo(f"loudness: {measurements['integrated_lufs']:.3f} LUFS")
    typer.echo(f"loudness_range: {measurements['loudness_range_lu']:.3f} LU")
    typer.echo(f"sections: {plan.section_count}")
    typer.echo(f"techniques: {','.join(plan.techniques)}")
    typer.echo(f"plan_sha256: {plan_sha256(plan)}")
    typer.echo(f"pcm_sha256: {digest}")
    typer.echo(f"render_seconds: {render_seconds:.3f}")


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
        name = preset if preset is not None else "station"
        if seed is None:
            raise PlanError("a seed is required", preset=name)
        try:
            loaded = load_preset(name, presets_dir=presets_dir)
        except PlanError as exc:
            raise exc.with_context(preset=name, seed=seed) from exc
        plan = director(compose(loaded, seed, _frames(minutes, seconds)))
    except (PlanError, RenderError) as exc:
        _fail(exc)
        return
    payload = canonical_json(plan)
    typer.echo(payload.decode("utf-8"), nl=False)
    typer.echo(f"plan_sha256: {plan_sha256(plan)}", err=True)


if __name__ == "__main__":
    app()
