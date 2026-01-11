## AgentBench

Offline harness for running and evaluating coding agents inside locked-down Docker sandboxes. The project ships a CLI (`ab`), task schema, execution pipeline, tool API for agents, and artifact formats so runs are reproducible and debuggable.

### Repository Layout (high level)
- `agentbench/`: core library (CLI, agent loop, tools, sandbox, schemas, scoring, task loading/validation, utilities)
- `tasks/`: task suites; each task is a `task.yaml` describing repo, setup, run command, labels, and agent budget (see below)
- `examples/toy_repo/`: toy Python project used by sample tasks
- `scripts/`: helper scripts (`benchmark_models.py`, `doctor.sh`, `import_swebench.py`, etc.)
- `docker/py-runner/`: hardened Python runner image definition
- `external/`: vendored references (e.g., `python-ai-sdk-sdk`, `snitchbench`) not required for core harness

### Task Specification (YAML)
Each task is described by `task.yaml` (see `tasks/custom-dev/toy_fail_pytest/task.yaml`):
- `task_spec_version`: currently `"1.0"` (validated in `agentbench/tasks/validation.py`)
- `id`, `suite`: identifiers used in CLI and artifact paths
- `repo`: `{ url, commit }` – repo is cloned and pinned to this commit; relative paths are resolved against the task file location
- `environment`: `{ docker_image, workdir, timeout_sec }` – container image and per-command timeout
- `setup.commands`: ordered shell commands (normalized to persist pip installs into `/workspace/site-packages` unless already targeted)
- `run.command`: test command (e.g., `PYTHONPATH=... python -m pytest -q`)
- `validation` (optional): expectations for baseline failure (exit codes, regex checks, expected failing tests, etc.)
- `agent` (optional): `{ entrypoint, max_steps }` used when running agents (default entrypoint can be overridden via CLI)
- `labels`, `harness_min_version` (optional)

### Core Execution Flows
**Baseline validation (`validate_baseline`)**
- Clones the repo (`git clone`, `git checkout`), resolves relative URLs, and runs setup in Docker with `network=bridge`.
- Runs the task’s test command in Docker with `network=none`; expects a non-zero exit code. Exit codes are mapped to `FailureReason` (e.g., 0 → `BASELINE_NOT_FAILING`, 124/137 → `TIMEOUT`).
- Captures git status/diff to ensure setup didn’t dirty the tree (unless `enforce_clean_setup` is false) and reruns tests if time allows to detect flaky baselines.
- Records artifacts and an `AttemptRecord` via `AttemptContext` into `logs/…/attempts.jsonl`.

**Suite validation (`run_suite`)**
- Loads all tasks in a suite, skips tasks with labels in `skip_labels` (default skips `flaky`), and runs baseline validation per task.
- Writes `runs/<timestamp>__<suite>__baseline/run.json`, per-task logs under `logs/<task_id>/`, and a summary table to the console.

**Task runner (`run_task`)**
- One-off executor for a task: clone, checkout, run setup and tests in Docker, collect metadata (`run.json`) plus logs under `artifacts/runs/<timestamp>__<ulid>/`.

**Agent run (`run_agent_attempt`)**
- Pre-step: optional baseline validation (skipped with `--skip-baseline`).
- Instantiates a sandbox (`DockerSandbox`) and an agent (`ScriptedAgent` or `LLMAgentV0`, or an override via `--variant`).
- Uses `AgentLoop` to orchestrate tool calls, enforce budgets (`max_steps`, `max_time_sec`, `repeated_failure_threshold`), and auto-run tests after patches or before exiting if tests haven’t run recently.
- Maps agent stop reasons to failure taxonomy, logs rich events (`events.jsonl`, optional `llm_messages.jsonl`), and returns an `AttemptRecord` with patch artifacts and exit codes.

### Agents
**ScriptedAgent** (`agentbench/agents/scripted.py`)
- Deterministic sequence used for toy tasks: list files → read known file → search → apply hard-coded patch → run tests.

**LLMAgentV0** (`agentbench/agents/llm_v0.py`)
- Tool-using LLM agent. System prompt in `agents/prompts/system_v1.py` instructs the model to fix tests using minimal changes.
- Defines five tools exposed to the LLM: `list_files`, `read_file`, `search`, `apply_patch`, `run`.
- Parses OpenRouter Responses API outputs (tool calls or plain text). Supports unified diff extraction when the model emits a diff instead of tool calls. Queues multiple tool calls, retries once on malformed JSON tool args.
- Builds observations from `AgentState` (recent tool history, last test output, budgets, patches) and streams requests via `LLMClient`.

### LLM Integration
- Provider support: OpenRouter (Responses API) via `agentbench/llm/openrouter.py`.
- Config via `LLMConfig`/`ProviderConfig`/`SamplingParams`/`RetryPolicy` in `agentbench/llm/config.py`.
- Environment: set `OPENROUTER_API_KEY`; optional `MODEL_NAME` (default `anthropic/claude-3.5-sonnet`), `AGENTBENCH_LOG_LLM_MESSAGES` and `AGENTBENCH_LLM_LOG_MAX_CHARS` to control logging, `AGENTBENCH_STRICT_PATCH` to reject non-standard patches, `AGENTBENCH_FULL_LOGS` to disable stdout/stderr truncation.
- Token counting is approximate (character-based). Errors are normalized to `LLMErrorType` and mapped to failure taxonomy.

