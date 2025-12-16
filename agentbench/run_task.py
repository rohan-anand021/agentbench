import yaml
import ulid
from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import json

from agentbench.util.paths import ensure_dir
from agentbench.sandbox.docker_sandbox import DockerSandbox

def run_task(task_yaml: Path, out_dir: Path, str_format: str = "%Y-%m-%d_%H-%M-%S") -> Path:

    with open(task_yaml) as f:
        task = yaml.safe_load(f)

    def validate_task_yaml(task: dict, task_yaml: Path) -> None:
        required_structure = {
            "id": str,
            "suite": str,
            "repo": {
                "url": str,
                "commit": str,
            },
            "environment": {
                "docker_image": str,
                "workdir": str,
                "timeout_sec": int,
            },
            "setup": {
                "commands": list,
            },
            "run": {
                "command": str,
            },
        }

        def validate(node, schema, path=""):
            if not isinstance(node, dict):
                raise TypeError(f"{path or 'root'} must be a mapping")

            for key, expected in schema.items():
                if key not in node:
                    raise KeyError(f"Missing key: {path + key}")

                value = node[key]

                if isinstance(expected, dict):
                    validate(value, expected, path + key + ".")
                else:
                    if not isinstance(value, expected):
                        raise TypeError(
                            f"Key '{path + key}' must be of type "
                            f"{expected.__name__}, got {type(value).__name__}"
                        )

        try:
            validate(task, required_structure)
        except Exception as e:
            raise ValueError(f"Invalid task YAML ({task_yaml}): {e}")

    #validate keys
    validate_task_yaml(task, task_yaml)

    out_dir = ensure_dir(out_dir)
    artifacts_dir = ensure_dir(Path(out_dir / 'artifacts'))
    runs_dir = ensure_dir(Path(artifacts_dir / 'runs'))

    timestamp = datetime.now().strftime(str_format)
    run_id = str(ulid.new())

    curr_run_dir = ensure_dir(Path(runs_dir, f'{timestamp}__{run_id}'))

    task_dir = ensure_dir(Path(curr_run_dir, 'task'))
    logs_dir = ensure_dir(Path(curr_run_dir, 'logs'))
    workspace_dir = ensure_dir(Path(curr_run_dir, 'workspace'))

    #copying task_yaml into task
    shutil.copy(task_yaml, task_dir)

    #create workspace/repo
    repo_dir = ensure_dir(Path(workspace_dir, 'repo'))

    def run_command(cmd_name: str, cmd: list, timeout: int, cwd: Path | None = None):
        stdout_path = Path(logs_dir, f'{cmd_name}_stdout.txt')
        stderr_path = Path(logs_dir, f'{cmd_name}_stderr.txt')
        exit_code = None

        try:
            stdout = stdout_path.open('w', encoding ="utf-8", newline = "\n")
            stderr = stderr_path.open('w', encoding = "utf-8", newline = "\n")
        
        except PermissionError as e:
            raise
            
        else:
            try:
                with stdout, stderr:
                    run_result = subprocess.run(
                        args = cmd,
                        cwd = cwd,
                        stdout = stdout,
                        stderr = stderr,
                        timeout = timeout
                    )

                    exit_code = run_result.returncode

            except OSError as e:
                    print(f'I/O error: {e}')
                    raise

            except subprocess.TimeoutExpired:

                with stderr_path.open('a') as stderr:
                    stderr.write(f'Execution timed out after {timeout} seconds')
                
                exit_code = 124
        
        return stdout_path, stderr_path, exit_code

    #clone the repo
    cmd = ['git', 'clone', task["repo"]["url"], str(repo_dir)]
    timeout = 120
    stdout_path, stderr_path, exit_code = run_command('git_clone', cmd, timeout)

    if exit_code != 0:
        raise ValueError('git clone operation failed')

    #checkout the commit
    cmd = ['git', 'checkout', task["repo"]["commit"]]
    timeout = 120
    cwd = repo_dir
    stdout_path, stderr_path, exit_code = run_command('git_checkout', cmd, timeout, cwd = repo_dir)

    if exit_code != 0:
        raise ValueError('git checkout operation failed')

    sandbox = DockerSandbox(
        image = task['environment']['docker_image'],
        workdir = task['environment']['workdir']
    )

    setup_commands = " && ".join(task['setup']['commands'])

    setup_run_result = sandbox.run(workspace_host_path=workspace_dir,
                             command = setup_commands,
                             network = 'bridge',
                             timeout_sec = task['environment']['timeout_sec'],
                             stdout_path = Path(logs_dir, 'setup_stdout.txt'),
                             stderr_path = Path(logs_dir, 'setup_stderr.txt'))

    if setup_run_result.exit_code != 0:
        raise ValueError("Setup run failed, please try again")

    run_run_result = sandbox.run(workspace_host_path=workspace_dir,
                             command = task['run']['command'],
                             network = 'none',
                             timeout_sec = task['environment']['timeout_sec'],
                             stdout_path = Path(logs_dir, 'run_stdout.txt'),
                             stderr_path = Path(logs_dir, 'run_stderr.txt'))

    run_data = {
        "run_id": run_id,
        "task_id": task['id'],
        "repo_url": task['repo']['url'],
        "repo_commit": task['repo']['commit'],
        "docker_image": task['environment']['docker_image'],
        "network_settings": {"Setup": "bridge", "Run": "none"},
        "commands_executed": {"setup": task["setup"]["commands"], "run": task["run"]["command"],},
        "exit_codes": {"Setup exit code": str(setup_run_result.exit_code), "Run exit code": str(run_run_result.exit_code)},
        "paths_to_logs": str(logs_dir)
    }

    runs_path = Path(curr_run_dir, 'run.json')
    with runs_path.open('w', encoding='utf-8') as runs:
        json.dump(run_data, runs, indent = 2)

    return curr_run_dir


