from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .models import CapabilityRunResult, TaskError, TaskStatus

if TYPE_CHECKING:
    from gateway.app.auth.models import RequestIdentity


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    capability_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    result: CapabilityRunResult | None = None
    error: TaskError | None = None
    owner_auth_mode: str | None = None
    owner_tenant_id: str | None = None
    owner_role: str | None = None
    owner_token_id: str | None = None


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = RLock()

    def create_queued(
        self,
        capability_id: str,
        owner_identity: "RequestIdentity | None" = None,
    ) -> TaskRecord:
        now = _utc_now()
        task = TaskRecord(
            task_id=f"task_{uuid4().hex}",
            capability_id=capability_id,
            status="queued",
            created_at=now,
            updated_at=now,
            **_owner_fields(owner_identity),
        )
        with self._lock:
            self._tasks[task.task_id] = task
        return _copy_existing_task(task)

    def create_completed(
        self,
        capability_id: str,
        result: CapabilityRunResult,
        owner_identity: "RequestIdentity | None" = None,
    ) -> TaskRecord:
        now = _utc_now()
        stored_result = result.model_copy(deep=True)
        task = TaskRecord(
            task_id=f"task_{uuid4().hex}",
            capability_id=capability_id,
            status="completed",
            created_at=now,
            updated_at=now,
            result=stored_result,
            **_owner_fields(owner_identity),
        )
        with self._lock:
            self._tasks[task.task_id] = task
        return _copy_existing_task(task)

    def mark_running(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != "queued":
                return _copy_task(task)
            updated = TaskRecord(
                task_id=task.task_id,
                capability_id=task.capability_id,
                status="running",
                created_at=task.created_at,
                updated_at=_utc_now(),
                result=task.result,
                error=task.error,
                owner_auth_mode=task.owner_auth_mode,
                owner_tenant_id=task.owner_tenant_id,
                owner_role=task.owner_role,
                owner_token_id=task.owner_token_id,
            )
            self._tasks[task_id] = updated
            return _copy_task(updated)

    def mark_failed(
        self,
        task_id: str,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != "running":
                return _copy_task(task)
            updated = TaskRecord(
                task_id=task.task_id,
                capability_id=task.capability_id,
                status="failed",
                created_at=task.created_at,
                updated_at=_utc_now(),
                error=TaskError(
                    code="task_failed",
                    message="Task failed.",
                    details={},
                ),
                owner_auth_mode=task.owner_auth_mode,
                owner_tenant_id=task.owner_tenant_id,
                owner_role=task.owner_role,
                owner_token_id=task.owner_token_id,
            )
            self._tasks[task_id] = updated
            return _copy_task(updated)

    def cancel(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status not in {"queued", "running"}:
                return _copy_task(task)
            updated = TaskRecord(
                task_id=task.task_id,
                capability_id=task.capability_id,
                status="cancelled",
                created_at=task.created_at,
                updated_at=_utc_now(),
                owner_auth_mode=task.owner_auth_mode,
                owner_tenant_id=task.owner_tenant_id,
                owner_role=task.owner_role,
                owner_token_id=task.owner_token_id,
            )
            self._tasks[task_id] = updated
            return _copy_task(updated)

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return _copy_task(self._tasks.get(task_id))

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _copy_existing_task(task: TaskRecord) -> TaskRecord:
    return deepcopy(task)


def _copy_task(task: TaskRecord | None) -> TaskRecord | None:
    return _copy_existing_task(task) if task is not None else None


def _owner_fields(identity: "RequestIdentity | None") -> dict[str, str | None]:
    if identity is None:
        return {
            "owner_auth_mode": None,
            "owner_tenant_id": None,
            "owner_role": None,
            "owner_token_id": None,
        }
    return {
        "owner_auth_mode": identity.auth_mode,
        "owner_tenant_id": identity.tenant_id,
        "owner_role": identity.role,
        "owner_token_id": identity.token_id,
    }


task_store = InMemoryTaskStore()
