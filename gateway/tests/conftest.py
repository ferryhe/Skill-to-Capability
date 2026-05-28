import sys
from pathlib import Path

import pytest


GATEWAY_ROOT = Path(__file__).resolve().parents[1]

if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))


@pytest.fixture(autouse=True)
def explicit_gateway_dev_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_GATEWAY_AUTH_MODE", "dev")
    monkeypatch.delenv("SKILL_GATEWAY_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_API_TOKENS", raising=False)
    monkeypatch.delenv("SKILL_GATEWAY_API_TOKEN_IDENTITIES", raising=False)
