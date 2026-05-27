from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PermissionMode = bool | Literal["never", "optional", "required"]


class ClientPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reads_workspace: bool
    writes_workspace: PermissionMode
    runs_commands: PermissionMode
    sends_code_to_server: bool


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    upload_context: Literal["auto", "user_confirm", "user_confirm_large"] | None = None
    apply_patch: Literal["never", "auto", "user_confirm"] | None = None
    run_commands: Literal["never", "auto", "user_confirm"] | None = None


class SecurityPolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_files: int | None = Field(default=None, ge=1)
    max_total_input_bytes: int | None = Field(default=None, ge=1)
    deny_file_globs: list[str] | None = None
    allow_file_globs: list[str] | None = None


class InternalManifest(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    skill_ref: str
    runner: Literal["mock", "hermes", "subprocess", "container"]
    expose_skill_text: Literal[False]
    model_policy: str | None = None
    required_env: list[str] | None = None
    required_commands: list[str] | None = None


class CapabilityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,80}$")
    name: str = Field(min_length=1)
    version: str
    category: str | None = None
    visible_description: str = Field(min_length=1)
    input_modes: list[
        Literal[
            "current_file",
            "selected_files",
            "git_diff",
            "workspace_snapshot",
            "selection",
            "manual_input",
        ]
    ] = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    client_permissions: ClientPermissions
    approval_policy: ApprovalPolicy
    security: SecurityPolicy | None = None
    internal: InternalManifest

    @field_validator("input_modes")
    @classmethod
    def input_modes_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("input_modes must be unique")
        return value

    def public_view(self) -> dict[str, Any]:
        public_fields = (
            "id",
            "name",
            "version",
            "category",
            "visible_description",
            "input_modes",
            "input_schema",
            "output_schema",
            "client_permissions",
            "approval_policy",
            "security",
        )
        return self.model_dump(include=set(public_fields), exclude_none=True)
