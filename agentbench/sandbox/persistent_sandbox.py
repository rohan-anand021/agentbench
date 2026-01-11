import logging
import subprocess
from pathlib import Path

from agentbench.sandbox.models import DockerRunResult
from agentbench.util.paths import ensure_dir

logger = logging.getLogger(__name__)


class PersistentDockerSandbox:
    """
    Maintain a long-lived container with a tmpfs-backed workspace.
    Commands are executed via `docker exec`, and stdout/stderr are streamed
    to host paths for logging.
    """

    def __init__(
        self,
        image: str,
        workdir: str = "/workspace",
        use_tmpfs: bool = True,
    ):
        self.image = image
        self.workdir = workdir
        self.use_tmpfs = use_tmpfs
        self.container_id: str | None = None
        self._network_state = "bridge"

    def start(self) -> None:
        if self.container_id:
            return

        cmd = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--workdir",
            self.workdir,
            "--network",
            "bridge",
        ]
        if self.use_tmpfs:
            # Ensure the tmpfs workspace is writable by any user (avoids permission issues with non-root images).
            cmd.extend(["--tmpfs", f"{self.workdir}:mode=1777"])
        cmd.extend([self.image, "sleep", "infinity"])

        logger.debug("Starting persistent sandbox: %s", " ".join(cmd))
        run_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if run_result.returncode != 0:
            raise RuntimeError(
                f"Failed to start sandbox: {run_result.stderr.strip()}"
            )

        self.container_id = run_result.stdout.strip()
        self._network_state = "bridge"
        logger.debug("Sandbox started with container_id=%s", self.container_id)

    def _ensure_started(self) -> None:
        if not self.container_id:
            self.start()

    def _set_network(self, network: str | None) -> None:
        if not network or network == self._network_state:
            return
        if not self.container_id:
            return

        if network == "none":
            subprocess.run(
                ["docker", "network", "disconnect", "bridge", self.container_id],
                check=False,
                capture_output=True,
            )
            self._network_state = "none"
        elif network == "bridge":
            subprocess.run(
                ["docker", "network", "connect", "bridge", self.container_id],
                check=False,
                capture_output=True,
            )
            self._network_state = "bridge"
        else:
            raise ValueError("Network must be 'none' or 'bridge'")

    def exec(
        self,
        command: str,
        stdout_path: Path,
        stderr_path: Path,
        timeout_sec: int,
        network: str | None = None,
        env: dict[str, str] | None = None,
    ) -> DockerRunResult:
        self._ensure_started()
        self._set_network(network)

        ensure_dir(stdout_path.parent)
        ensure_dir(stderr_path.parent)

        env_args: list[str] = []
        if env:
            for key, value in env.items():
                if value is None:
                    continue
                env_args.extend(["-e", f"{key}={value}"])

        cmd = [
            "docker",
            "exec",
            *env_args,
            self.container_id,
            "sh",
            "-c",
            command,
        ]

        logger.debug(
            "Exec in container %s with network=%s: %s",
            self.container_id,
            network or self._network_state,
            command,
        )

        try:
            stdout = stdout_path.open("w", encoding="utf-8", newline="\n")
            stderr = stderr_path.open("w", encoding="utf-8", newline="\n")
        except PermissionError:
            raise
        else:
            try:
                with stdout, stderr:
                    run_result = subprocess.run(
                        args=cmd,
                        stdout=stdout,
                        stderr=stderr,
                        timeout=timeout_sec,
                    )
                exit_code = run_result.returncode
            except OSError as e:
                logger.error("I/O error during docker exec: %s", e)
                raise
            except subprocess.TimeoutExpired:
                logger.warning(
                    "docker exec timed out after %d seconds", timeout_sec
                )
                with stderr_path.open("a") as err_f:
                    err_f.write(
                        f"Execution timed out after {timeout_sec} seconds"
                    )
                exit_code = 124

        return DockerRunResult(exit_code, stdout_path, stderr_path, cmd)

    def copy_from(self, src: str, dest: Path) -> None:
        self._ensure_started()
        ensure_dir(dest.parent)
        cmd = ["docker", "cp", f"{self.container_id}:{src}", str(dest)]
        logger.debug("Copying from container: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)

    def copy_to(self, src: Path, dest: str) -> None:
        self._ensure_started()
        cmd = ["docker", "cp", str(src), f"{self.container_id}:{dest}"]
        logger.debug("Copying to container: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)

    def cleanup(self) -> None:
        if not self.container_id:
            return
        logger.debug("Cleaning up sandbox container %s", self.container_id)
        subprocess.run(
            ["docker", "rm", "-f", self.container_id],
            check=False,
            capture_output=True,
        )
        self.container_id = None
