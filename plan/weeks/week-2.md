# Week 2: Loader + Suite + Baseline Validation

## Goal
By end of week: Load and enumerate all tasks in a suite, run baseline validation on each task (verify tests fail as expected), and produce a structured JSONL log of all attempts. Refuse tasks where baseline unexpectedly passes.

---

## Progress Summary

| Day | Focus | Status |
|-----|-------|--------|
| Day 1 | Task Loader Module | ✅ COMPLETE |
| Day 2 | Baseline Validator | ⏳ Not started |
| Day 3 | JSONL Attempt Records | ⏳ Not started |
| Day 4 | Suite Runner + CLI | ⏳ Not started |
| Day 5 | Polish + Additional Tasks | ⏳ Not started |

### Notes
- **Day 1**: Created `models.py` (for TaskSpec and nested models) and `validation.py` (extracted from run_task.py) in addition to the planned files.
- Minor linting issues remain (import ordering, line lengths) - can be auto-fixed with `ruff check --fix`

---

## Prerequisites (from Week 1)

Before starting Week 2, ensure:
- [x] `DockerSandbox` class works and can execute commands in containers
- [x] `run_task()` can execute a single task end-to-end
- [x] Artifact directory structure is established (`artifacts/runs/<timestamp>__<run_id>/`)
- [x] CLI `run-task` command works
- [x] `doctor.sh` passes all checks

---

## Day 1 (Monday): Task Loader Module

### Design Decision: Task Discovery
Tasks are organized in suites. Each suite is a directory under `tasks/`, and each task is a subdirectory containing a `task.yaml` file:

```
tasks/
  custom-dev/           # suite name
    toy_fail_pytest/    # task directory
      task.yaml         # task specification
    another_task/
      task.yaml
  custom-heldout/       # another suite
    task_101/
      task.yaml
```