### Tooling API (agents call these)
- Implementations in `agentbench/tools/builtins.py` and `agentbench/tools/patching.py`; contract defined in `agentbench/tools/contract.py`.
- `list_files(root=".", glob=None)`: safe glob within workspace (blocks path escape, symlinks, hidden dirs). Timeout 30s.
- `read_file(path, start_line=None, end_line=None)`: reads text with truncation for very large files; returns suggestions if missing; handles directories. Timeout 10s.
- `search(query, glob=None, max_results=50, context_lines=2, is_regex=False)`: uses ripgrep JSON output with context; tolerates no matches; timeout 60s.
- `apply_patch(unified_diff)`: normalizes diff formats unless `AGENTBENCH_STRICT_PATCH=1`; supports Begin Patch/context patches; validates paths to prevent escape; writes patch artifact to `diffs/step_NNNN.patch`.
- `run(command, timeout_sec=None, env=None, network=None)`: executes inside Docker with `network=none` by default; captures stdout/stderr to `logs/tool_step_*.txt`, truncates large output, and returns exit metadata. Setup may rerun automatically before tests if needed.

### Agent Loop Mechanics (`agentbench/agents/loop.py`)
- Initial step runs setup (if provided) then the test command; if tests already pass, exits success early.
- Maintains `AgentState` with history of `ToolRequest`/`ToolResult`, budgets, and last test output.
- Stop conditions: tests passing, step budget exhausted, time budget exhausted, repeated identical failures, or explicit agent stop.
- After `apply_patch`, automatically runs the test command. Before exiting without recent tests, auto-runs tests once.
- Uses `EventLogger` to emit structured events (tool start/finish, tests start/finish, patches, LLM requests) to JSONL.

### Sandbox & Security
- `DockerSandbox` wraps `docker run` with hardening flags (`--cap-drop=ALL`, `--security-opt no-new-privileges`, PID limit, tmpfs `/tmp`).
- Network isolation: setup uses `bridge`; tests/run use `none` (no outbound). Can pass environment overrides.
- Workspaces are mounted at `/workspace` (repo at `/workspace/repo`). Path safety enforced by `sandbox/filesystem.py` (blocks escapes and symlinks).

### Artifacts & Logging
- Runs are organized under `artifacts/`:
  - `runs/<timestamp>__<ulid>/` for `run_task` (includes `run.json`, `logs/`, `workspace/`).
  - `agent_runs/<task_id>/` for agent runs (per-run ULID handled by `run_agent_attempt`; contains `events.jsonl`, optional `llm_messages.jsonl`, `diffs/`, `logs/`, applied patch list).
  - `workspace/<task_id>/` is the working copy for agents.
- `AttemptRecord` schema in `agentbench/schemas/attempt_record.py` (versioned `schema_version="0.1.0"`), with nested `BaselineValidationResult`, `TaskResult`, `LimitsConfig`, and optional `ModelConfig`.
- Failure taxonomy documented in `agentbench/scoring/README.md`; mapping implemented in `agentbench/scoring/taxonomy.py`.

### CLI (`ab`, defined in `agentbench/cli.py`)
- `ab run-task TASK.yaml [--out artifacts]`: clone → setup → run tests, capture artifacts.
- `ab run-agent --task TASK.yaml [--variant scripted|llm_v0] [--out artifacts] [--strict-patch] [--skip-baseline] [--log-llm-messages/--no-log-llm-messages]`: run an agent. `llm_v0` requires `OPENROUTER_API_KEY` (and optional `MODEL_NAME`).
- `ab validate-suite SUITE [--tasks tasks] [--out artifacts] [--include-flaky]`: baseline validation for all tasks in a suite.
- `ab list-tasks SUITE [--tasks tasks]`: list task IDs in a suite.

### Helper Scripts
- `scripts/benchmark_models.py`: run the same task across multiple models (reads `scripts/models.txt` or a custom list), optional probe calls, per-model artifact directories, and summary table/JSON export.
- `scripts/doctor.sh`: environment sanity checks (Docker availability, runner image, network isolation, smoke task).
- `scripts/import_swebench.py`, `scripts/openrouter_call.py`, `scripts/demo_scripted_agent.sh`: dataset/import and convenience helpers.

### Development Notes
- Python ≥3.11. Dependencies in `pyproject.toml`; CLI entry point is `ab`.
- Tests use pytest (filtered to `agentbench/` paths). Default markers exclude `integration`/`docker`.
- Formatting/linting defaults: Ruff with relaxed rules (see `[tool.ruff]` in `pyproject.toml`).
- Docker must be available locally; runner image reference: `ghcr.io/agentbench/py-runner:0.1.0` (see `docker/py-runner/Dockerfile` and README).

### Example Usage
```bash
# Validate sample suite (baseline should fail)
ab validate-suite custom-dev --tasks tasks --out artifacts

# Run scripted agent on toy task (no LLM required)
ab run-agent --task tasks/custom-dev/toy_fail_pytest/task.yaml --variant scripted --out artifacts

# Run LLM agent (requires OPENROUTER_API_KEY)
MODEL_NAME=anthropic/claude-3.5-sonnet \
OPENROUTER_API_KEY=... \
ab run-agent --task tasks/custom-dev/toy_fail_pytest/task.yaml --variant llm_v0 --out artifacts
```
