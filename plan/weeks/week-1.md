# Week 1: Skeleton + Docker Runner

## Goal
By end of week: Run a single task (repo + pytest) inside Docker, capture all output to artifacts, and prove determinism by running twice and comparing results.

---

## Day 1 (Monday): Environment Setup + Project Skeleton

### Prerequisites Verification
- [x] Verify Docker Desktop is installed and running (`docker ps` works)
- [x] Verify Docker can run containers (`docker run --rm hello-world`)
- [x] Verify git is installed and configured
- [x] Verify Python 3.11+ is available
- [x] Install uv if not already installed (via official install script)
- [x] Verify uv works (`uv --version`)

### Project Initialization
- [x] Create the project root directory structure:
  - `agentbench/` (Python package)
  - `agentbench/sandbox/`
  - `agentbench/util/`
  - `agentbench/schemas/`
  - `docker/py-runner/`
  - `tasks/custom-dev/`
  - `artifacts/`
  - `scripts/`
  - `tests/`
  - `configs/`

- [x] Create `pyproject.toml` with:
  - Project name: `agentbench-py`
  - Version: `0.1.0`
  - Python requirement: `>=3.11`
  - Dependencies: typer, rich, pydantic, pydantic-settings, httpx, pyyaml, ulid-py, path, pytest, ulid
  - Dev dependencies: pytest, ruff
  - Script entry point: `agentbench = "agentbench.cli:app"` *(changed from `ab` to `agentbench`)*
  - Ruff config: line-length 80, select E/F/I/UP/B
  - Build system: hatchling
  - uv workspace includes `examples/toy_repo`

- [x] Create `.python-version` file with `3.11`

- [x] Create `.gitignore` with:
  - `.venv/`
  - `__pycache__/`
  - `*.pyc`
  - `artifacts/`
  - `.DS_Store`
  - `.env`
  - `uv.lock`

- [ ] Create `.env.example` with `OPENROUTER_API_KEY=replace_me` *(not yet created - not needed for Week 1)*

- [x] Initialize git repository
- [x] Run `uv venv --python 3.11` to create virtual environment
- [x] Run `uv sync` to install dependencies
- [x] Verify installation: `uv run python -c "import typer, yaml, pydantic"`

### End of Day 1 Checkpoint
- [x] `uv run python -c "import typer"` succeeds
- [x] Directory structure exists
- [x] Git repo initialized with first commit

---

## Day 2 (Tuesday): Docker Runner Image + Basic CLI

### Docker Runner Image
- [x] Create `docker/py-runner/Dockerfile`:
  - Base image: `python:3.11-slim`
  - Install system packages: git, build-essential (for compiling pip packages)
  - Create non-root user `runner` with UID 1000
  - Set working directory to `/workspace`
  - Set environment variables:
    - `PIP_DISABLE_PIP_VERSION_CHECK=1`
    - `PIP_NO_INPUT=1`
    - `PYTHONDONTWRITEBYTECODE=1`
    - `PYTHONUNBUFFERED=1`

- [x] Build the image: tag as `ghcr.io/agentbench/py-runner:0.1.0`
- [x] Test the image: run `python -V` inside container
- [x] Test the image: verify it runs as non-root user
- [x] Document the image in `docker/py-runner/README.md`:
  - What's included
  - How to build
  - How to verify

### Minimal CLI Skeleton
- [x] Create `agentbench/__init__.py` (empty, makes it a package)
- [x] Create `agentbench/cli.py`:
  - Initialize Typer app with `no_args_is_help=True`
  - Add `run-task` command that accepts:
    - `--task` (path to task.yaml, required)
    - `--out` (output directory, defaults to `artifacts`)
  - Command calls `run_task()` and prints the result path

- [x] Verify CLI works: `uv run agentbench --help` shows help *(note: command is `agentbench`, not `ab`)*
- [x] Verify CLI works: `uv run agentbench run-task --help` shows command help

