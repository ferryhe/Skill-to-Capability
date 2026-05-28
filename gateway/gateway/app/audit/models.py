from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway.app.auth.models import RequestIdentity


AuditEventType = Literal["task_lifecycle", "approval"]


class AuditActor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_mode: str
    tenant_id: str
    role: str
    token_id: str | None = None

    @classmethod
    def from_identity(cls, identity: RequestIdentity) -> "AuditActor":
        return cls(
            auth_mode=identity.auth_mode,
            tenant_id=identity.tenant_id,
            role=identity.role,
            token_id=identity.token_id,
        )


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: AuditEventType
    action: str
    created_at: datetime
    capability_id: str | None = None
    task_id: str | None = None
    actor: AuditActor | None = None
    input_metadata: dict[str, Any] | None = None
    output_metadata: dict[str, Any] | None = None
    approval_metadata: dict[str, Any] | None = None
