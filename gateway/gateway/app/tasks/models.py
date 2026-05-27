from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    sha256: str | None = None


class WorkspaceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    start_line: int | None = None
    end_line: int | None = None
    content: str


class WorkspaceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    root_uri: str | None = None
    git_branch: str | None = None
    git_diff: str | None = None
    files: list[WorkspaceFile] = Field(default_factory=list)
    selection: WorkspaceSelection | None = None


class RunClient(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["vscode", "mcp", "cli", "web", "test"] | None = None
    version: str | None = None


class CapabilityRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace: WorkspaceContext | None = None
    instruction: str = Field(min_length=1, max_length=4000)
    options: dict[str, Any] | None = None
    client: RunClient | None = None


class RunFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    severity: Literal["info", "low", "medium", "high", "critical"] | None = None
    path: str | None = None
    line: int | None = Field(default=None, ge=1)
    title: str | None = None
    message: str | None = None


class RunArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    label: str | None = None
    path: str | None = None
    uri: str | None = None
    content_type: str | None = None


class CapabilityRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    findings: list[RunFinding] = Field(default_factory=list)
    patch: str | None = None
    recommended_tests: list[str] = Field(default_factory=list)
    artifacts: list[RunArtifact] = Field(default_factory=list)
    safe_rationale: str
    confidence: float = Field(ge=0, le=1)


class CapabilityTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: Literal["completed"]
    result: CapabilityRunResult


TaskStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class CapabilityTaskQueued(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: Literal["queued"]


class CapabilityTaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: TaskStatus
    capability_id: str
    created_at: datetime
    updated_at: datetime


class TaskError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