### End of Day 2 Checkpoint
- [x] Docker image builds successfully
- [x] `docker run --rm ghcr.io/agentbench/py-runner:0.1.0 python -V` outputs Python 3.11.x
- [x] `docker run --rm ghcr.io/agentbench/py-runner:0.1.0 whoami` outputs `runner`
- [x] `uv run agentbench --help` shows CLI help

---

## Day 3 (Wednesday): Utility Modules + Docker Sandbox Class

### Utility Module: Paths
- [x] Create `agentbench/util/__init__.py`
- [x] Create `agentbench/util/paths.py`:
  - Function `ensure_dir(path: Path) -> Path`: creates directory if not exists, returns path
  - This is a simple helper used everywhere

### Docker Sandbox Module
- [x] Create `agentbench/sandbox/__init__.py`
- [x] Create `agentbench/sandbox/docker_sandbox.py`:
  - Define `DockerRunResult` dataclass with fields:
    - `exit_code: int`
    - `stdout_path: Path`
    - `stderr_path: Path`
  
  - Define `DockerSandbox` class:
    - Constructor takes `image: str` and `workdir: str` (default `/workspace`)
    - Method `run()` that:
      - Accepts: `workspace_host_path`, `command`, `network`, `timeout_sec`, `stdout_path`, `stderr_path`
      - Validates network is `"none"` or `"bridge"`
      - Builds docker run command with:
        - `--rm` (auto-remove container)
        - `--network` flag (none/bridge)
        - Volume mount: host workspace → container workdir
        - Working directory set to workdir
        - Command executed via `bash -lc` (login shell for proper env)
      - Executes via `subprocess.run()`
      - Captures stdout/stderr to the specified file paths
      - Handles timeout: if `subprocess.TimeoutExpired`, write timeout marker to stderr, return exit code 124
      - Returns `DockerRunResult`

### Test the Sandbox
- [x] Create sandbox tests in `agentbench/sandbox/tests/sandbox_test.py`:
  - Test Python version check
  - Test exit code capture
  - Uses pytest fixtures

### End of Day 3 Checkpoint
- [x] `DockerSandbox.run()` can execute commands in container
- [x] stdout/stderr are captured to files
- [x] Timeout handling works (test with `sleep` command and short timeout)
- [x] Exit codes are captured correctly

---

## Day 4 (Thursday): Toy Repo + Task Spec + Task Runner

### Create Toy Test Repository
- [x] Create `examples/toy_repo/` directory
- [x] Initialize as part of uv workspace
- [x] Create structure:
  - `pyproject.toml` (minimal, with hatchling)
  - `src/toy/__init__.py`
  - `src/toy/mathy.py` with a function `add(a, b)` that's intentionally broken (returns `a - b`)
  - `tests/test_basic.py` with failing test

- [x] Commit everything and record the commit SHA: `a3219a9adc9f143c379d38d76a77cd969380f90d`
- [x] Verify: running pytest on this repo should FAIL (this is intentional)

### Task Spec for Toy Repo

**Schema Change**: The task.yaml schema has been simplified from the spec:

| Spec Schema | Implemented Schema |
|-------------|-------------------|
| `environment.network_policy` | Removed - network is hardcoded (setup: bridge, run: none) |
| `validation.failing_command` | Replaced with `run.command` |
| `validation.passing_command` | Replaced with `run.command` |

- [x] Create `tasks/custom-dev/toy_fail_pytest/task.yaml`:
  - `id`: "toy_fail_pytest"
  - `suite`: "custom-dev"
  - `repo.url`: relative path `../../../examples/toy_repo`
  - `repo.commit`: `a3219a9adc9f143c379d38d76a77cd969380f90d`
  - `environment.docker_image`: `ghcr.io/agentbench/py-runner:0.1.0`
  - `environment.workdir`: `/workspace`
  - `environment.timeout_sec`: 300
  - `setup.commands`: pip upgrade, pip install pytest, pip install -e .
  - `run.command`: `pytest -q`

