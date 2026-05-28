import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from gateway.app.api import capabilities as capabilities_api
from gateway.app.auth.dependencies import require_request_identity
from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import default_registry
from gateway.app.main import app
from gateway.app.runners.mock_runner import MockCapabilityRunner
from gateway.app.tasks.store import task_store


pytestmark = pytest.mark.usefixtures("auth_config_isolation")


@pytest.fixture
def auth_config_isolation(
    explicit_gateway_dev_auth: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKILL_GATEWAY_AUTH_MODE", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_API_TOKENS", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_API_TOKEN_IDENTITIES", raising=False)


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
        "options": {"async": True},
        "client": {"type": "test", "version": "0.1.0"},
    }


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def token_identities_json() -> str:
    return json.dumps(
        [
            {
                "token": "tenant-viewer-token",
                "tenant_id": "tenant-alpha",
                "role": "viewer",
            },
            {
                "token": "tenant-developer-token",
                "tenant_id": "tenant-beta",
                "role": "developer",
            },
        ]
    )


def set_legacy_and_identity_config(
    monkeypatch: pytest.MonkeyPatch,
    identity_config: str,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKEN_IDENTITIES", identity_config)
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "legacy-token")


def request_with_headers(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/capabilities",
            "headers": [
                (name.lower().encode("ascii"), value.encode("ascii"))
                for name, value in headers.items()
            ],
        }
    )


def assert_auth_error(response: Any, expected_code: str = "auth_required") -> None:
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == expected_code
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)


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


def use_mock_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: MockCapabilityRunner(),
    )


def test_health_is_public_without_token() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/capabilities"),
        ("get", "/v1/capabilities/backend-rbac-review"),
        ("post", "/v1/capabilities/backend-rbac-review/run"),
        ("get", "/v1/tasks/task_missing"),
        ("get", "/v1/tasks/task_missing/result"),
        ("post", "/v1/tasks/task_missing/cancel"),
    ],
)
def test_protected_endpoints_reject_missing_token_by_default(
    method: str,
    path: str,
) -> None:
    client = TestClient(app)

    if path.endswith("/run"):
        response = client.post(path, json=valid_run_request())
    else:
        response = getattr(client, method)(path)

    assert_auth_error(response)


def test_invalid_token_is_rejected_without_echoing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "valid-token")
    raw_token = "raw-invalid-token"
    client = TestClient(app)

    response = client.get("/v1/capabilities", headers=auth_header(raw_token))

    assert_auth_error(response, "invalid_token")
    serialized = json.dumps(response.json()) + json.dumps(dict(response.headers))
    assert raw_token not in serialized
    assert "valid-token" not in serialized


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic x",
        "Bearer",
    ],
)
def test_malformed_auth_header_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    authorization: str,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "valid-token")
    client = TestClient(app)

    response = client.get(
        "/v1/capabilities",
        headers={"Authorization": authorization},
    )

    assert_auth_error(response)


def test_bearer_token_without_token_config_fails_closed() -> None:
    client = TestClient(app)

    response = client.get("/v1/capabilities", headers=auth_header("unused-token"))

    assert_auth_error(response)


def test_valid_bearer_token_allows_protected_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "alpha-token, beta-token")
    client = TestClient(app)

    response = client.get("/v1/capabilities", headers=auth_header("beta-token"))

    assert response.status_code == 200
    assert response.json()["capabilities"][0]["id"] == "backend-rbac-review"


def test_valid_token_identity_allows_protected_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKEN_IDENTITIES", token_identities_json())
    client = TestClient(app)

    response = client.get(
        "/v1/capabilities",
        headers=auth_header("tenant-viewer-token"),
    )

    assert response.status_code == 200
    assert isinstance(response.json()["capabilities"], list)


def test_auth_disabled_yes_does_not_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_AUTH_DISABLED", "yes")
    client = TestClient(app)

    response = client.get("/v1/capabilities")

    assert_auth_error(response)


def test_explicit_dev_bypass_allows_protected_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_AUTH_MODE", "dev")
    client = TestClient(app)

    response = client.get("/v1/capabilities")

    assert response.status_code == 200
    assert response.json()["capabilities"][0]["id"] == "backend-rbac-review"


def test_auth_disabled_flag_must_be_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_AUTH_DISABLED", " TrUe ")
    client = TestClient(app)

    response = client.get("/v1/capabilities")

    assert response.status_code == 200


def test_tenant_header_is_accepted_with_valid_token_without_leaking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "tenant-token")
    tenant_id = "tenant-alpha"
    client = TestClient(app)

    response = client.get(
        "/v1/capabilities",
        headers={**auth_header("tenant-token"), "X-Tenant-Id": tenant_id},
    )

    assert response.status_code == 200
    assert tenant_id not in json.dumps(response.json())


def test_token_mode_uses_server_bound_identity_not_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKEN_IDENTITIES", token_identities_json())
    request = request_with_headers(
        {
            **auth_header("tenant-viewer-token"),
            "X-Tenant-Id": "tenant-beta",
            "X-User-Role": "developer",
        }
    )

    identity = require_request_identity(request)

    assert identity.auth_mode == "token"
    assert identity.tenant_id == "tenant-alpha"
    assert identity.role == "viewer"
    assert identity.token_id is not None
    assert "tenant-viewer-token" not in identity.token_id
    assert request.state.identity == identity


def test_legacy_token_identity_defaults_ignore_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "legacy-token")
    request = request_with_headers(
        {
            **auth_header("legacy-token"),
            "X-Tenant-Id": "tenant-alpha",
            "X-User-Role": "viewer",
        }
    )

    identity = require_request_identity(request)

    assert identity.auth_mode == "token"
    assert identity.tenant_id == "default"
    assert identity.role == "developer"


@pytest.mark.parametrize(
    "identity_config",
    [
        "{not-json",
        json.dumps({"token": "not-a-list"}),
        json.dumps([{"token": "configured-token", "tenant_id": "tenant-a"}]),
        json.dumps(
            [{"token": "configured-token", "tenant_id": "tenant-a", "role": "admin"}]
        ),
        json.dumps(
            [
                {
                    "token": "duplicate-token",
                    "tenant_id": "tenant-a",
                    "role": "viewer",
                },
                {
                    "token": "duplicate-token",
                    "tenant_id": "tenant-b",
                    "role": "developer",
                },
            ]
        ),
    ],
)
def test_invalid_token_identity_config_fails_closed_without_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
    identity_config: str,
) -> None:
    set_legacy_and_identity_config(monkeypatch, identity_config)
    client = TestClient(app)

    response = client.get("/v1/capabilities", headers=auth_header("legacy-token"))

    assert_auth_error(response)


def test_dev_bypass_uses_headers_for_local_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_AUTH_MODE", "dev")
    request = request_with_headers(
        {
            "X-Tenant-Id": "tenant-alpha",
            "X-User-Role": "viewer",
        }
    )

    identity = require_request_identity(request)

    assert identity.auth_mode == "dev"
    assert identity.tenant_id == "tenant-alpha"
    assert identity.role == "viewer"


def test_task_endpoints_are_protected_with_valid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_API_TOKENS", "task-token")
    use_mock_runner(monkeypatch)
    client = TestClient(app)
    headers = auth_header("task-token")

    run_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
        headers=headers,
    )

    assert run_response.status_code == 200
    task_id = run_response.json()["task_id"]
    assert client.get(f"/v1/tasks/{task_id}", headers=headers).status_code == 200
    assert client.post(f"/v1/tasks/{task_id}/cancel", headers=headers).status_code == 200
    assert client.get(f"/v1/tasks/{task_id}/result", headers=headers).status_code == 409
