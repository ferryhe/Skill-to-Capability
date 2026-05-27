import json
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import default_registry
from gateway.app.main import app


SECRET_SUBMITTED_CONTENT = "OPENAI_API_KEY=sk-proj-submittedbody123456"


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
        "client": {"type": "test", "version": "0.1.0"},
    }


def assert_error_shape(body: dict[str, Any], expected_code: str) -> dict[str, Any]:
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    return error


def assert_not_serialized(body: Any, *needles: str) -> None:
    serialized = json.dumps(body)
    for needle in needles:
        assert needle not in serialized


def test_unknown_capability_uses_unified_error_shape() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/unknown-capability/run",
        json=valid_run_request(),
    )

    assert response.status_code == 404
    assert_error_shape(response.json(), "capability_not_found")


def test_input_policy_error_uses_unified_error_shape_and_redacts_content() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["workspace"]["files"] = []
    request_body["workspace"]["git_diff"] = (
        "Authorization: Bearer raw-submitted-token"
    )

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 400
    assert_error_shape(response.json(), "secret_like_content")
    assert_not_serialized(response.json(), "raw-submitted-token")


def test_unsupported_runner_error_uses_unified_error_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = backend_rbac_capability()
    unsupported = capability.model_copy(
        update={
            "internal": capability.internal.model_copy(update={"runner": "hermes"}),
        }
    )
    monkeypatch.setattr(
        capabilities_api,
        "default_registry",
        lambda: StubRegistry(unsupported),
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 501
    assert_error_shape(response.json(), "unsupported_runner")


def test_http_exception_handler_redacts_messages_and_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_secret_error(_runner_name: str) -> None:
        raise HTTPException(
            status_code=418,
            detail={
                "code": "runner_failed",
                "message": (
                    "Authorization: Bearer raw-http-token at "
                    r"C:\Users\ferry\.codex\skills\secret\SKILL.md"
                ),
                "details": {
                    "api_key": "sk-proj-httpsecret123456",
                    "path": "/var/run/secrets/kubernetes.io/serviceaccount/token",
                },
            },
        )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        raise_secret_error,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 418
    body = response.json()
    assert_error_shape(body, "runner_failed")
    assert_not_serialized(
        body,
        "raw-http-token",
        r"C:\Users\ferry",
        "sk-proj-httpsecret123456",
        "/var/run/secrets",
    )
    assert "[REDACTED" in json.dumps(body)


def test_http_exception_handler_redacts_sensitive_detail_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows_path_key = r"C:\Users\ferry\.codex\skills\secret\SKILL.md"
    api_key_key = "sk-proj-detailkeyleak123456"

    def raise_secret_key_error(_runner_name: str) -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "runner_failed",
                "message": "Safe public message.",
                "details": {
                    windows_path_key: "public path-key value",
                    api_key_key: "public api-key value",
                },
            },
        )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        raise_secret_key_error,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 400
    body = response.json()
    error = assert_error_shape(body, "runner_failed")
    assert_not_serialized(
        body,
        windows_path_key,
        r"C:\Users\ferry",
        api_key_key,
        "sk-proj-detailkeyleak123456",
    )
    assert error["details"]["[REDACTED_PATH]"] == "[REDACTED_SECRET]"
    assert error["details"]["[REDACTED_API_KEY]"] == "public api-key value"


def test_http_exception_handler_normalizes_unsafe_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe_code = r"runner_sk-proj-codeleak123456_C:\Users\ferry\secret"

    def raise_unsafe_code_error(_runner_name: str) -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": unsafe_code,
                "message": "Safe public message.",
                "details": {},
            },
        )

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        raise_unsafe_code_error,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 400
    body = response.json()
    error = assert_error_shape(body, "http_error")
    assert error["message"] == "Safe public message."
    assert_not_serialized(
        body,
        unsafe_code,
        "sk-proj-codeleak123456",
        r"C:\Users\ferry",
    )


def test_request_validation_error_does_not_echo_submitted_body_content() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["unexpected"] = {
        "token": "Authorization: Bearer raw-validation-token",
        "content": SECRET_SUBMITTED_CONTENT,
    }

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
    )

    assert response.status_code == 422
    body = response.json()
    error = assert_error_shape(body, "request_validation_error")
    assert "errors" in error["details"]
    assert_not_serialized(
        body,
        "raw-validation-token",
        SECRET_SUBMITTED_CONTENT,
        "unexpected",
    )


def test_unexpected_exception_uses_generic_redacted_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_message = (
        "Authorization: Bearer raw-runtime-token at "
        r"C:\Users\ferry\.codex\skills\secret\SKILL.md"
    )

    def raise_unexpected_error(_runner_name: str) -> None:
        raise RuntimeError(raw_message)

    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        raise_unexpected_error,
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
    )

    assert response.status_code == 500
    body = response.json()
    error = assert_error_shape(body, "internal_server_error")
    assert error["message"] == "Internal server error."
    assert error["details"] == {}
    assert_not_serialized(
        body,
        "raw-runtime-token",
        r"C:\Users\ferry",
        "RuntimeError",
        "Traceback",
        raw_message,
    )
