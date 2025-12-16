from dataclasses import dataclass
from pathlib import Path
import subprocess
from agentbench.util.paths import ensure_dir

@dataclass
class DockerRunResult:
    exit_code: int
    stdout_path: Path
    stderr_path: Path

class DockerSandbox:
    def __init__(self,
                image: str,
                workdir: str = '/workspace'):
        self.image = image
        self.workdir = workdir
    
    def run(self,
            workspace_host_path, 
            command,
            network,
            timeout_sec,
            stdout_path,
            stderr_path):

        #bash -lc - command
        #network - --network <network>

        if network not in ["none", "bridge"]:
            raise ValueError("Network must be 'none' or 'bridge'")

        ensure_dir(stdout_path.parent)
        ensure_dir(stderr_path.parent)

        if not workspace_host_path.is_dir():
            raise ValueError('Workspace host path directory does not exist')
        
        cmd = [
            #fixed docker boilerplate
            "docker",
            "run",
            "--rm",

            #runtime configuration
            "--network",
            f"{network}",
            "-v",
            f"{workspace_host_path}:{self.workdir}",
            "-w",
            f"{self.workdir}",
            
            #image selection
            self.image,

            #command inside container
            "bash",
            "-lc",
            command
        ]

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
                        stdout = stdout,
                        stderr = stderr,
                        timeout = timeout_sec
                    )

                exit_code = run_result.returncode

            except OSError as e:
                print(f'I/O error: {e}')
                raise

            except subprocess.TimeoutExpired:

                with stderr_path.open('a') as stderr:
                    stderr.write(f'Execution timed out after {timeout_sec} seconds')
                
                exit_code = 124

        return DockerRunResult(exit_code, stdout_path, stderr_path)




