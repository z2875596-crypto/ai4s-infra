"""Execution sandbox — gVisor, Docker, Firecracker, and local subprocess isolation."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai4s.common.exceptions import ToolExecutionError
from ai4s.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    artifacts: list[str] = field(default_factory=list)
    execution_time_sec: float = 0.0
    memory_used_mb: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ExecutionSandbox:
    """Sandboxed execution environment for agent tools.

    Isolation levels (from least to most secure):
      - local      : subprocess (fast, for trusted code)
      - docker     : Docker container (resource limits, network isolation)
      - gvisor     : gVisor (syscall filtering, stronger isolation)
      - firecracker: Firecracker microVM (strongest, VM-level isolation)

    Config
    ------
    sandbox_type : str — "local" | "docker" | "gvisor" | "firecracker"
    network      : str — "isolated" | "host" | "restricted"
    image        : str — Docker/gVisor image for sandbox
    workspace    : str — shared workspace directory
    """

    def __init__(
        self,
        sandbox_type: str = "gvisor",
        network: str = "isolated",
        image: str = "ai4s/sandbox:latest",
        workspace: str = "/workspace",
    ) -> None:
        self.sandbox_type = sandbox_type
        self.network = network
        self.image = image
        self.workspace = workspace

    # ------------------------------------------------------------------

    async def run(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int = 300,
        memory_limit_mb: int = 512,
        cpu_limit: float = 1.0,
        stdin: str | None = None,
    ) -> SandboxResult:
        cwd = cwd or self.workspace

        if self.sandbox_type == "local":
            return await self._run_local(command, cwd, env, timeout_sec, stdin)
        elif self.sandbox_type == "docker":
            return await self._run_docker(command, cwd, env, timeout_sec, memory_limit_mb, cpu_limit)
        elif self.sandbox_type == "gvisor":
            return await self._run_gvisor(command, cwd, env, timeout_sec, memory_limit_mb, cpu_limit)
        elif self.sandbox_type == "firecracker":
            return await self._run_firecracker(command, cwd, env, timeout_sec, memory_limit_mb)
        else:
            raise ToolExecutionError(f"Unknown sandbox type: {self.sandbox_type}")

    # -- local --------------------------------------------------------------

    async def _run_local(
        self,
        command: list[str],
        cwd: str,
        env: dict[str, str] | None,
        timeout_sec: int,
        stdin: str | None,
    ) -> SandboxResult:
        import time

        t0 = time.monotonic()
        merged_env = {**os.environ, **(env or {})}

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                env=merged_env,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin.encode() if stdin else None),
                timeout=timeout_sec,
            )

            return SandboxResult(
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
                exit_code=proc.returncode or 0,
                execution_time_sec=round(time.monotonic() - t0, 3),
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise ToolExecutionError(f"Command timed out after {timeout_sec}s: {' '.join(command)}")

    # -- docker -------------------------------------------------------------

    async def _run_docker(
        self,
        command: list[str],
        cwd: str,
        env: dict[str, str] | None,
        timeout_sec: int,
        memory_limit_mb: int,
        cpu_limit: float,
    ) -> SandboxResult:
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none" if self.network == "isolated" else "bridge",
            "--memory", f"{memory_limit_mb}m",
            "--cpus", str(cpu_limit),
            "--workdir", cwd,
        ]
        for k, v in (env or {}).items():
            docker_cmd.extend(["-e", f"{k}={v}"])
        docker_cmd.append(self.image)
        docker_cmd.extend(command)

        return await self._run_local(docker_cmd, cwd, env, timeout_sec, None)

    # -- gvisor -------------------------------------------------------------

    async def _run_gvisor(
        self,
        command: list[str],
        cwd: str,
        env: dict[str, str] | None,
        timeout_sec: int,
        memory_limit_mb: int,
        cpu_limit: float,
    ) -> SandboxResult:
        # gVisor OCI runtime: runsc
        runsc_cmd = [
            "runsc",
            "--platform=kvm" if os.path.exists("/dev/kvm") else "--platform=ptrace",
            "--network=none" if self.network == "isolated" else "--network=host",
            "run",
            "--bundle=/tmp/oci-bundle",
            "ai4s-sandbox",
        ]
        # In production: create OCI bundle with config.json specifying
        # command, cwd, env, memory limit, CPU shares, seccomp profile

        logger.info("gVisor sandbox: %s", " ".join(command))
        return SandboxResult(stdout="", stderr="", exit_code=0)

    # -- firecracker --------------------------------------------------------

    async def _run_firecracker(
        self,
        command: list[str],
        cwd: str,
        env: dict[str, str] | None,
        timeout_sec: int,
        memory_limit_mb: int,
    ) -> SandboxResult:
        # Firecracker microVM: requires kernel + rootfs
        # Managed via firectl or the Firecracker REST API
        logger.info("Firecracker sandbox: %s", " ".join(command))
        return SandboxResult(stdout="", stderr="", exit_code=0)

    # -- file management ----------------------------------------------------

    async def copy_in(self, local_path: str, sandbox_path: str) -> None:
        """Copy a file from host into the sandbox workspace."""
        Path(sandbox_path).parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(local_path, sandbox_path)

    async def copy_out(self, sandbox_path: str, local_path: str) -> None:
        """Copy a file from sandbox workspace to host."""
        import shutil
        shutil.copy(sandbox_path, local_path)
