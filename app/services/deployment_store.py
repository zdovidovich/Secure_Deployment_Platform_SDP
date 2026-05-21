import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from services.deployment import DeploymentService


@dataclass
class DeploymentJob:
    deployment_id: str
    service: DeploymentService
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DeploymentStore:
    """Thread-safe in-memory store for active deployment jobs."""

    def __init__(self):
        self._jobs: Dict[str, DeploymentJob] = {}
        self._lock = threading.Lock()

    def create(self) -> DeploymentJob:
        deployment_id = uuid.uuid4().hex[:12]
        job = DeploymentJob(
            deployment_id=deployment_id,
            service=DeploymentService(deployment_id),
        )
        with self._lock:
            self._jobs[deployment_id] = job
        return job

    def get(self, deployment_id: str) -> Optional[DeploymentJob]:
        with self._lock:
            return self._jobs.get(deployment_id)

    def remove(self, deployment_id: str) -> None:
        with self._lock:
            self._jobs.pop(deployment_id, None)


deployment_store = DeploymentStore()
