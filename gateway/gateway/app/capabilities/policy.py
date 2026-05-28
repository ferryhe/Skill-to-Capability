from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gateway.app.auth.models import RequestIdentity

if TYPE_CHECKING:
    from gateway.app.capabilities.manifest import CapabilityManifest


CapabilityRole = Literal["viewer", "developer"]


class CapabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_allowlist: list[str] | None = Field(default=None, min_length=1)
    view_roles: list[CapabilityRole] | None = Field(default=None, min_length=1)
    run_roles: list[CapabilityRole] | None = Field(default=None, min_length=1)

    @field_validator("tenant_allowlist", "view_roles", "run_roles")
    @classmethod
    def values_must_be_unique(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("policy values must be unique")
        return value


def is_capability_visible(
    capability: "CapabilityManifest",
    identity: RequestIdentity,
) -> bool:
    policy = _policy_for(capability)
    if policy is None:
        return True

    if policy.tenant_allowlist is not None:
        if identity.tenant_id not in policy.tenant_allowlist:
            return False

    visible_roles = policy.view_roles
    if visible_roles is None:
        visible_roles = policy.run_roles
    if visible_roles is not None and identity.role not in visible_roles:
        return False

    return True


def can_run_capability(
    capability: "CapabilityManifest",
    identity: RequestIdentity,
) -> bool:
    if not is_capability_visible(capability, identity):
        return False

    policy = _policy_for(capability)
    if policy is None or policy.run_roles is None:
        return True

    return identity.role in policy.run_roles


def _policy_for(capability: "CapabilityManifest") -> CapabilityPolicy | None:
    policy = capability.internal.policy
    if policy is None or isinstance(policy, CapabilityPolicy):
        return policy
    return CapabilityPolicy.model_validate(policy)
