import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gateway.app.api import capabilities as capabilities_api
from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import default_registry
from gateway.app.main import app
from gateway.app.tasks.models import CapabilityRunResult


PRIVATE_RESPONSE_TOKENS = (
    "prompt",
    "trace",
    "skill_text",
    "internal",
    "skill_ref",
    "model_policy",
)
SECRET_LIKE_SELECTION_CONTENT = 'OPENAI_API_KEY = "sk-proj-secretvalue"'


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


def assert_policy_error(response_body: dict[str, Any], expected_code: str) -> None:
    error = response_body["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)


class StubRegistry:
    def __init__(self, capability: CapabilityManifest) -> None:
        self._capability = capability

    def find(self, capability_id: str) -> CapabilityManifest | None:
        if capability_id == self._capability.id:
            return self._capability
        return None


def backend_rbac_capability() -> CapabilityManifest:
    capability = default_registry().find("backend-rbac-review")
    assert capability is not None
    return capability


def capability_with(
    *,
    capability_id: str | None = None,
    input_modes: list[str] | None = None,
    runner: str = "mock",
) -> CapabilityManifest:
    capability = backend_rbac_capability()
    return capability.model_copy(
        update={
            "id": capability_id or capability.id,
            "input_modes": input_modes or capability.input_modes,
            "internal": capability.internal.model_copy(update={"runner": runner}),
        }
    )


def use_capability(monkeypatch: pytest.MonkeyPatch, capability: CapabilityManifest) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "default_registry",
        lambda: StubRegistry(capability),
    )


def test_backend_rbac_review_manifest_uses_hermes_runner_for_d3() -> None:
    assert backend_rbac_capability().internal.runner == "hermes"


def test_run_capability_returns_completed_mock_result_public_fields_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(runner="mock"))
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["task_id"], str)
    assert body["task_id"]
    assert body["status"] == "completed"

    result = body["result"]
    assert set(result) == {
        "summary",
        "findings",
        "patch",
        "recommended_tests",
        "artifacts",
        "safe_rationale",
        "confidence",
    }
    assert isinstance(result["summary"], str)
    assert isinstance(result["findings"], list)
    assert result["patch"] is None or isinstance(result["patch"], str)
    assert isinstance(result["recommended_tests"], list)
    assert isinstance(result["artifacts"], list)
    assert isinstance(result["safe_rationale"], str)
    assert 0 <= result["confidence"] <= 1
    assert_no_private_response_tokens(body)


def test_mock_runner_returns_sample_rbac_patch_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(runner="mock"))
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = [
        {
            "path": "app.py",
            "content": "\n".join(
                [
                    "from dataclasses import dataclass",
                    "",
                    "",
                    "@dataclass(frozen=True)",
                    "class User:",
                    "    username: str",
                    "    role: str",
                    "    is_active: bool = True",
                    "",
                    "",
                    "def can_view_admin_report(user: User) -> bool:",
                    "    # BUG: this grants every active user access to the admin report.",
                    "    return user.is_active",
                    "",
                ]
            ),
        }
    ]
    request_body["options"]["return_patch"] = True

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 200
    body = response.json()
    result = body["result"]
    assert result["patch"].startswith("diff --git a/app.py b/app.py\n")
    assert "-    return user.is_active" in result["patch"]
    assert '+    return user.is_active and user.role == "admin"' in result["patch"]
    assert result["recommended_tests"] == [
        "python -m unittest discover -s tests -v"
    ]
    assert result["findings"][0]["path"] == "app.py"
    assert_no_private_response_tokens(body)


@pytest.mark.parametrize(
    ("capability_id", "workspace_name"),
    [
        ("other-review", "sample-workspace"),
        ("backend-rbac-review", "other-workspace"),
    ],
)
def test_mock_runner_sample_patch_is_scoped_to_sample_workspace(
    monkeypatch: pytest.MonkeyPatch,
    capability_id: str,
    workspace_name: str,
) -> None:
    use_capability(
        monkeypatch,
        capability_with(capability_id=capability_id, runner="mock"),
    )
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["name"] = workspace_name
    request_body["workspace"]["files"] = [
        {
            "path": "app.py",
            "content": "\n".join(
                [
                    "from dataclasses import dataclass",
                    "",
                    "",
                    "@dataclass(frozen=True)",
                    "class User:",
                    "    username: str",
                    "    role: str",
                    "    is_active: bool = True",
                    "",
                    "",
                    "def can_view_admin_report(user: User) -> bool:",
                    "    # BUG: this grants every active user access to the admin report.",
                    "    return user.is_active",
                    "",
                ]
            ),
        }
    ]
    request_body["options"]["return_patch"] = True

    response = client.post(
        f"/v1/capabilities/{capability_id}/run",
        json=request_body,
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["patch"] is None
    assert result["findings"] == []
    assert result["recommended_tests"] == ["python -m pytest"]


def test_run_returns_public_error_for_unsupported_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(runner="subprocess"))
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 501
    body = response.json()
    assert_policy_error(body, "unsupported_runner")
    assert_no_private_response_tokens(body)


def test_run_unknown_capability_returns_404_without_private_fields() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/unknown-capability/run",
        json=valid_run_request(),
    )

    assert response.status_code == 404
    body = response.json()
    assert_policy_error(body, "capability_not_found")
    assert_no_private_response_tokens(body)


