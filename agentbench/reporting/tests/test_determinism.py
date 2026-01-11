from pathlib import Path

from agentbench.reporting.inputs import load_run_dir
from agentbench.reporting.render import (
    render_attempts_csv,
    render_markdown,
    render_summary_csv,
)
from agentbench.reporting.summary import compute_summary
from typer.testing import CliRunner

from agentbench.reporting.cli import report_app


def test_deterministic_outputs(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "run_min"
    inputs = load_run_dir(fixture)
    summary = compute_summary(inputs.attempts)
    summary.run_id = inputs.run_metadata.run_id
    summary.suite = inputs.run_metadata.suite
    summary.variant = inputs.run_metadata.variant
    summary.warnings.extend(inputs.warnings)

    md1 = render_markdown(summary)
    md2 = render_markdown(summary)
    assert md1 == md2

    s_csv1 = render_summary_csv(summary)
    s_csv2 = render_summary_csv(summary)
    assert s_csv1 == s_csv2

    a_csv1 = render_attempts_csv(
        attempts=inputs.attempts,
        run_id=inputs.run_metadata.run_id,
        suite=inputs.run_metadata.suite,
        variant=inputs.run_metadata.variant,
    )
    a_csv2 = render_attempts_csv(
        attempts=inputs.attempts,
        run_id=inputs.run_metadata.run_id,
        suite=inputs.run_metadata.suite,
        variant=inputs.run_metadata.variant,
    )
    assert a_csv1 == a_csv2


def test_strict_mode_warns(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "run_min"
    inputs = load_run_dir(fixture)
    assert inputs.invalid_lines == 1


def test_cli_strict_mode_fails(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "run_min"
    runner = CliRunner()
    result = runner.invoke(
        report_app,
        [
            "summary",
            "--run",
            str(fixture),
            "--out",
            str(tmp_path),
            "--format",
            "md",
            "--strict",
        ],
    )
    assert result.exit_code != 0