### Task Runner Module
- [x] Create `agentbench/run_task.py`:
  - Function `run_task(task_yaml: Path, out_dir: Path, str_format: str) -> Path`:
    - Load task.yaml using PyYAML
    - **Added**: `validate_task_yaml()` function that validates required structure:
      - `id`, `suite` (strings)
      - `repo.url`, `repo.commit` (strings)
      - `environment.docker_image`, `environment.workdir` (strings)
      - `environment.timeout_sec` (int)
      - `setup.commands` (list)
      - `run.command` (string)
    - Generate run ID using ULID
    - Create artifact directory structure:
      - `<out_dir>/artifacts/runs/<timestamp>__<run_id>/`
      - Subdirs: `task/`, `logs/`, `workspace/`
    - Copy task.yaml into `task/` directory (freeze the spec)
    
    - **Git operations**:
      - Clone the repo URL into `workspace/repo/`
      - Checkout the pinned commit
      - Log git stdout/stderr to `logs/git_clone_*.txt` and `logs/git_checkout_*.txt`
      - Raise ValueError if clone/checkout fails
    
    - **Setup phase**:
      - Instantiate `DockerSandbox`
      - Join all setup commands with ` && `
      - Run in container with network=bridge (allow pip to download)
      - Capture to `logs/setup_stdout.txt`, `logs/setup_stderr.txt`
      - Raise ValueError if setup fails
    
    - **Run phase**:
      - Run the `run.command` in container
      - Use network=none (isolated)
      - Capture to `logs/run_stdout.txt`, `logs/run_stderr.txt`
    
    - **Metadata**:
      - Create `run.json` with:
        - run_id
        - task_id
        - repo_url, repo_commit
        - docker_image
        - network_settings (Setup: bridge, Run: none)
        - commands_executed (setup and run)
        - exit_codes (Setup and Run)
        - paths_to_logs
    
    - Return the run directory path

### Wire Up CLI
- [x] Update `agentbench/cli.py`:
  - Import `run_task` function
  - `run-task` command calls `run_task()` and prints the result path

### End of Day 4 Checkpoint
- [x] `uv run agentbench run-task --task tasks/custom-dev/toy_fail_pytest/task.yaml` executes
- [x] Artifact directory is created with expected files
- [x] `run.json` contains all metadata
- [x] `logs/run_stdout.txt` shows pytest failure output
- [x] Exit code in `run.json` is 1 (failing test)

---

## Day 5 (Friday): Doctor Script + Determinism Proof + Polish

### Doctor Script
- [x] Create `scripts/doctor.sh`:
  - Check docker is available: `docker version`
  - Check docker can run containers: `docker run --rm hello-world`
  - Check the py-runner image exists: `docker image inspect ghcr.io/agentbench/py-runner:0.1.0`
  - Check git is available: `git --version`
  - Check Python version: `python3 --version`
  - Check disk space: warn if < 10GB free
  - Print success/failure summary with colors (green/red)
  - Exit 0 if all pass, exit 1 if any fail

- [x] Make it executable: `chmod +x scripts/doctor.sh`
- [x] Test: `./scripts/doctor.sh` passes

### Determinism Proof
- [x] Run the task twice:
  - `uv run agentbench run-task --task tasks/custom-dev/toy_fail_pytest/task.yaml`
  - `uv run agentbench run-task --task tasks/custom-dev/toy_fail_pytest/task.yaml`

- [x] Verify determinism:
  - Both runs create separate artifact directories (different timestamps/ULIDs)
  - Both have the same exit code (1)
  - Both `run_stdout.txt` show the same pytest failure
  - Both `run.json` have consistent metadata (same commit, image, commands)

- [x] Document: Add to notes what varies (timestamps, run IDs) vs what's stable (exit codes, error messages)

### Capture Docker Image Digest
- [x] Enhance `run_task.py` to also capture:
  - Docker image digest: run `docker image inspect --format='{{.Id}}'` and store in `run.json`
  - This proves which exact image was used

