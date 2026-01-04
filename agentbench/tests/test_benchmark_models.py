import importlib
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "flags,expected",
    [
        ([], None),
        (["--log-llm-messages"], True),
        (["--no-log-llm-messages"], False),
    ],
)
def test_benchmark_models_log_flags(monkeypatch, tmp_path, flags, expected):
    module = importlib.import_module("scripts.benchmark_models")
    models_path = tmp_path / "models.txt"
    models_path.write_text("openai/gpt-5-mini\n")

    called = []

    def fake_run_agent(
        task_path,
        model,
        out_dir,
        timeout_sec,
        log_llm_messages=None,
        skip_baseline=False,
        strict_patch=False,
    ):
        called.append(log_llm_messages)
        return {
            "model": model,
            "success": True,
            "exit_code": 0,
            "duration_sec": 0.1,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    out_dir = tmp_path / "out"
    argv = [
        "benchmark_models.py",
        "--task",
        "tasks/custom-dev/toy_fail_pytest/task.yaml",
        "--models",
        str(models_path),
        "--out",
        str(out_dir),
        "--probe-mode",
        "none",
    ] + flags
    monkeypatch.setattr(module.sys, "argv", argv)

    module.main()

    assert called == [expected]


def test_benchmark_models_baseline_once(monkeypatch, tmp_path):
    module = importlib.import_module("scripts.benchmark_models")
    models_path = tmp_path / "models.txt"
    models_path.write_text("openai/gpt-5-mini\n")

    baseline_calls = []
    run_calls = []

    def fake_validate_baseline(task, workspace_dir, logs_dir):
        baseline_calls.append((workspace_dir, logs_dir))
        return SimpleNamespace(exit_code=1)

    def fake_run_agent(
        task_path,
        model,
        out_dir,
        timeout_sec,
        log_llm_messages=None,
        skip_baseline=False,
        strict_patch=False,
    ):
        run_calls.append(skip_baseline)
        return {
            "model": model,
            "success": True,
            "exit_code": 0,
            "duration_sec": 0.1,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(module, "validate_baseline", fake_validate_baseline)
    monkeypatch.setattr(module, "load_task", lambda path: object())
    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    out_dir = tmp_path / "out"
    argv = [
        "benchmark_models.py",
        "--task",
        "tasks/custom-dev/toy_fail_pytest/task.yaml",
        "--models",
        str(models_path),
        "--out",
        str(out_dir),
        "--probe-mode",
        "none",
        "--baseline-once",
    ]
    monkeypatch.setattr(module.sys, "argv", argv)

    module.main()

    assert len(baseline_calls) == 1
    assert run_calls == [True]


def test_benchmark_models_skip_baseline(monkeypatch, tmp_path):
    module = importlib.import_module("scripts.benchmark_models")
    models_path = tmp_path / "models.txt"
    models_path.write_text("openai/gpt-5-mini\n")

    baseline_calls = []
    run_calls = []

    def fake_validate_baseline(task, workspace_dir, logs_dir):
        baseline_calls.append((workspace_dir, logs_dir))
        return SimpleNamespace(exit_code=1)

    def fake_run_agent(
        task_path,
        model,
        out_dir,
        timeout_sec,
        log_llm_messages=None,
        skip_baseline=False,
        strict_patch=False,
    ):
        run_calls.append(skip_baseline)
        return {
            "model": model,
            "success": True,
            "exit_code": 0,
            "duration_sec": 0.1,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(module, "validate_baseline", fake_validate_baseline)
    monkeypatch.setattr(module, "load_task", lambda path: object())
    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    out_dir = tmp_path / "out"
    argv = [
        "benchmark_models.py",
        "--task",
        "tasks/custom-dev/toy_fail_pytest/task.yaml",
        "--models",
        str(models_path),
        "--out",
        str(out_dir),
        "--probe-mode",
        "none",
        "--skip-baseline",
    ]
    monkeypatch.setattr(module.sys, "argv", argv)

    module.main()

    assert baseline_calls == []
    assert run_calls == [True]
