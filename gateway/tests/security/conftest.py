import pytest
from fastapi.testclient import TestClient

from gateway.app.audit.store import audit_store
from gateway.app.main import app
from gateway.app.tasks.store import task_store


@pytest.fixture(autouse=True)
def clear_security_state() -> None:
    task_store.clear()
    audit_store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
