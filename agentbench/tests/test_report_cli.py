from pathlib import Path

from typer.testing import CliRunner

from agentbench.cli import app


def _fixture_run_min() -> Path:
    return Path(__file__).parent.parent / "reporting" / "tests" / "fixtures" / "run_min"


def test_report_summary_success(tmp_path: Path):
    fixture = _fixture_run_min()
    runner = CliRunner()
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "report",
            "summary",
            "--run",
            str(fixture),
            "--out",
            str(out_dir),
            "--format",
            "md,csv",
            "--overwrite",
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "report_summary.md").exists()
    assert (out_dir / "report_summary.csv").exists()
    assert (out_dir / "report_attempts.csv").exists()


def test_report_summary_strict_fails(tmp_path: Path):
    fixture = _fixture_run_min()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "report",
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


def test_report_summary_missing_attempts(tmp_path: Path):
    run_dir = tmp_path / "missing"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "report",
            "summary",
            "--run",
            str(run_dir),
        ],
    )
    assert result.exit_code != 0
    assert "attempts.jsonl" in result.output