### Create Task Loader
- [x] Create `agentbench/tasks/__init__.py` (empty, makes it a package)
- [x] Create `agentbench/tasks/loader.py`:
  - Define `TaskSpec` dataclass or Pydantic model with fields:
    - `id: str`
    - `suite: str`
    - `repo: RepoSpec` (nested: `url`, `commit`)
    - `environment: EnvironmentSpec` (nested: `docker_image`, `workdir`, `timeout_sec`)
    - `setup: SetupSpec` (nested: `commands: list[str]`)
    - `run: RunSpec` (nested: `command: str`)
    - `source_path: Path` (path to the task.yaml file)
  
  - Function `load_task(task_yaml: Path) -> TaskSpec`:
    - Read and parse YAML file
    - Validate against schema (reuse validation logic from `run_task.py`)
    - Return `TaskSpec` object
    - Raise `InvalidTaskError` if validation fails
  
  - Function `discover_tasks(suite_dir: Path) -> list[Path]`:
    - Use `pathlib.Path.glob("*/task.yaml")` to find all task.yaml files
    - Return sorted list of paths (deterministic ordering)
  
  - Function `load_suite(tasks_root: Path, suite_name: str) -> list[TaskSpec]`:
    - Construct suite path: `tasks_root / suite_name`
    - Call `discover_tasks()` to find all task.yaml files
    - Call `load_task()` for each, collecting results
    - Log warning for any tasks that fail to load (don't crash entire suite)
    - Return list of successfully loaded `TaskSpec` objects

### Create Custom Exceptions
- [x] Create `agentbench/tasks/exceptions.py`:
  - `class InvalidTaskError(Exception)`: raised when task.yaml is malformed
  - `class TaskNotFoundError(Exception)`: raised when task directory doesn't exist
  - `class SuiteNotFoundError(Exception)`: raised when suite directory doesn't exist

### Unit Tests for Loader
- [x] Create `agentbench/tasks/tests/__init__.py`
- [x] Create `agentbench/tasks/tests/test_loader.py`:
  - Test `load_task()` with valid task.yaml
  - Test `load_task()` raises `InvalidTaskError` for malformed YAML
  - Test `discover_tasks()` finds all tasks in a directory
  - Test `load_suite()` returns all valid tasks
  - Use pytest fixtures to create temporary task directories

### End of Day 1 Checkpoint
- [x] `load_task()` correctly parses `tasks/custom-dev/toy_fail_pytest/task.yaml`
- [x] `load_suite()` returns a list containing the toy task
- [x] Invalid YAML raises appropriate exception
- [x] Unit tests pass (10 tests passing)

---

## Day 2 (Tuesday): Baseline Validator

### Design Decision: What is Baseline Validation?
Baseline validation ensures that a task's tests **fail** before any agent intervention. This is critical because:
1. If tests already pass, the task is invalid (nothing to fix)
2. It proves the test suite actually catches the bug
3. It establishes the "before" state for comparison

### Create Validator Module
- [ ] Create `agentbench/tasks/validator.py`:
  - Define `ValidationResult` dataclass:
    - `task_id: str`
    - `valid: bool` (True if baseline fails as expected)
    - `exit_code: int`
    - `stdout_path: Path`
    - `stderr_path: Path`
    - `error_reason: str | None` (e.g., "baseline_passed", "setup_failed", "timeout")
    - `duration_sec: float`
  
  - Function `validate_baseline(task: TaskSpec, workspace_dir: Path, logs_dir: Path) -> ValidationResult`:
    - Create workspace directory structure
    - Clone repo to `workspace/repo/`
    - Checkout pinned commit
    - Run setup commands with `network=bridge`
    - Run the `run.command` (which should fail) with `network=none`
    - If exit_code == 0: task is INVALID (baseline passed unexpectedly)
    - If exit_code != 0: task is VALID (baseline fails as expected)
    - If setup fails: task is INVALID (setup_failed)
    - If timeout: task is INVALID (timeout)
    - Return `ValidationResult`

### Integrate with Existing Code
- [ ] Refactor `run_task.py` to use `TaskSpec` from loader:
  - Change `run_task(task_yaml: Path, ...)` to internally use `load_task()`
  - Keep the function signature the same for CLI compatibility
  - Extract common logic (git clone, checkout) into helper functions in `agentbench/util/git.py`

### Create Git Utilities
- [ ] Create `agentbench/util/git.py`:
  - Function `clone_repo(url: str, dest: Path, logs_dir: Path) -> tuple[int, Path, Path]`:
    - Run `git clone <url> <dest>`
    - Capture stdout/stderr to log files
    - Return (exit_code, stdout_path, stderr_path)
  
  - Function `checkout_commit(repo_dir: Path, commit: str, logs_dir: Path) -> tuple[int, Path, Path]`:
    - Run `git checkout <commit>` in repo_dir
    - Capture stdout/stderr to log files
    - Return (exit_code, stdout_path, stderr_path)

### End of Day 2 Checkpoint
- [ ] `validate_baseline()` correctly identifies toy_fail_pytest as valid (tests fail)
- [ ] If you temporarily fix the bug in toy_repo, validator should mark it invalid
- [ ] Setup failures are caught and reported
- [ ] Git utilities work and log properly

---

## Day 3 (Wednesday): JSONL Attempt Records

### Design Decision: Event-Sourced Logging
Every task attempt should produce a structured record. This enables:
- Aggregating results across many tasks
- Debugging failures
- Generating reports
- Comparing runs

### JSONL Utilities
- [ ] Create `agentbench/util/jsonl.py`:
  - Function `append_jsonl(path: Path, record: dict) -> None`:
    - Open file in append mode
    - Write JSON + newline
    - Use atomic write pattern (write to temp, rename)
    - Handle file locking for concurrent writes (optional, can use `filelock` library)
  
  - Function `read_jsonl(path: Path) -> Iterator[dict]`:
    - Open file, yield one parsed dict per line
    - Skip empty lines
    - Log warning (don't crash) for malformed lines

### Attempt Record Schema
- [ ] Create `agentbench/schemas/attempt_record.py`:
  - Define `AttemptRecord` Pydantic model matching spec:
    ```python
    class AttemptRecord(BaseModel):
        run_id: str
        task_id: str
        suite: str
        timestamps: TimestampInfo  # started_at, ended_at
        duration_sec: float
        baseline_validation: BaselineValidationResult
        result: TaskResult  # passed, exit_code, failure_reason
        artifact_paths: dict[str, str]
    ```
  - Nested models:
    - `TimestampInfo`: `started_at: datetime`, `ended_at: datetime`
    - `BaselineValidationResult`: `attempted: bool`, `failed_as_expected: bool`, `exit_code: int`
    - `TaskResult`: `passed: bool`, `exit_code: int`, `failure_reason: str | None`

### Integrate Attempt Recording
- [ ] Update `validate_baseline()` to record attempts:
  - Generate ULID for each validation run
  - Record start/end timestamps
  - Write `AttemptRecord` to `attempts.jsonl` in the run directory

### End of Day 3 Checkpoint
- [ ] `append_jsonl()` correctly writes records
- [ ] `read_jsonl()` correctly reads them back
- [ ] Running validation produces `attempts.jsonl` with structured records
- [ ] Schema validates correctly with Pydantic

---

## Day 4 (Thursday): Suite Runner + CLI

### Suite Runner
- [ ] Create `agentbench/suite_runner.py`:
  - Function `run_suite(suite_name: str, tasks_root: Path, out_dir: Path) -> Path`:
    - Load all tasks in suite using `load_suite()`
    - Create run directory: `<out_dir>/runs/<timestamp>__<suite>__baseline/`
    - Create `run.json` metadata file with:
      - `run_id: str` (ULID)
      - `suite: str`
      - `started_at: datetime`
      - `task_count: int`
      - `harness_version: str` (git SHA or "dev")
    - For each task:
      - Create task subdirectory
      - Run `validate_baseline()`
      - Append result to `attempts.jsonl`
      - Print progress to console (e.g., "Task 1/5: toy_fail_pytest... VALID")
    - Update `run.json` with:
      - `ended_at: datetime`
      - `valid_count: int`
      - `invalid_count: int`
    - Return run directory path

### CLI Commands
- [ ] Update `agentbench/cli.py`:
  - Add `validate-suite` command:
    ```
    @app.command('validate-suite')
    def validate_suite_cmd(
        suite: str = typer.Argument(..., help="Suite name (e.g., custom-dev)"),
        tasks_root: Path = typer.Option(
            Path('tasks'), 
            '--tasks', '-t',
            help="Root directory containing task suites"
        ),
        out: Path = typer.Option(
            Path('artifacts'),
            '--out', '-o', 
            help="Output directory for artifacts"
        ),
    ):
        """
        Validate all tasks in a suite.
        
        Runs baseline validation on each task to ensure tests fail as expected.
        Tasks where tests pass are marked as invalid.
        """
    ```
  
  - Add `list-tasks` command (useful for debugging):
    ```
    @app.command('list-tasks')
    def list_tasks_cmd(
        suite: str = typer.Argument(..., help="Suite name"),
        tasks_root: Path = typer.Option(Path('tasks'), '--tasks', '-t'),
    ):
        """List all tasks in a suite."""
    ```

### Progress Reporting
- [ ] Use `rich` library for better console output:
  - Progress bar for suite validation
  - Color-coded status (green for valid, red for invalid)
  - Summary table at the end

### End of Day 4 Checkpoint
- [ ] `uv run agentbench list-tasks custom-dev` shows toy_fail_pytest
- [ ] `uv run agentbench validate-suite custom-dev` runs validation
- [ ] Progress is displayed during execution
- [ ] `attempts.jsonl` is created with all results
- [ ] `run.json` contains suite metadata

---

## Day 5 (Friday): Polish + Additional Tasks + Documentation

### Add More Test Tasks
To properly test suite functionality, create 2-3 more toy tasks:

- [ ] Create `tasks/custom-dev/toy_pass_pytest/task.yaml`:
  - A task where tests already pass (should be marked INVALID)
  - Use same toy_repo but with a "fixed" commit
  - This tests the "baseline passed unexpectedly" detection

- [ ] Create `tasks/custom-dev/toy_timeout/task.yaml`:
  - A task with a very short timeout (e.g., 5 seconds)
  - Run command: `sleep 60 && pytest -q`
  - This tests timeout handling

- [ ] Create `tasks/custom-dev/toy_setup_fail/task.yaml`:
  - A task with broken setup (e.g., `pip install nonexistent-package-xyz`)
  - This tests setup failure handling

### Error Handling & Edge Cases
- [ ] Handle empty suite (no tasks found): print warning, exit gracefully
- [ ] Handle missing suite directory: raise `SuiteNotFoundError`
- [ ] Handle partial failures: continue with other tasks, summarize failures at end
- [ ] Ensure Ctrl+C (SIGINT) during suite run:
  - Writes partial `attempts.jsonl` (don't lose progress)
  - Updates `run.json` with `interrupted: true`

### Summary Report (Preview of Week 7)
- [ ] Add simple summary output at end of `validate-suite`:
  ```
  ════════════════════════════════════════
  Suite Validation Complete: custom-dev
  ════════════════════════════════════════
  Total tasks:    4
  Valid:          2 (50%)
  Invalid:        2 (50%)
    - baseline_passed: 1
    - setup_failed: 1
  
  Run artifacts: artifacts/runs/2025-12-16_...
  ```

### Linting & Formatting
- [ ] Run `uv run ruff check agentbench/`
- [ ] Fix any linting issues
- [ ] Run `uv run ruff format agentbench/`

### Documentation
- [ ] Add docstrings to all new modules and functions
- [ ] Update `agentbench/cli.py` help strings

### Week 2 Commit
- [ ] Stage all changes
- [ ] Commit with message: "Week 2: task loader + suite runner + baseline validation"

### End of Day 5 / Week 2 Checkpoint
- [ ] Suite with 4 tasks can be validated
- [ ] Invalid tasks (baseline passes, setup fails, timeout) are detected
- [ ] `attempts.jsonl` contains structured records for all attempts
- [ ] `run.json` contains suite-level metadata
- [ ] Progress reporting works
- [ ] All code passes ruff linting

---

## Week 2 Success Criteria (Summary)

| Criterion | How to Verify | Status |
|-----------|---------------|--------|
| Task loader works | `load_suite()` returns list of TaskSpec | |
| Suite discovery | `list-tasks custom-dev` shows all tasks | |
| Baseline validation | `validate-suite` correctly identifies valid/invalid | |
| Invalid detection | Task with passing tests marked invalid | |
| Setup failure detection | Task with broken setup marked invalid | |
| Timeout detection | Task exceeding timeout marked invalid | |
| JSONL logging | `attempts.jsonl` contains all records | |
| Suite metadata | `run.json` contains run info | |
| Progress reporting | Console shows progress during run | |
| Graceful errors | Missing suite raises clear error | |

---

## Architecture Decisions for Week 2

1. **Pydantic for schemas**: Use Pydantic models for `TaskSpec` and `AttemptRecord`. Provides validation, serialization, and documentation.

2. **Separate loader from validator**: Keep `loader.py` (parsing) separate from `validator.py` (execution). Single responsibility.

3. **JSONL for attempt logs**: One line per attempt. Append-only, survives crashes, easy to aggregate.

4. **Suite-level run directory**: Each suite run gets its own directory with `run.json` metadata and `attempts.jsonl` log.

5. **Reuse DockerSandbox**: The validator uses the same `DockerSandbox` class from Week 1. No new Docker code needed.

6. **Extract git utilities**: Common git operations (clone, checkout) moved to `util/git.py` for reuse.

7. **Graceful degradation**: If one task fails to load/validate, continue with others. Don't fail the entire suite.

---

## New Files This Week

```
agentbench/
  tasks/
    __init__.py              DONE (Day 1)
    loader.py                DONE (Day 1)
    models.py                DONE (Day 1) - TaskSpec and nested models
    validation.py            DONE (Day 1) - validate_task_yaml() extracted from run_task.py
    validator.py             TODO (Day 2)
    exceptions.py            DONE (Day 1)
    tests/
      __init__.py            DONE (Day 1)
      test_loader.py         DONE (Day 1) - 10 tests passing
  
  schemas/
    __init__.py              TODO (if not exists)
    attempt_record.py        TODO (Day 3)
  
  util/
    git.py                   TODO (Day 2)
    jsonl.py                 TODO (Day 3)
  
  suite_runner.py            TODO (Day 4)
  cli.py                     TODO (Day 4) - add validate-suite, list-tasks commands

tasks/
  custom-dev/
    toy_pass_pytest/
      task.yaml              TODO (Day 5)
    toy_timeout/
      task.yaml              TODO (Day 5)
    toy_setup_fail/
      task.yaml              TODO (Day 5)
```

---

## Dependencies

No new dependencies required. All functionality uses:
- `pydantic` (already installed) - for schemas
- `pyyaml` (already installed) - for YAML parsing
- `rich` (already installed) - for progress/formatting
- `typer` (already installed) - for CLI
- `ulid` (already installed) - for run IDs

---

## Potential Blockers & Mitigations

| Blocker | Mitigation |
|---------|------------|
| Suite directory structure unclear | Document expected layout, validate early |
| JSONL file corruption on crash | Use atomic writes (write to temp, rename) |
| Pydantic version incompatibility | Pin pydantic>=2.0 in pyproject.toml |
| Git clone failures during validation | Reuse git utilities from Week 1, log stderr |
| Task discovery too slow | Use pathlib.glob, cache results |
| Concurrent write conflicts | Use filelock library if parallelism added later |

---

## Future Considerations (Not This Week)

- **Parallel validation**: Run multiple tasks concurrently with `--workers N` flag (Week 8+)
- **Caching**: Cache git clones to avoid re-cloning same repos (Week 8+)
- **Flakiness detection**: Run baseline twice to detect flaky tests (Week 8)
- **Task filtering**: `--filter` flag to run specific tasks by pattern

---

## Testing Strategy

### Manual Testing
1. Run `uv run agentbench list-tasks custom-dev` - should list all tasks
2. Run `uv run agentbench validate-suite custom-dev` - should validate all
3. Check `artifacts/runs/<run>/attempts.jsonl` - should have records
4. Check `artifacts/runs/<run>/run.json` - should have metadata

### Automated Testing
- Unit tests for `loader.py` with mock task directories
- Unit tests for `validator.py` with mock DockerSandbox
- Integration test: validate the toy_fail_pytest task

### Edge Case Testing
- Empty suite directory
- Malformed task.yaml
- Missing required fields
- Suite directory doesn't exist
- Task with very long name (path length limits)

