from pathlib import Path
import importlib.util
import sys

import pytest


def sample_instances():
    return [
        {
            "instance_id": "repo__issue-1",
            "repo": "org/repo",
            "base_commit": "abc123",
            "FAIL_TO_PASS": ["tests/test_a.py::test_a"],
            "estimated_runtime": 30,
        },
        {
            "instance_id": "slow__issue-2",
            "repo": "org/slow",
            "base_commit": "def456",
            "FAIL_TO_PASS": ["tests/test_slow.py::test_slow"],
            "estimated_runtime": 120,
        },
        {
            "instance_id": "missing__issue-3",
            "repo": "org/missing",
            "base_commit": "ghi789",
            "FAIL_TO_PASS": [],
        },
    ]


def import_module():
    """Load scripts/import_swebench.py as a module regardless of package layout."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "import_swebench.py"
    spec = importlib.util.spec_from_file_location("import_swebench", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def test_filter_fast_tasks_respects_runtime_and_fail_list():
    mod = import_module()
    picked = mod.filter_fast_tasks(sample_instances(), max_test_time_sec=60, limit=5)
    assert [inst["instance_id"] for inst in picked] == ["repo__issue-1"]


def test_generate_task_yaml(tmp_path: Path):
    mod = import_module()
    inst = sample_instances()[0]
    out_dir = tmp_path / inst["instance_id"]
    task_path = mod.generate_task_yaml(
        inst,
        output_dir=out_dir,
        suite="custom-suite",
        docker_image="img:latest",
        timeout_sec=123,
    )
    text = task_path.read_text()
    assert "task_spec_version" in text
    assert "repo__issue-1" in text
    assert "custom-suite" in text
    assert "pytest -q tests/test_a.py::test_a" in text
    assert "img:latest" in text
    assert "timeout_sec: 123" in text


def test_generate_task_yaml_parses_string_fail_list(tmp_path: Path):
    mod = import_module()
    inst = sample_instances()[0].copy()
    inst["FAIL_TO_PASS"] = '["tests/test_a.py::test_a","tests/test_b.py::test_b"]'
    out_dir = tmp_path / "string_fail_to_pass"
    task_path = mod.generate_task_yaml(inst, output_dir=out_dir)
    text = task_path.read_text()
    assert "pytest -q tests/test_a.py::test_a tests/test_b.py::test_b" in text


def test_main_writes_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = import_module()

    def fake_load():
        return sample_instances()

    monkeypatch.setattr(mod, "load_swebench_lite", fake_load)
    monkeypatch.setattr(sys, "argv", ["import_swebench", "--output-dir", str(tmp_path), "--limit", "2"])

    # Ensure yaml safe_dump is available and not patched away
    assert hasattr(importlib.import_module("yaml"), "safe_dump")

    mod.main()

    generated = sorted(p.name for p in tmp_path.iterdir())
    assert "repo__issue-1" in generated
    # slow task filtered by runtime, missing filtered by empty FAIL_TO_PASS
    assert len(generated) == 1
    task_file = tmp_path / "repo__issue-1" / "task.yaml"
    assert task_file.exists()
