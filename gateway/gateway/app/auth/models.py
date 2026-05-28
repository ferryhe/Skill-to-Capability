from pydantic import BaseModel, ConfigDict


class RequestIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_mode: str
    tenant_id: str
    token_id: str | None = None
