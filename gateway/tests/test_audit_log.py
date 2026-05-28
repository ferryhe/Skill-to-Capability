import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.audit.models import AuditActor
from gateway.app.audit.store import audit_store
from gateway.app.main import app
from gateway.app.runners.mock_runner import MockCapabilityRunner
from gateway.app.tasks.store import task_store


RAW_SECRET = "sk-proj-auditsecret123456"
GITHUB_TOKEN = "ghp_abcdef1234567890"
SLACK_TOKEN = "xoxb-123456789012-abcdefghi"
RAW_INSTRUCTION = f"Review this without leaking {RAW_SECRET}"
RAW_FILE_CONTENT = "def hello():\n    return 'world'\n"
RAW_DIFF = "diff --git a/app.py b/app.py\n+print('hello')\n"

PRIVATE_AUDIT_TOKENS = (
    RAW_SECRET,
    GITHUB_TOKEN,
    SLACK_TOKEN,
    RAW_INSTRUCTION,
    RAW_FILE_CONTENT,
    RAW_DIFF,
    "raw_runner_output",
    "prompt",
    "skill_text",
    "internal system prompt",
    "Authorization: Bearer",
)


@pytest.fixture(autouse=True)
def clear_stores() -> None:
    task_store.clear()
    audit_store.clear()


def valid_run_request() -> dict[str, Any]:
    return {
        "workspace": {
            "name": "sample-workspace",
            "root_uri": "file:///workspace/sample-workspace",
            "git_branch": "feat/rbac-tightening",
            "git_diff": RAW_DIFF,
            "files": [
                {
                    "path": "app.py",
                    "content": RAW_FILE_CONTENT,
                }
            ],
        },
        "instruction": RAW_INSTRUCTION,
        "options": {
            "return_patch": True,
            "strictness": "high",
        },
        "client": {
            "type": "test",
            "version": "0.1.0",
        },
    }


def assert_audit_is_sanitized(events: list[Any]) -> None:
    serialized = json.dumps([event.model_dump(mode="json") for event in events])
    for token in PRIVATE_AUDIT_TOKENS:
        assert token not in serialized


def test_async_run_and_cancel_record_sanitized_task_lifecycle() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["options"]["async"] = True

    run_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )
    task_id = run_response.json()["task_id"]
    cancel_response = client.post(f"/v1/tasks/{task_id}/cancel")

    assert run_response.status_code == 200
    assert cancel_response.status_code == 200
    events = audit_store.list_for_task(task_id)
    assert [event.action for event in events] == ["queued", "cancelled"]
    queued = events[0]
    assert queued.event_type == "task_lifecycle"
    assert queued.capability_id == "backend-rbac-review"
    assert queued.actor is not None
    assert queued.actor.tenant_id == "default"
    assert queued.actor.role == "developer"
    assert queued.input_metadata == {
        "execution_mode": "async",
        "instruction_length": len(RAW_INSTRUCTION),
        "workspace_file_count": 1,
        "workspace_file_bytes": len(RAW_FILE_CONTENT.encode("utf-8")),
        "has_git_diff": True,
        "git_diff_bytes": len(RAW_DIFF.encode("utf-8")),
        "has_selection": False,
        "selection_bytes": 0,
        "option_count": 3,
        "client_type": "test",
    }
    assert events[1].output_metadata == {"status": "cancelled"}
    assert_audit_is_sanitized(events)


