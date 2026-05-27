import json
from typing import Any

from fastapi.testclient import TestClient

from gateway.app.main import app


PRIVATE_RESPONSE_TOKENS = (
    "prompt",
    "trace",
    "skill_text",
    "internal",
    "skill_ref",
    "model_policy",
)


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
    detail = response_body["detail"]
    assert detail["code"] == expected_code
    assert isinstance(detail["message"], str)


def test_run_capability_returns_completed_mock_result_public_fields_only() -> None:
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


def test_run_unknown_capability_returns_404_without_private_fields() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/unknown-capability/run",
        json=valid_run_request(),
    )

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Capability not found"
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
    assert ".env" in body["detail"]["message"]
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
    assert "notes.txt" in body["detail"]["message"]
    assert_no_private_response_tokens(body)


def test_run_denies_denylisted_selection_path_with_policy_error_only() -> None:
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
    assert_policy_error(body, "denylisted_file")
    assert ".env" in body["detail"]["message"]
    assert_no_private_response_tokens(body)


def test_run_rejects_secret_like_selection_content() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["selection"] = {
        "path": "src/settings.py",
        "start_line": 1,
        "end_line": 1,
        "content": 'OPENAI_API_KEY = "sk-proj-secretvalue"',
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    body = response.json()
    assert_policy_error(body, "secret_like_content")
    assert "src/settings.py" in body["detail"]["message"]
    assert_no_private_response_tokens(body)


def test_run_counts_selection_content_toward_manifest_total_input_bytes() -> None:
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
    assert "limit is 300000" in body["detail"]["message"]
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
    assert "limit is 300000" in body["detail"]["message"]
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
    assert "workspace.git_diff" in body["detail"]["message"]
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
    assert "limit is 20" in body["detail"]["message"]
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
    assert "limit is 300000" in body["detail"]["message"]
    assert_no_private_response_tokens(body)


def test_run_returns_distinct_task_ids_for_separate_runs() -> None:
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
