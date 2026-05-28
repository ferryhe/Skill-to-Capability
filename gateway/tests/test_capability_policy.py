import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway.app.api import capabilities as capabilities_api
from gateway.app.capabilities.manifest import CapabilityManifest
from gateway.app.capabilities.registry import default_registry
from gateway.app.main import app
from gateway.app.runners.mock_runner import MockCapabilityRunner
from gateway.app.tasks.store import task_store


@pytest.fixture(autouse=True)
def auth_config_isolation(
    explicit_gateway_dev_auth: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKILL_GATEWAY_AUTH_MODE", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_API_TOKENS", raising=False)
    monkeypatch.setenv(
        "SKILL_GATEWAY_API_TOKEN_IDENTITIES",
        json.dumps(
            [
                {
                    "token": "tenant-a-viewer-token",
                    "tenant_id": "tenant-a",
                    "role": "viewer",
                },
                {
                    "token": "tenant-a-developer-token",
                    "tenant_id": "tenant-a",
                    "role": "developer",
                },
                {
                    "token": "tenant-b-developer-token",
                    "tenant_id": "tenant-b",
                    "role": "developer",
                },
            ]
        ),
    )
    task_store.clear()


class StubRegistry:
    def __init__(self, manifests: list[CapabilityManifest]) -> None:
        self._manifests = {manifest.id: manifest for manifest in manifests}

    def find(self, capability_id: str) -> CapabilityManifest | None:
        return self._manifests.get(capability_id)

    def list_all(self) -> list[CapabilityManifest]:
        return list(self._manifests.values())

    def list_public(self) -> list[dict[str, Any]]:
        return [manifest.public_view() for manifest in self._manifests.values()]


def auth_headers(
    *,
    token: str = "tenant-a-developer-token",
    tenant_id: str | None = None,
    role: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    if role is not None:
        headers["X-User-Role"] = role
    return headers


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


def backend_rbac_capability() -> CapabilityManifest:
    capability = default_registry().find("backend-rbac-review")
    assert capability is not None
    return capability


def capability_with_policy(
    capability_id: str,
    *,
    tenant_allowlist: list[str] | None = None,
    run_roles: list[str] | None = None,
) -> CapabilityManifest:
    capability = backend_rbac_capability()
    policy: dict[str, Any] = {}
    if tenant_allowlist is not None:
        policy["tenant_allowlist"] = tenant_allowlist
    if run_roles is not None:
        policy["run_roles"] = run_roles

    return capability.model_copy(
        update={
            "id": capability_id,
            "name": capability_id.replace("-", " ").title(),
            "internal": capability.internal.model_copy(
                update={
                    "runner": "mock",
                    "policy": policy,
                }
            ),
        }
    )


def use_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    manifests: list[CapabilityManifest],
) -> None:
    monkeypatch.setattr(
        capabilities_api,
        "default_registry",
        lambda: StubRegistry(manifests),
    )
    monkeypatch.setattr(
        capabilities_api,
        "_runner_for_capability",
        lambda _runner_name: MockCapabilityRunner(),
    )


def assert_error_shape(body: dict[str, Any], expected_code: str) -> dict[str, Any]:
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    return error


def test_list_capabilities_filters_by_tenant_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [
            capability_with_policy("tenant-a-capability", tenant_allowlist=["tenant-a"]),
            capability_with_policy("tenant-b-capability", tenant_allowlist=["tenant-b"]),
            capability_with_policy("shared-capability"),
        ],
    )
    client = TestClient(app)

    response = client.get("/v1/capabilities", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert [capability["id"] for capability in body["capabilities"]] == [
        "tenant-a-capability",
        "shared-capability",
    ]
    serialized = json.dumps(body)
    assert "tenant-b-capability" not in serialized
    assert "internal" not in serialized
    assert "tenant_allowlist" not in serialized
    assert "run_roles" not in serialized


def test_list_capabilities_hides_developer_only_capability_from_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [
            capability_with_policy(
                "developer-only-capability",
                tenant_allowlist=["tenant-a"],
                run_roles=["developer"],
            ),
            capability_with_policy(
                "readonly-capability",
                tenant_allowlist=["tenant-a"],
                run_roles=["viewer", "developer"],
            ),
        ],
    )
    client = TestClient(app)

    response = client.get(
        "/v1/capabilities",
        headers=auth_headers(token="tenant-a-viewer-token"),
    )

    assert response.status_code == 200
    body = response.json()
    assert [capability["id"] for capability in body["capabilities"]] == [
        "readonly-capability"
    ]
    assert "developer-only-capability" not in json.dumps(body)


