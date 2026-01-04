from agentbench.util.commands import normalize_setup_commands


def test_normalize_setup_commands_adds_target_when_run_command_uses_target():
    commands = ["pip install pytest"]
    run_command = "PYTHONPATH=/workspace/site-packages python -m pytest -q"

    normalized = normalize_setup_commands(commands, run_command=run_command)

    assert normalized == [
        "pip install pytest --target=/workspace/site-packages --upgrade --force-reinstall"
    ]


def test_normalize_setup_commands_skips_target_when_run_command_missing():
    commands = ["pip install pytest"]
    run_command = "pytest -q"

    normalized = normalize_setup_commands(commands, run_command=run_command)

    assert normalized == ["pip install pytest"]


def test_normalize_setup_commands_keeps_explicit_target_without_run_command():
    commands = ["pip install pytest --target=/tmp/site-packages"]
    run_command = "pytest -q"

    normalized = normalize_setup_commands(commands, run_command=run_command)

    assert normalized == [
        "pip install pytest --target=/tmp/site-packages --upgrade --force-reinstall"
    ]
