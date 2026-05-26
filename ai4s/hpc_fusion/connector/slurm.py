"""Slurm connector — full integration with Slurm workload manager via REST API and CLI.

Supports:
  - Slurm REST API (slurmrestd) for job submission, query, cancel
  - CLI fallback (sbatch, squeue, scancel, sinfo) for environments without REST
  - Job array support
  - Accounting data via sacct
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from ai4s.common.exceptions import ConnectorError
from ai4s.common.logging import get_logger
from ai4s.hpc_fusion.connector.base import HPCConnector, HPCJob, JobState, NodeInfo

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# state mapping
# ---------------------------------------------------------------------------

_SLURM_STATE_MAP: dict[str, JobState] = {
    "PENDING": JobState.PENDING,
    "RUNNING": JobState.RUNNING,
    "COMPLETED": JobState.COMPLETED,
    "COMPLETING": JobState.RUNNING,
    "FAILED": JobState.FAILED,
    "CANCELLED": JobState.CANCELLED,
    "SUSPENDED": JobState.SUSPENDED,
    "TIMEOUT": JobState.FAILED,
    "NODE_FAIL": JobState.FAILED,
    "PREEMPTED": JobState.FAILED,
    "BOOT_FAIL": JobState.FAILED,
}


class SlurmConnector(HPCConnector):
    """Connector for Slurm workload manager.

    Config:
      rest_api_url  : str  — slurmrestd base URL (optional, enables REST mode)
      cluster       : str  — cluster name
      default_partition : str
      default_account   : str
      auth_token    : str  — JWT for REST API

    When rest_api_url is not provided, falls back to CLI (sbatch/squeue/scancel).
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._rest_url = config.get("rest_api_url", "").rstrip("/")
        self._cluster = config.get("cluster", "")
        self._default_partition = config.get("default_partition", "")
        self._default_account = config.get("default_account", "")
        self._auth_token = config.get("auth_token", "")
        self._http: httpx.AsyncClient | None = None

    # -- connect / disconnect -----------------------------------------------

    async def connect(self) -> None:
        if self._rest_url:
            headers = {"Content-Type": "application/json"}
            if self._auth_token:
                headers["X-SLURM-USER-TOKEN"] = self._auth_token
            self._http = httpx.AsyncClient(
                base_url=self._rest_url,
                headers=headers,
                timeout=60.0,
            )
            # Verify connectivity
            resp = await self._http.get("/openapi/v3")
            if resp.status_code != 200:
                raise ConnectorError(f"Slurm REST API unreachable: {resp.status_code}")
            logger.info("Slurm connector [%s] connected via REST: %s", self.name, self._rest_url)
        else:
            # Verify CLI availability
            proc = await asyncio.create_subprocess_exec(
                "sinfo", "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                raise ConnectorError("Slurm CLI tools not available (sinfo failed)")
            logger.info("Slurm connector [%s] connected via CLI: %s",
                         self.name, stdout.decode().strip())

    async def disconnect(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # -- submit job ---------------------------------------------------------

    async def submit_job(self, job_spec: dict[str, Any]) -> str:
        if self._rest_url:
            return await self._submit_rest(job_spec)
        return await self._submit_cli(job_spec)

    async def _submit_rest(self, job_spec: dict[str, Any]) -> str:
        """Submit via Slurm REST API POST /slurm/v0.0.40/job/submit."""
        script = job_spec.pop("script", "#!/bin/bash\nhostname")

        job_desc: dict[str, Any] = {
            "name": job_spec.get("name", "ai4s-job"),
            "environment": {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            },
            "tasks": job_spec.get("ntasks", 1),
            "nodes": job_spec.get("nodes", 1),
            "current_working_directory": job_spec.get("workdir", "/tmp"),
            "standard_output": job_spec.get("output", "slurm-%j.out"),
            "standard_error": job_spec.get("error", "slurm-%j.err"),
        }

        if "partition" in job_spec or self._default_partition:
            job_desc["partition"] = job_spec.get("partition", self._default_partition)
        if "account" in job_spec or self._default_account:
            job_desc["account"] = job_spec.get("account", self._default_account)
        if "qos" in job_spec:
            job_desc["qos"] = job_spec["qos"]
        if "time" in job_spec:
            job_desc["time_limit"] = {"number": int(job_spec["time"])}
        if "gpus" in job_spec:
            job_desc["gres"] = f"gpu:{job_spec['gpus']}"
        if "memory" in job_spec:
            job_desc["memory_per_node"] = {"set": True, "number": job_spec["memory"]}

        job_desc["script"] = script

        resp = await self._http.post(
            "/slurm/v0.0.40/job/submit",
            json={"jobs": [job_desc]},
        )
        data = resp.json()

        if resp.status_code != 200 or data.get("errors"):
            raise ConnectorError(f"Slurm submit failed: {data.get('errors', resp.text)}")

        job_id = str(data["jobs"][0]["job_id"])
        logger.info("Slurm job submitted: %s (name=%s)", job_id, job_desc["name"])
        return job_id

    async def _submit_cli(self, job_spec: dict[str, Any]) -> str:
        """Submit via sbatch CLI."""
        script = job_spec.pop("script", "#!/bin/bash\nhostname")

        cmd = ["sbatch", "--parsable"]
        if "partition" in job_spec or self._default_partition:
            cmd.extend(["-p", job_spec.get("partition", self._default_partition)])
        if "account" in job_spec or self._default_account:
            cmd.extend(["-A", job_spec.get("account", self._default_account)])
        if "nodes" in job_spec:
            cmd.extend(["-N", str(job_spec["nodes"])])
        if "ntasks" in job_spec:
            cmd.extend(["-n", str(job_spec["ntasks"])])
        if "cpus_per_task" in job_spec:
            cmd.extend(["-c", str(job_spec["cpus_per_task"])])
        if "gpus" in job_spec:
            cmd.extend([f"--gres=gpu:{job_spec['gpus']}"])
        if "memory" in job_spec:
            cmd.extend([f"--mem={job_spec['memory']}M" if isinstance(job_spec['memory'], int) else f"--mem={job_spec['memory']}"])
        if "time" in job_spec:
            cmd.extend(["-t", str(job_spec["time"])])
        if "qos" in job_spec:
            cmd.extend(["--qos", job_spec["qos"]])
        if "output" in job_spec:
            cmd.extend(["-o", job_spec["output"]])
        if "error" in job_spec:
            cmd.extend(["-e", job_spec["error"]])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=script.encode())
        if proc.returncode != 0:
            raise ConnectorError(f"sbatch failed: {stderr.decode()}")

        job_id = stdout.decode().strip()
        logger.info("Slurm job submitted (CLI): %s", job_id)
        return job_id

    # -- cancel job ---------------------------------------------------------

    async def cancel_job(self, job_id: str) -> bool:
        if self._rest_url:
            resp = await self._http.delete(f"/slurm/v0.0.40/job/{job_id}")
            return resp.status_code == 200

        proc = await asyncio.create_subprocess_exec("scancel", job_id)
        await proc.wait()
        return proc.returncode == 0

    # -- get job ------------------------------------------------------------

    async def get_job(self, job_id: str) -> HPCJob:
        if self._rest_url:
            return await self._get_job_rest(job_id)
        return await self._get_job_cli(job_id)

    async def _get_job_rest(self, job_id: str) -> HPCJob:
        resp = await self._http.get(f"/slurm/v0.0.40/job/{job_id}")
        data = resp.json()
        job_data = data["jobs"][0]

        return HPCJob(
            job_id=str(job_data["job_id"]),
            name=job_data.get("name", ""),
            state=_SLURM_STATE_MAP.get(job_data.get("job_state", ""), JobState.PENDING),
            partition=job_data.get("partition", ""),
            nodes=job_data.get("node_count", 1),
            gpus_per_node=0,  # Parse from gres
            cpu_cores=job_data.get("cpus", 1),
            memory_mb=0,
            wall_time_min=job_data.get("time_limit", {}).get("number", 0),
            submit_time=str(job_data.get("submit_time", "")),
            start_time=str(job_data.get("start_time", "")),
            end_time=str(job_data.get("end_time", "")),
        )

    async def _get_job_cli(self, job_id: str) -> HPCJob:
        proc = await asyncio.create_subprocess_exec(
            "scontrol", "show", "job", job_id, "-o",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()

        # Parse scontrol -o output fields
        fields: dict[str, str] = {}
        for part in output.split():
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k] = v

        return HPCJob(
            job_id=job_id,
            name=fields.get("JobName", ""),
            state=_SLURM_STATE_MAP.get(fields.get("JobState", ""), JobState.PENDING),
            partition=fields.get("Partition", ""),
            nodes=int(fields.get("NumNodes", 1)),
            gpus_per_node=0,
            cpu_cores=int(fields.get("NumCPUs", 1)),
            memory_mb=0,
            wall_time_min=int(int(fields.get("TimeLimit", 0))),
            submit_time=fields.get("SubmitTime", ""),
            start_time=fields.get("StartTime", ""),
            end_time=fields.get("EndTime", ""),
        )

    # -- list jobs ----------------------------------------------------------

    async def list_jobs(self, partition: str | None = None) -> list[HPCJob]:
        if self._rest_url:
            return await self._list_jobs_rest(partition)
        return await self._list_jobs_cli(partition)

    async def _list_jobs_rest(self, partition: str | None = None) -> list[HPCJob]:
        params = {}
        if partition:
            params["partition"] = partition
        resp = await self._http.get("/slurm/v0.0.40/jobs", params=params)
        data = resp.json()
        jobs = []
        for j in data.get("jobs", []):
            jobs.append(HPCJob(
                job_id=str(j["job_id"]), name=j.get("name", ""),
                state=_SLURM_STATE_MAP.get(j.get("job_state", ""), JobState.PENDING),
                partition=j.get("partition", ""), nodes=j.get("node_count", 1),
                gpus_per_node=0, cpu_cores=j.get("cpus", 1), memory_mb=0,
                wall_time_min=j.get("time_limit", {}).get("number", 0),
                submit_time=str(j.get("submit_time", "")),
            ))
        return jobs

    async def _list_jobs_cli(self, partition: str | None = None) -> list[HPCJob]:
        cmd = ["squeue", "-h", "-o", "%A|%j|%T|%P|%D|%C|%m|%M|%V"]
        if partition:
            cmd.extend(["-p", partition])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        jobs = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 9:
                jobs.append(HPCJob(
                    job_id=parts[0], name=parts[1],
                    state=_SLURM_STATE_MAP.get(parts[2], JobState.PENDING),
                    partition=parts[3], nodes=int(parts[4]),
                    cpu_cores=int(parts[5]), memory_mb=0,
                    gpus_per_node=0, wall_time_min=0,
                    submit_time=str(parts[8]),
                ))
        return jobs

    # -- get nodes ----------------------------------------------------------

    async def get_nodes(self) -> list[NodeInfo]:
        if self._rest_url:
            return await self._get_nodes_rest()
        return await self._get_nodes_cli()

    async def _get_nodes_rest(self) -> list[NodeInfo]:
        resp = await self._http.get("/slurm/v0.0.40/nodes")
        data = resp.json()
        nodes = []
        for n in data.get("nodes", []):
            nodes.append(NodeInfo(
                node_id=n.get("name", ""),
                state=n.get("state", "UNKNOWN").lower(),
                cpu_total=n.get("cpus", 0),
                cpu_alloc=n.get("alloc_cpus", 0),
                mem_total_mb=n.get("real_memory", 0),
                mem_alloc_mb=n.get("alloc_memory", 0),
                gpu_total=n.get("gres", "").count("gpu"),
                gpu_alloc=0,
                partitions=n.get("partitions", []),
            ))
        return nodes

    async def _get_nodes_cli(self) -> list[NodeInfo]:
        proc = await asyncio.create_subprocess_exec(
            "sinfo", "-h", "-o", "%n|%t|%c|%C|%m|%m|%G|%P",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        nodes = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 8:
                cpu_alloc_str = parts[3].split("/")[1] if "/" in parts[3] else "0"
                gpus = sum(1 for c in parts[6] if c.isdigit()) if parts[6] else 0

                nodes.append(NodeInfo(
                    node_id=parts[0],
                    state=parts[1].rstrip("*").lower(),
                    cpu_total=int(parts[2]),
                    cpu_alloc=int(cpu_alloc_str) if cpu_alloc_str.isdigit() else 0,
                    mem_total_mb=int(parts[4]),
                    mem_alloc_mb=0,
                    gpu_total=gpus,
                    gpu_alloc=0,
                    partitions=parts[7].split(",") if parts[7] else [],
                ))
        return nodes

    # -- get queue status ---------------------------------------------------

    async def get_queue_status(self) -> dict[str, int]:
        if self._rest_url:
            resp = await self._http.get("/slurm/v0.0.40/jobs")
            data = resp.json()
            pending: dict[str, int] = {}
            for j in data.get("jobs", []):
                if j.get("job_state") == "PENDING":
                    p = j.get("partition", "default")
                    pending[p] = pending.get(p, 0) + 1
            return pending

        proc = await asyncio.create_subprocess_exec(
            "squeue", "-h", "-t", "PENDING", "-o", "%P",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        pending: dict[str, int] = {}
        for part in stdout.decode().strip().split("\n"):
            if part:
                pending[part] = pending.get(part, 0) + 1
        return pending

    # -- accounting ---------------------------------------------------------

    async def job_history(
        self, user: str | None = None, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get job history from Slurm accounting (sacct)."""
        start = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime("%Y-%m-%d")
        cmd = ["sacct", "-S", start, "--format=JobID,JobName,State,Elapsed,CPUTime,MaxRSS", "-P", "-n"]
        if user:
            cmd.extend(["-u", user])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        history = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 6:
                history.append({
                    "job_id": parts[0], "name": parts[1], "state": parts[2],
                    "elapsed": parts[3], "cpu_time": parts[4], "max_rss": parts[5],
                })
        return history