def test_run_denies_denylisted_workspace_file_with_policy_error_only() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = [
        {
            "path": ".env",
            "content": "not a real secret",
        }
    ]

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "denylisted_file")
    assert ".env" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_denies_workspace_file_outside_manifest_allowlist() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = [
        {
            "path": "notes.txt",
            "content": "plain text is not in the manifest allowlist",
        }
    ]

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "file_not_allowed")
    assert "notes.txt" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_workspace_files_when_no_file_like_input_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(input_modes=["git_diff"]))
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "unsupported_input_mode")
    assert "workspace files" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_git_diff_when_input_mode_is_not_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(input_modes=["current_file"]))
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "unsupported_input_mode")
    assert "git_diff" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_selection_when_input_mode_is_not_declared() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["selection"] = {
        "path": ".env",
        "start_line": 1,
        "end_line": 1,
        "content": "not a real secret",
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "unsupported_input_mode")
    assert "selection" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_denies_denylisted_selection_path_when_mode_is_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(input_modes=["selection"]))
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = None
    request_body["workspace"]["selection"] = {
        "path": ".env",
        "start_line": 1,
        "end_line": 1,
        "content": "not a real secret",
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "denylisted_file")
    assert ".env" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_selection_content_when_input_mode_is_not_declared() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["selection"] = {
        "path": "src/settings.py",
        "start_line": 1,
        "end_line": 1,
        "content": SECRET_LIKE_SELECTION_CONTENT,
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "unsupported_input_mode")
    assert "selection" in body["error"]["message"]
    assert SECRET_LIKE_SELECTION_CONTENT not in json.dumps(body)
    assert_no_private_response_tokens(body)


def test_run_rejects_secret_like_selection_content_when_mode_is_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(input_modes=["selection"]))
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = None
    request_body["workspace"]["selection"] = {
        "path": "src/settings.py",
        "start_line": 1,
        "end_line": 1,
        "content": SECRET_LIKE_SELECTION_CONTENT,
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "secret_like_content")
    assert "src/settings.py" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_oversized_selection_when_input_mode_is_not_declared() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = None
    request_body["workspace"]["selection"] = {
        "path": "src/large.py",
        "content": "x" * 300001,
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "unsupported_input_mode")
    assert "selection" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_counts_selection_content_toward_manifest_total_input_bytes_when_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(input_modes=["selection"]))
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = None
    request_body["workspace"]["selection"] = {
        "path": "src/large.py",
        "content": "x" * 300001,
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "max_total_input_bytes_exceeded")
    assert "limit is 300000" in body["error"]["message"]
    assert_no_private_response_tokens(body)


@pytest.mark.parametrize(
    "selection",
    [
        {
            "path": "app.py",
            "start_line": 1,
            "content": SECRET_LIKE_SELECTION_CONTENT,
        },
        {
            "path": "app.py",
            "end_line": 1,
            "content": SECRET_LIKE_SELECTION_CONTENT,
        },
        {
            "path": "app.py",
            "start_line": 0,
            "end_line": 1,
            "content": SECRET_LIKE_SELECTION_CONTENT,
        },
        {
            "path": "app.py",
            "start_line": 1,
            "end_line": 0,
            "content": SECRET_LIKE_SELECTION_CONTENT,
        },
        {
            "path": "app.py",
            "start_line": 3,
            "end_line": 2,
            "content": SECRET_LIKE_SELECTION_CONTENT,
        },
    ],
)
def test_run_rejects_invalid_selection_ranges(
    selection: dict[str, Any],
) -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["selection"] = selection

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "invalid_selection_range")
    assert SECRET_LIKE_SELECTION_CONTENT not in json.dumps(body)
    assert_no_private_response_tokens(body)


def test_run_counts_git_diff_toward_manifest_total_input_bytes() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = "x" * 300001

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "max_total_input_bytes_exceeded")
    assert "limit is 300000" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_secret_like_git_diff_content() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = "Authorization: Bearer secret-token"

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "secret_like_content")
    assert "workspace.git_diff" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_enforces_manifest_file_count_limit_using_input_policy() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = [
        {
            "path": f"src/file_{index}.py",
            "content": "print('ok')\n",
        }
        for index in range(21)
    ]

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "max_files_exceeded")
    assert "limit is 20" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_enforces_manifest_total_input_bytes_limit_using_input_policy() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = [
        {
            "path": "src/large.py",
            "content": "x" * 300001,
        }
    ]

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "max_total_input_bytes_exceeded")
    assert "limit is 300000" in body["error"]["message"]
    assert_no_private_response_tokens(body)


def test_run_returns_distinct_task_ids_for_separate_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capability(monkeypatch, capability_with(runner="mock"))
    client = TestClient(app)

    first_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )
    second_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["task_id"] != second_response.json()["task_id"]
    assert first_response.json()["task_id"].startswith("task_")
    assert second_response.json()["task_id"].startswith("task_")
    assert_no_private_response_tokens(first_response.json())
    assert_no_private_response_tokens(second_response.json())


def test_run_result_rejects_unvetted_artifact_keys() -> None:
    with pytest.raises(ValidationError):
        CapabilityRunResult(
            summary="Mock summary.",
            artifacts=[
                {
                    "type": "report",
                    "label": "Report",
                    "unexpected": "not public",
                }
            ],
            safe_rationale="Public artifact fields are constrained.",
            confidence=0.82,
        )
