import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.api import tasks as tasks_api
from gateway.app.main import app
from gateway.app.runners.mock_runner import MockCapabilityRunner
from gateway.app.tasks.models import CapabilityRunResult
from gateway.app.tasks.store import task_store


PRIVATE_RESPONSE_TOKENS = (
    "prompt",
    "trace",
    "skill_text",
    "internal",
    "raw_runner_output",
)


@pytest.fixture(autouse=True)
def clear_task_store() -> None:
    task_store.clear()


def valid_run_request() -> dict[str, Any]:
    return {
        "workspace": {
            "name": "sample-workspace",
            "root_uri": "file:///workspace/sample-workspace",
            "git_branch": "feat/rbac-tightening",
            "git_diff": "diff --git a/app.py b/app.py\n",
            "files": [
                {
                    "path": "app.py",
                    "content": "def hello():\n    return 'world'\n",
                }
            ],
        },
        "instruction": "Review public payload and RBAC boundaries.",
        "options": {
            "return_patch": True,
            "strictness": "high",
        },
        "client": {
            "type": "test",
            "version": "0.1.0",
        },
    }


def assert_no_private_response_tokens(body: dict[str, Any]) -> None:
    serialized = json.dumps(body)
    for token in PRIVATE_RESPONSE_TOKENS:
        assert token not in serialized


def assert_error_shape(body: dict[str, Any], expected_code: str) -> dict[str, Any]:
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    return error


def test_async_run_returns_queued_task_status_and_not_completed_result() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["options"]["async"] = True

    run_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert run_response.status_code == 200
    run_body = run_response.json()
    assert set(run_body) == {"task_id", "status"}
    assert run_body["task_id"].startswith("task_")
    assert run_body["status"] == "queued"
    assert_no_private_response_tokens(run_body)

    status_response = client.get(f"/v1/tasks/{run_body['task_id']}")

    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["task_id"] == run_body["task_id"]
    assert status_body["status"] == "queued"
    assert status_body["capability_id"] == "backend-rbac-review"
    assert isinstance(status_body["created_at"], str)
    assert isinstance(status_body["updated_at"], str)
    assert "request" not in status_body
    assert_no_private_response_tokens(status_body)

    result_response = client.get(f"/v1/tasks/{run_body['task_id']}/result")

    assert result_response.status_code == 409
    result_body = result_response.json()
    assert_error_shape(result_body, "task_not_completed")
    assert_no_private_response_tokens(result_body)


def test_sync_run_stores_completed_result_for_result_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: MockCapabilityRunner(),
    )
    client = TestClient(app)

    run_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert run_response.status_code == 200
    run_body = run_response.json()
    assert run_body["status"] == "completed"

    result_response = client.get(f"/v1/tasks/{run_body['task_id']}/result")

    assert result_response.status_code == 200
    result_body = result_response.json()
    assert result_body == run_body["result"]
    assert "task_id" not in result_body
    assert "status" not in result_body
    assert_no_private_response_tokens(result_body)


def test_cancel_queued_task_transitions_to_cancelled() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["options"]["execution_mode"] = "async"
    task_id = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    ).json()["task_id"]

    cancel_response = client.post(f"/v1/tasks/{task_id}/cancel")

    assert cancel_response.status_code == 200
    cancel_body = cancel_response.json()
    assert cancel_body["task_id"] == task_id
    assert cancel_body["status"] == "cancelled"
    assert_no_private_response_tokens(cancel_body)

    result_response = client.get(f"/v1/tasks/{task_id}/result")
    assert result_response.status_code == 409
    assert_error_shape(result_response.json(), "task_cancelled")


def test_completed_task_cannot_be_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: MockCapabilityRunner(),
    )
    client = TestClient(app)
    task_id = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    ).json()["task_id"]

    cancel_response = client.post(f"/v1/tasks/{task_id}/cancel")

    assert cancel_response.status_code == 409
    cancel_body = cancel_response.json()
    assert_error_shape(cancel_body, "task_not_cancellable")
    assert_no_private_response_tokens(cancel_body)


def test_cancel_returns_conflict_if_store_does_not_cancel_after_initial_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    task = task_store.create_queued("backend-rbac-review")
    completed = task_store.create_completed(
        "backend-rbac-review",
        CapabilityRunResult(
            summary="Already done.",
            safe_rationale="Public result shape only.",
            confidence=0.82,
        ),
    )
    monkeypatch.setattr(tasks_api.task_store, "cancel", lambda _task_id: completed)

    cancel_response = client.post(f"/v1/tasks/{task.task_id}/cancel")

    assert cancel_response.status_code == 409
    cancel_body = cancel_response.json()
    assert_error_shape(cancel_body, "task_not_cancellable")
    assert_no_private_response_tokens(cancel_body)


def test_failed_task_result_returns_redacted_error_envelope() -> None:
    client = TestClient(app)
    raw_message = (
        "Authorization: Bearer raw-failed-token at "
        r"C:\Users\ferry\.codex\skills\secret\SKILL.md"
    )
    task = task_store.create_queued("backend-rbac-review")
    task_store.mark_running(task.task_id)
    task_store.mark_failed(
        task.task_id,
        code="internal_prompt_trace_skill_text_raw_runner_output",
        message=f"Task failed with prompt trace skill_text internal raw_runner_output {raw_message}",
        details={
            "api_key": "sk-proj-taskfailed123456",
            "prompt": "raw prompt content",
            "raw_runner_output": "raw runner dump",
        },
    )

    response = client.get(f"/v1/tasks/{task.task_id}/result")

    assert response.status_code == 502
    body = response.json()
    error = assert_error_shape(body, "task_failed")
    assert error["message"] == "Task failed."
    assert error["details"] == {}
    assert_no_private_response_tokens(body)
    serialized = json.dumps(body)
    assert "raw-failed-token" not in serialized
    assert r"C:\Users\ferry" not in serialized
    assert "sk-proj-taskfailed123456" not in serialized
    assert "raw prompt content" not in serialized
    assert "raw runner dump" not in serialized


def test_missing_task_status_result_and_cancel_return_404() -> None:
    client = TestClient(app)

    status_response = client.get("/v1/tasks/task_missing")
    result_response = client.get("/v1/tasks/task_missing/result")
    cancel_response = client.post("/v1/tasks/task_missing/cancel")

    assert status_response.status_code == 404
    assert_error_shape(status_response.json(), "task_not_found")
    assert result_response.status_code == 404
    assert_error_shape(result_response.json(), "task_not_found")
    assert cancel_response.status_code == 404
    assert_error_shape(cancel_response.json(), "task_not_found")


def test_task_result_model_rejects_private_result_keys() -> None:
    with pytest.raises(Exception):
        CapabilityRunResult(
            summary="unsafe",
            safe_rationale="unsafe",
            confidence=0.5,
            raw_runner_output="raw",
        )
