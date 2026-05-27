from fastapi import APIRouter

from .errors import api_error
from ..security.output_filter import filter_capability_run_result
from ..tasks.models import CapabilityTaskStatus
from ..tasks.store import TaskRecord, task_store

router = APIRouter(prefix="/v1/tasks")


@router.get("/{task_id}")
def get_task_status(task_id: str) -> dict:
    task = _get_task_or_404(task_id)
    return CapabilityTaskStatus(
        task_id=task.task_id,
        status=task.status,
        capability_id=task.capability_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    ).model_dump(mode="json")


@router.get("/{task_id}/result")
def get_task_result(task_id: str) -> dict:
    task = _get_task_or_404(task_id)
    if task.status in {"queued", "running"}:
        raise api_error(
            status_code=409,
            code="task_not_completed",
            message="Task is not completed.",
        )
    if task.status == "cancelled":
        raise api_error(
            status_code=409,
            code="task_cancelled",
            message="Task was cancelled.",
        )
    if task.status == "failed":
        raise api_error(
            status_code=502,
            code="task_failed",
            message="Task failed.",
            details={},
        )

    if task.result is None:
        raise api_error(
            status_code=409,
            code="task_not_completed",
            message="Task is not completed.",
        )

    result = filter_capability_run_result(task.result)
    return result.model_dump()


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str) -> dict:
    task = _get_task_or_404(task_id)
    if task.status not in {"queued", "running"}:
        raise _task_not_cancellable()

    cancelled = task_store.cancel(task_id)
    if cancelled is None:
        raise _task_not_found()
    if cancelled.status != "cancelled":
        raise _task_not_cancellable()
    return CapabilityTaskStatus(
        task_id=cancelled.task_id,
        status=cancelled.status,
        capability_id=cancelled.capability_id,
        created_at=cancelled.created_at,
        updated_at=cancelled.updated_at,
    ).model_dump(mode="json")


def _get_task_or_404(task_id: str) -> TaskRecord:
    task = task_store.get(task_id)
    if task is None:
        raise _task_not_found()
    return task


def _task_not_found() -> Exception:
    return api_error(
        status_code=404,
        code="task_not_found",
        message="Task not found.",
    )


def _task_not_cancellable() -> Exception:
    return api_error(
        status_code=409,
        code="task_not_cancellable",
        message="Task cannot be cancelled.",
    )
