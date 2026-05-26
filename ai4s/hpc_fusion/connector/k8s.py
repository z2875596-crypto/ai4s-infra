"""Kubernetes connector — manages containerized HPC/AI workloads via K8s with Volcano.

Supports:
  - Native K8s Jobs (batch/v1)
  - Volcano batch scheduler (volcano.sh/v1alpha1 — PodGroup, priority, gang scheduling)
  - Kueue (kueue.x-k8s.io — resource quota/queue management)
  - GPU scheduling (nvidia.com/gpu resource)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from kubernetes import client, config, watch
from kubernetes.client import (
    BatchV1Api,
    CoreV1Api,
    V1Job,
    V1JobSpec,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Container,
    V1ResourceRequirements,
    V1EnvVar,
    V1VolumeMount,
    V1Volume,
    V1HostPathVolumeSource,
)

from ai4s.common.exceptions import ConnectorError
from ai4s.common.logging import get_logger
from ai4s.hpc_fusion.connector.base import HPCConnector, HPCJob, JobState, NodeInfo

logger = get_logger(__name__)

# Job state mapping
_POD_PHASE_MAP: dict[str, JobState] = {
    "Pending": JobState.PENDING,
    "Running": JobState.RUNNING,
    "Succeeded": JobState.COMPLETED,
    "Failed": JobState.FAILED,
    "Unknown": JobState.PENDING,
}


class K8sConnector(HPCConnector):
    """Kubernetes connector for containerized AI/HPC workloads.

    Config:
      context        : str  — kubeconfig context name
      namespace      : str  — default namespace
      scheduler      : str  — "default" | "volcano" | "kueue"
      volcano_queue  : str  — Volcano queue name
      kueue_local_queue  : str
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        super().__init__(name, config)
        self._namespace = config.get("namespace", "ai4s-compute")
        self._context = config.get("context", "")
        self._scheduler_name = config.get("scheduler", "default")
        self._volcano_queue = config.get("volcano_queue", "default")
        self._batch_v1: BatchV1Api | None = None
        self._core_v1: CoreV1Api | None = None

    # -- connect / disconnect -----------------------------------------------

    async def connect(self) -> None:
        if self._context:
            config.load_kube_config(context=self._context)
        else:
            try:
                config.load_incluster_config()  # Running inside K8s
            except config.ConfigException:
                config.load_kube_config()       # Fallback to ~/.kube/config

        self._batch_v1 = BatchV1Api()
        self._core_v1 = CoreV1Api()
        logger.info("K8s connector [%s] connected (ns=%s, scheduler=%s)",
                     self.name, self._namespace, self._scheduler_name)

    async def disconnect(self) -> None:
        if self._batch_v1:
            self._batch_v1.api_client.close()

    # -- submit job ---------------------------------------------------------

    async def submit_job(self, job_spec: dict[str, Any]) -> str:
        job_name = job_spec.get("name", f"ai4s-job-{datetime.now().strftime('%Y%m%d%H%M%S')}")

        if self._scheduler_name == "volcano":
            return await self._submit_volcano_job(job_name, job_spec)
        else:
            return await self._submit_native_job(job_name, job_spec)

    async def _submit_native_job(self, job_name: str, job_spec: dict[str, Any]) -> str:
        # Build container
        env = [V1EnvVar(name=k, value=str(v)) for k, v in job_spec.get("env", {}).items()]
        volume_mounts = []
        volumes = []
        for vm in job_spec.get("volumes", []):
            volume_mounts.append(V1VolumeMount(name=vm["name"], mount_path=vm["mount_path"]))
            volumes.append(V1Volume(
                name=vm["name"],
                host_path=V1HostPathVolumeSource(path=vm["host_path"]),
            ))

        resources = V1ResourceRequirements(
            requests={
                "cpu": str(job_spec.get("cpus", 1)),
                "memory": f"{job_spec.get('memory_gb', 4)}Gi",
                "nvidia.com/gpu": str(job_spec.get("gpus", 0)),
            },
            limits={
                "cpu": str(job_spec.get("cpus", 1)),
                "memory": f"{job_spec.get('memory_gb', 4)}Gi",
                "nvidia.com/gpu": str(job_spec.get("gpus", 0)),
            },
        )

        container = V1Container(
            name="worker",
            image=job_spec.get("image", "nvidia/cuda:12.1-runtime"),
            command=job_spec.get("command", ["/bin/bash", "-c"]),
            args=job_spec.get("args", [job_spec.get("script", "echo 'Hello'")]),
            env=env,
            volume_mounts=volume_mounts if volume_mounts else None,
            resources=resources,
        )

        pod_spec = V1PodSpec(
            containers=[container],
            restart_policy=job_spec.get("restart_policy", "Never"),
            volumes=volumes if volumes else None,
            node_selector=job_spec.get("node_selector"),
            tolerations=job_spec.get("tolerations"),
        )

        # Volcano scheduler name annotation
        annotations = {}
        if self._scheduler_name == "volcano":
            annotations["scheduling.k8s.io/group-name"] = job_name

        template = V1PodTemplateSpec(
            metadata=V1ObjectMeta(labels={"app": "ai4s-hpc", "job-name": job_name}, annotations=annotations),
            spec=pod_spec,
        )

        job = V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=V1ObjectMeta(name=job_name, namespace=self._namespace, annotations=annotations),
            spec=V1JobSpec(
                template=template,
                backoff_limit=job_spec.get("backoff_limit", 0),
                completions=job_spec.get("completions", 1),
                parallelism=job_spec.get("parallelism", 1),
                ttl_seconds_after_finished=job_spec.get("ttl_seconds", 86400),
            ),
        )

        result = self._batch_v1.create_namespaced_job(self._namespace, job)
        job_id = result.metadata.name
        logger.info("K8s native job submitted: %s (gpus=%s)", job_id, job_spec.get("gpus", 0))
        return job_id

    async def _submit_volcano_job(self, job_name: str, job_spec: dict[str, Any]) -> str:
        # Volcano vcjob — uses volcano.sh/v1alpha1 Job
        # This is a custom resource; in production use the volcano SDK or kubernetes dynamic client
        from kubernetes import dynamic

        dyn_client = dynamic.DynamicClient(client.ApiClient())

        vcjob = {
            "apiVersion": "batch.volcano.sh/v1alpha1",
            "kind": "Job",
            "metadata": {"name": job_name, "namespace": self._namespace},
            "spec": {
                "minAvailable": job_spec.get("min_available", 1),
                "schedulerName": "volcano",
                "queue": self._volcano_queue,
                "tasks": [{
                    "replicas": job_spec.get("nodes", 1),
                    "name": "worker",
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "worker",
                                "image": job_spec.get("image", "nvidia/cuda:12.1-runtime"),
                                "command": job_spec.get("command", ["/bin/bash", "-c"]),
                                "args": [job_spec.get("script", "echo 'hello'")],
                                "resources": {
                                    "requests": {
                                        "cpu": str(job_spec.get("cpus", 1)),
                                        "memory": f"{job_spec.get('memory_gb', 4)}Gi",
                                        "nvidia.com/gpu": str(job_spec.get("gpus", 0)),
                                    },
                                    "limits": {
                                        "cpu": str(job_spec.get("cpus", 1)),
                                        "memory": f"{job_spec.get('memory_gb', 4)}Gi",
                                        "nvidia.com/gpu": str(job_spec.get("gpus", 0)),
                                    },
                                },
                            }],
                            "restartPolicy": "Never",
                        }
                    },
                }],
            },
        }

        # Create via dynamic client
        volcano_api = dyn_client.resources.get(api_version="batch.volcano.sh/v1alpha1", kind="Job")
        result = volcano_api.create(body=vcjob, namespace=self._namespace)
        job_id = result.metadata.name
        logger.info("Volcano job submitted: %s (queue=%s)", job_id, self._volcano_queue)
        return job_id

    # -- cancel / get / list ------------------------------------------------

    async def cancel_job(self, job_id: str) -> bool:
        try:
            self._batch_v1.delete_namespaced_job(
                job_id, self._namespace,
                propagation_policy="Background",
            )
            return True
        except client.ApiException as e:
            if e.status == 404:
                return False
            raise ConnectorError(f"Failed to cancel K8s job {job_id}: {e}")

    async def get_job(self, job_id: str) -> HPCJob:
        try:
            k8s_job = self._batch_v1.read_namespaced_job(job_id, self._namespace)
            return self._k8s_job_to_hpc(k8s_job)
        except client.ApiException:
            raise ConnectorError(f"Job not found: {job_id}")

    async def list_jobs(self, partition: str | None = None) -> list[HPCJob]:
        jobs = self._batch_v1.list_namespaced_job(self._namespace)
        result = []
        for j in jobs.items:
            hpc_job = self._k8s_job_to_hpc(j)
            if partition:
                labels = j.metadata.labels or {}
                if labels.get("partition") != partition:
                    continue
            result.append(hpc_job)
        return result

    async def get_nodes(self) -> list[NodeInfo]:
        nodes = self._core_v1.list_node()
        result = []
        for n in nodes.items:
            allocatable = n.status.allocatable or {}
            capacity = n.status.capacity or {}
            # Node conditions
            conditions = {c.type: c.status for c in (n.status.conditions or [])}
            is_ready = conditions.get("Ready") == "True"

            result.append(NodeInfo(
                node_id=n.metadata.name,
                state="idle" if is_ready else "down",
                cpu_total=int(capacity.get("cpu", 0)),
                cpu_alloc=int(capacity.get("cpu", 0)) - int(allocatable.get("cpu", 0)),
                mem_total_mb=int(capacity.get("memory", "0Ki").rstrip("Ki")) // 1024,
                mem_alloc_mb=(int(capacity.get("memory", "0Ki").rstrip("Ki")) - int(allocatable.get("memory", "0Ki").rstrip("Ki"))) // 1024,
                gpu_total=int(capacity.get("nvidia.com/gpu", 0)),
                gpu_alloc=int(capacity.get("nvidia.com/gpu", 0)) - int(allocatable.get("nvidia.com/gpu", 0)),
                partitions=[self._namespace],
            ))
        return result

    async def get_queue_status(self) -> dict[str, int]:
        """Return pending job counts."""
        jobs = self._batch_v1.list_namespaced_job(self._namespace)
        pending = 0
        for j in jobs.items:
            if not j.status.active and not j.status.succeeded and not j.status.failed:
                pending += 1
        return {self._namespace: pending}

    # -- helpers ------------------------------------------------------------

    def _k8s_job_to_hpc(self, k8s_job) -> HPCJob:
        s = k8s_job.status
        if s.active:
            state = JobState.RUNNING
        elif s.succeeded:
            state = JobState.COMPLETED
        elif s.failed:
            state = JobState.FAILED
        else:
            state = JobState.PENDING

        containers = (k8s_job.spec.template.spec.containers or [])
        resources = containers[0].resources.requests if containers else {}
        gpus = int(resources.get("nvidia.com/gpu", 0)) if resources else 0

        return HPCJob(
            job_id=k8s_job.metadata.name,
            name=k8s_job.metadata.name,
            state=state,
            partition=k8s_job.metadata.labels.get("partition", "") if k8s_job.metadata.labels else "",
            nodes=k8s_job.spec.parallelism or 1,
            gpus_per_node=gpus,
            cpu_cores=int(resources.get("cpu", 1)) if resources else 1,
            memory_mb=0,
            wall_time_min=0,
            submit_time=str(k8s_job.metadata.creation_timestamp),
            start_time=str(s.start_time) if s.start_time else None,
        )

    async def get_pod_logs(self, job_id: str, tail_lines: int = 100) -> str:
        """Get logs from the pod(s) of a job."""
        pods = self._core_v1.list_namespaced_pod(
            self._namespace,
            label_selector=f"job-name={job_id}",
        )
        logs = []
        for pod in pods.items:
            try:
                log = self._core_v1.read_namespaced_pod_log(
                    pod.metadata.name, self._namespace, tail_lines=tail_lines
                )
                logs.append(f"--- {pod.metadata.name} ---\n{log}")
            except client.ApiException:
                pass
        return "\n".join(logs)
