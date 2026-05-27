from gateway.app.tasks.models import CapabilityRunResult
from gateway.app.tasks.store import InMemoryTaskStore


def public_result(summary: str = "Initial summary.") -> CapabilityRunResult:
    return CapabilityRunResult(
        summary=summary,
        safe_rationale="Public result shape only.",
        confidence=0.82,
    )


def test_terminal_tasks_are_not_revived_or_overwritten_by_worker_updates() -> None:
    store = InMemoryTaskStore()

    cancelled = store.create_queued("backend-rbac-review")
    store.cancel(cancelled.task_id)
    store.mark_running(cancelled.task_id)
    store.mark_failed(
        cancelled.task_id,
        code="runner_failed",
        message="Runner failed.",
    )

    assert store.get(cancelled.task_id).status == "cancelled"

    completed = store.create_completed("backend-rbac-review", public_result())
    store.mark_running(completed.task_id)
    store.mark_failed(
        completed.task_id,
        code="runner_failed",
        message="Runner failed.",
    )

    completed_after_updates = store.get(completed.task_id)
    assert completed_after_updates.status == "completed"
    assert completed_after_updates.result.summary == "Initial summary."

    failed = store.create_queued("backend-rbac-review")
    store.mark_running(failed.task_id)
    store.mark_failed(
        failed.task_id,
        code="runner_failed",
        message="Runner failed.",
    )
    store.cancel(failed.task_id)

    assert store.get(failed.task_id).status == "failed"


def test_mark_failed_only_allows_running_to_failed() -> None:
    store = InMemoryTaskStore()
    queued = store.create_queued("backend-rbac-review")

    store.mark_failed(
        queued.task_id,
        code="runner_failed",
        message="Runner failed.",
    )

    assert store.get(queued.task_id).status == "queued"


def test_create_completed_copies_result_before_storing() -> None:
    store = InMemoryTaskStore()
    result = public_result("Stored summary.")

    task = store.create_completed("backend-rbac-review", result)
    result.summary = "Mutated outside store."

    stored = store.get(task.task_id)
    assert stored.result.summary == "Stored summary."


def test_create_completed_returns_copy_not_mutable_store_state() -> None:
    store = InMemoryTaskStore()

    task = store.create_completed(
        "backend-rbac-review",
        public_result("Stored summary."),
    )
    task.result.summary = "Mutated returned task."

    stored = store.get(task.task_id)
    assert stored.result.summary == "Stored summary."


def test_get_returns_copy_and_failed_error_details_are_not_mutable_store_state() -> None:
    store = InMemoryTaskStore()
    task = store.create_queued("backend-rbac-review")
    store.mark_running(task.task_id)
    store.mark_failed(
        task.task_id,
        code="internal_prompt_trace",
        message="raw prompt trace should not persist",
        details={"prompt": "raw prompt content"},
    )

    returned = store.get(task.task_id)
    returned.error.details["new"] = "mutated outside store"

    stored = store.get(task.task_id)
    assert stored.error.code == "task_failed"
    assert stored.error.message == "Task failed."
    assert stored.error.details == {}