### Polish and Documentation
- [x] Create `artifacts/.gitkeep` so the directory is tracked but empty
- [x] Update CLI help strings to be descriptive
- [x] Add docstrings to main functions
- [x] Run ruff: `uv run ruff check agentbench/`
- [x] Fix any linting issues
- [x] Run ruff format: `uv run ruff format agentbench/`

### Week 1 Commit
- [ ] Stage all changes
- [ ] Commit with message: "Week 1: docker runner + single-task execution with artifacts"
- [ ] Verify: `git log --oneline` shows the commit

### End of Day 5 / Week 1 Checkpoint
- [x] `./scripts/doctor.sh` passes all checks
- [x] `uv run agentbench run-task --task ...` works end-to-end
- [x] Two runs produce:
  - Different artifact directories
  - Same exit codes
  - Same test output
  - Captured docker image digest
- [x] All code passes ruff linting
- [ ] Week 1 commit is made

---

## Week 1 Success Criteria (Summary)

| Criterion | How to Verify | Status |
|-----------|---------------|--------|
| Docker image builds | `docker run --rm ghcr.io/agentbench/py-runner:0.1.0 python -V` | ✅ |
| CLI works | `uv run agentbench --help` shows commands | ✅ |
| Task runs | `uv run agentbench run-task --task tasks/.../task.yaml` completes | ✅ |
| Artifacts created | `ls artifacts/` shows timestamped directories | ✅ |
| Logs captured | `cat artifacts/.../logs/run_stdout.txt` shows pytest output | ✅ |
| Metadata recorded | `cat artifacts/.../run.json` shows all fields | ✅ |
| Determinism | Two runs have same exit code and similar logs | ✅ |
| Image digest captured | `run.json` includes docker image ID | ✅ |

---

## Architecture Decisions Made This Week

1. **subprocess over docker-py**: Using `subprocess` to call docker CLI directly. Simpler to debug, easier to see exactly what commands run.

2. **bash -lc for commands**: Running commands via `bash -lc` ensures login shell environment is loaded (important for pip, pyenv, etc.).

3. **ULID for run IDs**: Using ULID instead of UUID because ULIDs are sortable by time and more readable.

4. **Separate setup and run phases**: Setup runs with network=bridge (for pip), run phase uses network=none (isolated).

5. **Freeze task.yaml in artifacts**: Copy the task spec into the artifact directory so you always know exactly what config was used.

6. **stdout/stderr to files**: Capture to files rather than memory to handle large outputs and allow post-hoc inspection.

7. **exit code 124 for timeout**: Following standard convention (like GNU timeout) for timeout exit codes.

8. **CLI entry point changed**: Using `agentbench` instead of `ab` as the CLI command name.

9. **Simplified task schema**: Removed `network_policy` from task spec; network behavior is hardcoded (setup=bridge, run=none). Using single `run.command` instead of separate `failing_command`/`passing_command`.

10. **Task YAML validation**: Added inline validation function in `run_task.py` to ensure required fields are present and correctly typed.

---

## Schema Changes from Spec

### Task YAML Schema (Implemented vs Spec)

**Implemented schema** (`tasks/custom-dev/toy_fail_pytest/task.yaml`):
```yaml
id: toy_fail_pytest
suite: custom-dev

repo:
  url: ../../../examples/toy_repo
  commit: a3219a9adc9f143c379d38d76a77cd969380f90d

environment:
  docker_image: ghcr.io/agentbench/py-runner:0.1.0
  workdir: /workspace
  timeout_sec: 300

setup:
  commands:
    - pip install --upgrade pip
    - pip install pytest
    - pip install -e .

run:
  command: pytest -q
```

**Changes from spec**:
- `environment.network_policy` - **Removed** (hardcoded: setup=bridge, run=none)
- `environment.python` - **Removed**
- `environment.cpu_limit` - **Not implemented yet**
- `environment.mem_limit_mb` - **Not implemented yet**
- `environment.tool_timeout_sec` - **Not implemented yet**
- `setup.capture` - **Not implemented yet**
- `validation.failing_command` / `validation.passing_command` - **Replaced with** `run.command`
- `agent.*` - **Not implemented yet** (Week 4+)
- `artifacts.*` - **Not implemented yet**