def test_sync_completed_run_records_sanitized_output_metadata(
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
    task_id = run_response.json()["task_id"]
    events = audit_store.list_for_task(task_id)
    assert [event.action for event in events] == ["completed"]
    completed = events[0]
    assert completed.output_metadata is not None
    assert completed.output_metadata["status"] == "completed"
    assert completed.output_metadata["result_keys"] == [
        "artifacts",
        "confidence",
        "findings",
        "patch",
        "recommended_tests",
        "safe_rationale",
        "summary",
    ]
    assert completed.output_metadata["finding_count"] == 0
    assert completed.output_metadata["artifact_count"] == 0
    assert completed.output_metadata["recommended_test_count"] == 1
    assert completed.output_metadata["patch_present"] is False
    assert isinstance(completed.output_metadata["result_size_bytes"], int)
    assert_audit_is_sanitized(events)


def test_store_transitions_record_running_and_failed_error_code_only() -> None:
    task = task_store.create_queued("backend-rbac-review")
    task_store.mark_running(task.task_id)
    task_store.mark_failed(
        task.task_id,
        code="runner_failed",
        message=f"raw_runner_output {RAW_SECRET}",
        details={"prompt": RAW_INSTRUCTION, "api_key": RAW_SECRET},
    )

    events = audit_store.list_for_task(task.task_id)
    assert [event.action for event in events] == ["queued", "running", "failed"]
    assert events[-1].output_metadata == {
        "status": "failed",
        "error_code": "task_failed",
    }
    assert_audit_is_sanitized(events)


def test_approval_event_support_records_sanitized_metadata() -> None:
    event = audit_store.record_approval_event(
        action="approved",
        capability_id="backend-rbac-review",
        task_id="task_manual",
        actor=None,
        approval_metadata={
            "approval_type": "apply_patch",
            "decision": "approved",
            "raw_prompt": RAW_INSTRUCTION,
            "secret": RAW_SECRET,
        },
    )

    events = audit_store.list_for_task("task_manual")
    assert events == [event]
    assert event.event_type == "approval"
    assert event.action == "approved"
    assert event.approval_metadata == {
        "approval_type": "apply_patch",
        "decision": "approved",
    }
    assert_audit_is_sanitized(events)


def test_approval_metadata_drops_raw_values_in_allowed_keys() -> None:
    event = audit_store.record_approval_event(
        action="approved",
        capability_id="backend-rbac-review",
        task_id="task_approval_raw",
        actor=None,
        approval_metadata={
            "approval_type": RAW_SECRET,
            "decision": RAW_INSTRUCTION,
        },
    )

    assert event.approval_metadata is None
    assert_audit_is_sanitized([event])


def test_task_metadata_drops_raw_values_in_allowed_keys() -> None:
    event = audit_store.record_task_lifecycle(
        action="failed",
        capability_id="backend-rbac-review",
        task_id="task_metadata_raw",
        input_metadata={
            "execution_mode": RAW_SECRET,
            "client_type": RAW_INSTRUCTION,
            "instruction_length": len(RAW_INSTRUCTION),
            "has_git_diff": True,
        },
        output_metadata={
            "status": RAW_SECRET,
            "error_code": f"runner_failed_{RAW_SECRET}",
            "result_keys": ["summary", RAW_INSTRUCTION],
            "finding_count": 1,
            "patch_present": False,
        },
    )

    assert event.input_metadata == {
        "instruction_length": len(RAW_INSTRUCTION),
        "has_git_diff": True,
    }
    assert event.output_metadata == {
        "finding_count": 1,
        "patch_present": False,
    }
    assert_audit_is_sanitized([event])


def test_store_normalizes_caller_supplied_audit_actor() -> None:
    event = audit_store.record_task_lifecycle(
        action="queued",
        capability_id="backend-rbac-review",
        task_id="task_actor_raw",
        actor=AuditActor(
            auth_mode=f"token-{RAW_SECRET}",
            tenant_id=f"tenant-{RAW_SECRET}",
            role="admin",
            token_id=RAW_SECRET,
        ),
        input_metadata={"execution_mode": "async"},
    )

    assert event.actor is None
    assert_audit_is_sanitized([event])

    token_event = audit_store.record_task_lifecycle(
        action="queued",
        capability_id="backend-rbac-review",
        task_id="task_actor_token_raw",
        actor=AuditActor(
            auth_mode="token",
            tenant_id="tenant-a",
            role="viewer",
            token_id=RAW_SECRET,
        ),
        input_metadata={"execution_mode": "async"},
    )

    assert token_event.actor is not None
    assert token_event.actor.auth_mode == "token"
    assert token_event.actor.tenant_id == "tenant-a"
    assert token_event.actor.role == "viewer"
    assert token_event.actor.token_id is None
    assert_audit_is_sanitized([token_event])


def test_store_normalizes_raw_actions() -> None:
    task_event = audit_store.record_task_lifecycle(
        action=RAW_INSTRUCTION,
        capability_id="backend-rbac-review",
        task_id="task_action_raw",
        input_metadata={"execution_mode": "async"},
    )
    approval_event = audit_store.record_approval_event(
        action=RAW_SECRET,
        capability_id="backend-rbac-review",
        task_id="task_action_raw",
        actor=None,
        approval_metadata={"approval_type": "apply_patch", "decision": "approved"},
    )

    assert task_event.action == "unknown"
    assert approval_event.action == "unknown"
    assert_audit_is_sanitized([task_event, approval_event])


def test_store_normalizes_raw_lifecycle_ids() -> None:
    event = audit_store.record_task_lifecycle(
        action="queued",
        capability_id=RAW_SECRET,
        task_id=f"task_{RAW_SECRET}",
        input_metadata={"execution_mode": "async"},
    )

    assert event.capability_id is None
    assert event.task_id is None
    assert_audit_is_sanitized([event])

    token_event = audit_store.record_task_lifecycle(
        action="queued",
        capability_id=SLACK_TOKEN,
        task_id=f"task_{GITHUB_TOKEN}",
        input_metadata={"execution_mode": "async"},
    )

    assert token_event.capability_id is None
    assert token_event.task_id is None
    assert_audit_is_sanitized([token_event])


def test_store_normalizes_raw_approval_ids() -> None:
    event = audit_store.record_approval_event(
        action="approved",
        capability_id=RAW_SECRET,
        task_id=f"task_{RAW_SECRET}",
        actor=None,
        approval_metadata={"approval_type": "apply_patch", "decision": "approved"},
    )

    assert event.capability_id is None
    assert event.task_id is None
    assert_audit_is_sanitized([event])


def test_store_drops_non_sk_token_shapes_in_metadata() -> None:
    event = audit_store.record_task_lifecycle(
        action="failed",
        capability_id="backend-rbac-review",
        task_id="task_non_sk_metadata",
        output_metadata={
            "status": "failed",
            "error_code": GITHUB_TOKEN,
            "result_keys": ["summary", SLACK_TOKEN],
            "finding_count": 1,
        },
    )

    assert event.output_metadata == {
        "status": "failed",
        "finding_count": 1,
    }
    assert_audit_is_sanitized([event])
