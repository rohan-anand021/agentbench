from pathlib import Path

import typer

from agentbench.reporting.inputs import load_run_dir
from agentbench.reporting.render import (
    default_output_paths,
    render_attempts_csv,
    render_markdown,
    render_summary_csv,
)
from agentbench.reporting.summary import compute_summary

report_app = typer.Typer()


@report_app.command("summary")
def report_summary_cmd(
    run_dir: Path = typer.Option(..., "--run", help="Run directory with attempts.jsonl"),
    out_dir: Path | None = typer.Option(None, "--out", help="Output directory"),
    format: str = typer.Option(
        "md,csv",
        "--format",
        help="Formats: md,csv (csv emits both summary + attempts)",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing files"),
    strict: bool = typer.Option(False, "--strict", help="Fail on malformed records"),
):
    run_dir = Path(run_dir)
    out_dir = Path(out_dir) if out_dir else run_dir

    try:
        inputs = load_run_dir(run_dir)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc))

    if strict and inputs.warnings:
        messages = "; ".join(f"{w.code}:{w.message}" for w in inputs.warnings)
        raise typer.BadParameter(f"Strict mode: warnings present: {messages}")
    summary = compute_summary(inputs.attempts)
    summary.run_id = inputs.run_metadata.run_id
    summary.suite = summary.suite or inputs.run_metadata.suite
    summary.variant = summary.variant or inputs.run_metadata.variant
    summary.warnings.extend(inputs.warnings)

    formats = {f.strip() for f in format.split(",") if f.strip()}
    outputs = default_output_paths(out_dir)

    if "md" in formats:
        md = render_markdown(summary)
        _write_output(outputs["markdown"], md, overwrite)

    if "csv" in formats:
        summary_csv = render_summary_csv(summary)
        attempts_csv = render_attempts_csv(
            attempts=inputs.attempts,
            run_id=inputs.run_metadata.run_id,
            suite=inputs.run_metadata.suite,
            variant=inputs.run_metadata.variant,
        )
        _write_output(outputs["summary_csv"], summary_csv, overwrite)
        _write_output(outputs["attempts_csv"], attempts_csv, overwrite)

    typer.echo("Report generated:")
    if "md" in formats:
        typer.echo(f"- Markdown: {outputs['markdown']}")
    if "csv" in formats:
        typer.echo(f"- Summary CSV: {outputs['summary_csv']}")
        typer.echo(f"- Attempts CSV: {outputs['attempts_csv']}")
    typer.echo(f"Total attempts: {len(inputs.attempts)}")
    typer.echo(f"Pass rate: {summary.overview.pass_rate:.2%}")
    typer.echo(f"Warnings: {len(summary.warnings)}")


def _write_output(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Use --overwrite to replace.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