def test_get_capability_returns_404_when_tenant_cannot_see_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [capability_with_policy("tenant-b-capability", tenant_allowlist=["tenant-b"])],
    )
    client = TestClient(app)

    response = client.get(
        "/v1/capabilities/tenant-b-capability",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert_error_shape(response.json(), "capability_not_found")
    assert "tenant-b" not in json.dumps(response.json())


def test_viewer_can_run_readonly_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [
            capability_with_policy(
                "readonly-capability",
                tenant_allowlist=["tenant-a"],
                run_roles=["viewer", "developer"],
            )
        ],
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/readonly-capability/run",
        json=valid_run_request(),
        headers=auth_headers(token="tenant-a-viewer-token"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_viewer_cannot_run_patch_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [
            capability_with_policy(
                "patch-capability",
                tenant_allowlist=["tenant-a"],
                run_roles=["developer"],
            )
        ],
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/patch-capability/run",
        json=valid_run_request(),
        headers=auth_headers(token="tenant-a-viewer-token"),
    )

    assert response.status_code == 404
    body = response.json()
    assert_error_shape(body, "capability_not_found")
    assert "tenant-a-viewer-token" not in json.dumps(body)
    assert "developer" not in json.dumps(body)


def test_developer_can_run_patch_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [
            capability_with_policy(
                "patch-capability",
                tenant_allowlist=["tenant-a"],
                run_roles=["developer"],
            )
        ],
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/patch-capability/run",
        json=valid_run_request(),
        headers=auth_headers(token="tenant-a-developer-token"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_real_backend_rbac_review_hidden_from_viewer() -> None:
    client = TestClient(app)

    list_response = client.get(
        "/v1/capabilities",
        headers=auth_headers(token="tenant-a-viewer-token"),
    )
    get_response = client.get(
        "/v1/capabilities/backend-rbac-review",
        headers=auth_headers(token="tenant-a-viewer-token"),
    )
    run_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=valid_run_request(),
        headers=auth_headers(token="tenant-a-viewer-token"),
    )

    assert list_response.status_code == 200
    assert "backend-rbac-review" not in json.dumps(list_response.json())
    assert get_response.status_code == 404
    assert_error_shape(get_response.json(), "capability_not_found")
    assert run_response.status_code == 404
    assert_error_shape(run_response.json(), "capability_not_found")


def test_real_backend_rbac_review_run_allowed_for_developer() -> None:
    client = TestClient(app)
    request_body = valid_run_request()
    request_body["options"]["async"] = True

    get_response = client.get(
        "/v1/capabilities/backend-rbac-review",
        headers=auth_headers(token="tenant-a-developer-token"),
    )
    run_response = client.post(
        "/v1/capabilities/backend-rbac-review/run",
        json=request_body,
        headers=auth_headers(token="tenant-a-developer-token"),
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == "backend-rbac-review"
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "queued"


def test_token_bound_tenant_cannot_be_overridden_by_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [capability_with_policy("tenant-b-capability", tenant_allowlist=["tenant-b"])],
    )
    client = TestClient(app)

    response = client.get(
        "/v1/capabilities/tenant-b-capability",
        headers=auth_headers(
            token="tenant-a-developer-token",
            tenant_id="tenant-b",
        ),
    )

    assert response.status_code == 404
    assert_error_shape(response.json(), "capability_not_found")


def test_token_bound_viewer_role_cannot_be_overridden_by_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_capabilities(
        monkeypatch,
        [
            capability_with_policy(
                "patch-capability",
                tenant_allowlist=["tenant-a"],
                run_roles=["developer"],
            )
        ],
    )
    client = TestClient(app)

    response = client.post(
        "/v1/capabilities/patch-capability/run",
        json=valid_run_request(),
        headers=auth_headers(
            token="tenant-a-viewer-token",
            role="developer",
        ),
    )

    assert response.status_code == 404
    assert_error_shape(response.json(), "capability_not_found")