---

## Files Created This Week

```
agentbench/
  __init__.py                    ✅
  cli.py                         ✅
  run_task.py                    ✅
  sandbox/
    __init__.py                  ✅
    docker_sandbox.py            ✅
    tests/
      sandbox_test.py            ✅ (bonus: not in original plan)
  util/
    __init__.py                  ✅
    paths.py                     ✅
  schemas/                       (empty directory)

docker/
  py-runner/
    Dockerfile                   ✅
    README.md                    ✅

examples/
  toy_repo/
    pyproject.toml               ✅
    src/toy/__init__.py          ✅
    src/toy/mathy.py             ✅
    tests/test_basic.py          ✅

tasks/
  custom-dev/
    toy_fail_pytest/
      task.yaml                  ✅

scripts/
  doctor.sh                      ✅

artifacts/
  .gitkeep                       ✅

pyproject.toml                   ✅
.python-version                  ✅
.gitignore                       ✅
.env.example                     ❌ (not needed for Week 1)
```

---

## Known Issues / TODOs

All Week 1 issues have been resolved:

1. ~~**Double artifacts path**~~: ✅ Fixed - now creates `artifacts/runs/...` directly
2. ~~**Missing .python-version**~~: ✅ Created with `3.11`
3. ~~**Missing doctor.sh**~~: ✅ Implemented with all checks
4. ~~**Missing artifacts/.gitkeep**~~: ✅ Created
5. ~~**Docker image digest**~~: ✅ Now captured in `run.json`
6. ~~**Toy repo tests**~~: ✅ Test file is correctly at `examples/toy_repo/tests/test_basic.py`

**Remaining for future weeks:**
- `.env.example` not created (not needed until Week 4+ when agent integration begins)

---

## Potential Blockers & Mitigations

| Blocker | Mitigation |
|---------|------------|
| Docker Desktop not running | Add to doctor.sh, document in README |
| Image build fails | Pin base image digest, document expected output |
| Relative path issues with repo URL | Use absolute paths or `file://` URLs |
| Git clone fails | Log full stderr, check network |
| Container runs as root | Verify Dockerfile USER directive, test with whoami |
| Timeout not working | Test explicitly with `sleep` command |

---

## Week 1 Reflection

### What Was Accomplished

Week 1 has been **successfully completed**. The core infrastructure for AgentBench is now in place:

1. **Docker-based task execution**: Tasks defined in YAML can be executed in isolated Docker containers with proper network segmentation (bridge for setup, none for run).

2. **Deterministic artifact capture**: Each run produces a timestamped directory with:
   - Complete stdout/stderr logs for all phases (git clone, checkout, setup, run)
   - Frozen copy of the task specification
   - Metadata JSON with run ID, exit codes, docker image digest, and commands executed

3. **Developer tooling**: 
   - CLI (`agentbench run-task`) provides a clean interface
   - `doctor.sh` validates the development environment
   - Ruff linting/formatting keeps code quality high

4. **Toy test case**: The intentionally-failing `toy_repo` with broken `add()` function provides a reproducible test case that verifies the system correctly captures test failures.

### Key Design Decisions That Worked Well

- **subprocess over docker-py**: Direct CLI calls are transparent and debuggable
- **ULID for run IDs**: Sortable, readable, and unique
- **Separate setup/run phases**: Clean separation of network-required (pip install) vs isolated (test execution) operations
- **Freezing task.yaml**: Artifact directories are self-documenting

### What Could Be Improved

- The `run_task.py` module is doing a lot (validation, git ops, docker orchestration, metadata). Future weeks might benefit from splitting this into smaller, focused modules.
- Error messages could be more actionable (e.g., when git clone fails, suggest checking network or repo URL).

### Ready for Week 2

The foundation is solid. Week 2 can build on this to add:
- Multiple task execution
- Result comparison tooling
- More sophisticated validation

