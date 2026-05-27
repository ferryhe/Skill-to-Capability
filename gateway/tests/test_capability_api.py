from fastapi.testclient import TestClient

from gateway.app.main import app


def test_list_capabilities_returns_public_views_only() -> None:
    client = TestClient(app)

    response = client.get("/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert [capability["id"] for capability in body["capabilities"]] == [
        "backend-rbac-review"
    ]
    assert "internal" not in str(body)
    assert "skill_ref" not in str(body)
    assert "model_policy" not in str(body)


def test_get_capability_returns_public_detail_only() -> None:
    client = TestClient(app)

    response = client.get("/v1/capabilities/backend-rbac-review")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "backend-rbac-review"
    assert body["input_schema"]["required"] == ["instruction"]
    assert "internal" not in str(body)
    assert "skill_ref" not in str(body)
    assert "model_policy" not in str(body)


def test_get_unknown_capability_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/v1/capabilities/unknown-capability")

    assert response.status_code == 404
