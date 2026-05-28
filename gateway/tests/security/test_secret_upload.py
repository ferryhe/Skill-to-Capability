import json
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.audit.store import audit_store

from helpers import (
    API_KEY_MARKER,
    BEARER_TOKEN_MARKER,
    PASSWORD_MARKER,
    RAW_AUTH_HEADER,
    RAW_BEARER_TOKEN,
    RAW_PASSWORD_JSON,
    RAW_SECRET_ASSIGNMENT,
    assert_error_response,
    assert_not_serialized,
    backend_rbac_capability,
    public_result,
    use_capability,
    valid_run_request,
)


def test_secret_like_workspace_file_is_rejected_before_runner_or_audit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_runner_is_resolved(_runner_name: str) -> None:
        raise AssertionError("runner should not be resolved for rejected uploads")

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        fail_if_runner_is_resolved,
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(
            files=[{"path": "src/settings.py", "content": RAW_SECRET_ASSIGNMENT}],
            git_diff=None,
        ),
    )

    assert response.status_code == 400
    body = response.json()
    assert_error_response(body, "secret_like_content")
    assert audit_store.list_all() == []
    assert_not_serialized(body, RAW_SECRET_ASSIGNMENT, API_KEY_MARKER)


def test_secret_like_git_diff_is_rejected_without_echoing_content(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(files=[], git_diff=RAW_AUTH_HEADER),
    )

    assert response.status_code == 400
    body = response.json()
    assert_error_response(body, "secret_like_content")
    assert audit_store.list_all() == []
    assert_not_serialized(body, RAW_AUTH_HEADER, RAW_BEARER_TOKEN, BEARER_TOKEN_MARKER)


def test_secret_like_selection_is_rejected_when_selection_mode_is_allowed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = backend_rbac_capability().model_copy(
        update={"input_modes": ["selection"]},
    )
    use_capability(monkeypatch, capability)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(
            files=[],
            git_diff=None,
            selection={
                "path": "src/settings.py",
                "start_line": 1,
                "end_line": 1,
                "content": RAW_PASSWORD_JSON,
            },
        ),
    )

    assert response.status_code == 400
    body = response.json()
    assert_error_response(body, "secret_like_content")
    assert audit_store.list_all() == []
    assert_not_serialized(body, RAW_PASSWORD_JSON, PASSWORD_MARKER)


def test_runner_secrets_are_redacted_from_response_and_audit_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SecretEchoRunner:
        def run(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return public_result(
                summary=f"Runner said {RAW_AUTH_HEADER}",
                safe_rationale=f"{RAW_SECRET_ASSIGNMENT}\n{RAW_PASSWORD_JSON}",
            )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: SecretEchoRunner(),
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 200
    body = response.json()
    task_id = body["task_id"]
    assert "[REDACTED" in json.dumps(body)
    assert_not_serialized(
        body,
        RAW_BEARER_TOKEN,
        BEARER_TOKEN_MARKER,
        RAW_SECRET_ASSIGNMENT,
        API_KEY_MARKER,
        PASSWORD_MARKER,
    )
    assert_not_serialized(
        audit_store.list_for_task(task_id),
        RAW_BEARER_TOKEN,
        BEARER_TOKEN_MARKER,
        RAW_SECRET_ASSIGNMENT,
        API_KEY_MARKER,
        PASSWORD_MARKER,
    )


def test_error_responses_redact_secret_details_headers_and_paths(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = r"C:\Users\ferry\.codex\skills\secret\SKILL.md"

    def raise_secret_error(_runner_name: str) -> None:
        raise HTTPException(
            status_code=418,
            detail={
                "code": "runner_failed",
                "message": f"{RAW_AUTH_HEADER} from {raw_path}",
                "details": {
                    "api_key": API_KEY_MARKER,
                    "token": RAW_BEARER_TOKEN,
                    "path": raw_path,
                },
            },
            headers={
                "WWW-Authenticate": f"Bearer {RAW_BEARER_TOKEN} path={raw_path}",
                "X-Debug-Path": raw_path,
            },
        )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        raise_secret_error,
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 418
    body = response.json()
    assert_error_response(body, "runner_failed")
    assert "x-debug-path" not in response.headers
    assert "[REDACTED" in json.dumps(body)
    assert "[REDACTED" in response.headers["www-authenticate"]
    assert_not_serialized(
        [body, dict(response.headers)],
        RAW_AUTH_HEADER,
        RAW_BEARER_TOKEN,
        BEARER_TOKEN_MARKER,
        API_KEY_MARKER,
        raw_path,
        r"C:\Users\ferry",
    )
