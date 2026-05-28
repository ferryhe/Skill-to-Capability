from copy import deepcopy
from datetime import UTC, datetime
import re
from threading import RLock
from typing import Any
from uuid import uuid4

from gateway.app.auth.models import RequestIdentity

from .models import AuditActor, AuditEvent


INPUT_METADATA_KEYS = {
    "execution_mode",
    "instruction_length",
    "workspace_file_count",
    "workspace_file_bytes",
    "has_git_diff",
    "git_diff_bytes",
    "has_selection",
    "selection_bytes",
    "option_count",
    "client_type",
}
SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAFE_CAPABILITY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")
SAFE_TASK_ID_PATTERN = re.compile(r"^task_[a-z0-9_]{1,80}$")
SAFE_TOKEN_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{12,64}$")
SAFE_TENANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SENSITIVE_STRING_PATTERNS = (
    re.compile(r"sk-(?:proj-)?[a-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"ghp_[a-z0-9_]{12,}", re.IGNORECASE),
    re.compile(r"github_pat_[a-z0-9_]{12,}", re.IGNORECASE),
    re.compile(r"glpat-[a-z0-9_-]{12,}", re.IGNORECASE),
    re.compile(r"xox[abprs]-[a-z0-9-]{10,}", re.IGNORECASE),
    re.compile(r"\bauthorization\s*:\s*bearer\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+[a-z0-9._~+/-]{12,}={0,2}", re.IGNORECASE),
    re.compile(r"\b[a-z0-9_-]{10,}\.[a-z0-9_-]{10,}\.[a-z0-9_-]{10,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
SENSITIVE_DIRECT_VALUES = {
    "full prompt",
    "internal system prompt",
    "prompt",
    "raw error",
    "raw runner output",
    "raw_runner_output",
    "skill body",
    "skill text",
    "skill_text",
}
APPROVAL_TYPES = {
    "apply_patch",
    "run_command",
    "upload_context",
    "recommended_tests",
}
APPROVAL_DECISIONS = {"approved", "rejected", "cancelled"}
APPROVAL_ACTIONS = APPROVAL_DECISIONS
AUTH_MODES = {"dev", "token"}
EXECUTION_MODES = {"sync", "async"}
CLIENT_TYPES = {"vscode", "mcp", "cli", "web", "test"}
TASK_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}
TASK_LIFECYCLE_ACTIONS = TASK_STATUSES
USER_ROLES = {"viewer", "developer"}
UNKNOWN_ACTION = "unknown"
PUBLIC_RESULT_KEYS = {
    "summary",
    "findings",
    "patch",
    "recommended_tests",
    "artifacts",
    "safe_rationale",
    "confidence",
}
NUMERIC_METADATA_KEYS = {
    "instruction_length",
    "workspace_file_count",
    "workspace_file_bytes",
    "git_diff_bytes",
    "selection_bytes",
    "option_count",
    "finding_count",
    "artifact_count",
    "recommended_test_count",
    "result_size_bytes",
}
BOOLEAN_METADATA_KEYS = {
    "has_git_diff",
    "has_selection",
    "patch_present",
}
_DROP = object()


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def record_task_lifecycle(
        self,
        *,
        action: str,
        capability_id: str,
        task_id: str,
        actor: RequestIdentity | AuditActor | None = None,
        input_metadata: dict[str, Any] | None = None,
        output_metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"audit_{uuid4().hex}",
            event_type="task_lifecycle",
            action=_normalize_action(action, TASK_LIFECYCLE_ACTIONS),
            created_at=_utc_now(),
            capability_id=_normalize_capability_id(capability_id),
            task_id=_normalize_task_id(task_id),
            actor=_audit_actor(actor),
            input_metadata=_allow_task_input_metadata(input_metadata),
            output_metadata=_allow_task_output_metadata(output_metadata),
        )
        return self._append(event)

    def record_approval_event(
        self,
        *,
        action: str,
        capability_id: str | None,
        task_id: str | None,
        actor: RequestIdentity | AuditActor | None,
        approval_metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"audit_{uuid4().hex}",
            event_type="approval",
            action=_normalize_action(action, APPROVAL_ACTIONS),
            created_at=_utc_now(),
            capability_id=_normalize_capability_id(capability_id),
            task_id=_normalize_task_id(task_id),
            actor=_audit_actor(actor),
            approval_metadata=_allow_approval_metadata(approval_metadata),
        )
        return self._append(event)

    def list_for_task(self, task_id: str) -> list[AuditEvent]:
        normalized_task_id = _normalize_task_id(task_id)
        if normalized_task_id is None:
            return []
        with self._lock:
            return [deepcopy(event) for event in self._events if event.task_id == normalized_task_id]

    def list_all(self) -> list[AuditEvent]:
        with self._lock:
            return deepcopy(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def _append(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._events.append(event)
        return deepcopy(event)


def _audit_actor(actor: RequestIdentity | AuditActor | None) -> AuditActor | None:
    if actor is None:
        return None

    raw_actor = actor if isinstance(actor, AuditActor) else AuditActor.from_identity(actor)
    auth_mode = _normalize_enum(raw_actor.auth_mode, AUTH_MODES)
    tenant_id = _normalize_tenant_id(raw_actor.tenant_id)
    role = _normalize_enum(raw_actor.role, USER_ROLES)
    if auth_mode is _DROP or tenant_id is _DROP or role is _DROP:
        return None

    token_id = raw_actor.token_id
    if (
        not isinstance(token_id, str)
        or _looks_sensitive_string(token_id)
        or not SAFE_TOKEN_ID_PATTERN.fullmatch(token_id)
    ):
        token_id = None

    return AuditActor(
        auth_mode=auth_mode,
        tenant_id=tenant_id,
        role=role,
        token_id=token_id,
    )


def _allow_task_input_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None

    allowed: dict[str, Any] = {}
    for key in INPUT_METADATA_KEYS:
        value = metadata.get(key)
        normalized = _normalize_metadata_value(key, value)
        if normalized is not _DROP:
            allowed[key] = normalized
    return allowed or None


def _allow_task_output_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None

    allowed: dict[str, Any] = {}
    for key in (
        "status",
        "result_keys",
        "finding_count",
        "artifact_count",
        "recommended_test_count",
        "patch_present",
        "result_size_bytes",
        "error_code",
    ):
        value = metadata.get(key)
        normalized = _normalize_metadata_value(key, value)
        if normalized is not _DROP:
            allowed[key] = normalized
    return allowed or None


def _allow_approval_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None

    allowed: dict[str, Any] = {}
    for key in ("approval_type", "decision"):
        value = metadata.get(key)
        normalized = _normalize_metadata_value(key, value)
        if normalized is not _DROP:
            allowed[key] = normalized
    return allowed or None


def _normalize_metadata_value(key: str, value: Any) -> Any:
    if key in NUMERIC_METADATA_KEYS:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else _DROP
    if key in BOOLEAN_METADATA_KEYS:
        return value if isinstance(value, bool) else _DROP
    if key == "execution_mode":
        return _normalize_enum(value, EXECUTION_MODES)
    if key == "client_type":
        return _normalize_enum(value, CLIENT_TYPES)
    if key == "status":
        return _normalize_enum(value, TASK_STATUSES)
    if key == "error_code":
        if not isinstance(value, str) or _looks_sensitive_string(value):
            return _DROP
        return value if SAFE_CODE_PATTERN.fullmatch(value) else _DROP
    if key == "result_keys":
        if not isinstance(value, list):
            return _DROP
        if not all(
            isinstance(item, str)
            and not _looks_sensitive_string(item)
            and item in PUBLIC_RESULT_KEYS
            for item in value
        ):
            return _DROP
        return deepcopy(value)
    if key == "approval_type":
        return _normalize_enum(value, APPROVAL_TYPES)
    if key == "decision":
        return _normalize_enum(value, APPROVAL_DECISIONS)
    return _DROP


def _normalize_action(value: Any, allowed_values: set[str]) -> str:
    normalized = _normalize_enum(value, allowed_values)
    if normalized is _DROP:
        return UNKNOWN_ACTION
    return normalized


def _normalize_tenant_id(value: Any) -> str | object:
    if not isinstance(value, str) or _looks_sensitive_string(value):
        return _DROP
    normalized = value.strip().casefold()
    if SAFE_TENANT_PATTERN.fullmatch(normalized):
        return normalized
    return _DROP


def _normalize_capability_id(value: Any) -> str | None:
    if not isinstance(value, str) or _looks_sensitive_string(value):
        return None
    normalized = value.strip().casefold()
    if SAFE_CAPABILITY_ID_PATTERN.fullmatch(normalized):
        return normalized
    return None


def _normalize_task_id(value: Any) -> str | None:
    if not isinstance(value, str) or _looks_sensitive_string(value):
        return None
    normalized = value.strip().casefold()
    if SAFE_TASK_ID_PATTERN.fullmatch(normalized):
        return normalized
    return None


def _normalize_enum(value: Any, allowed_values: set[str]) -> str | object:
    if not isinstance(value, str) or _looks_sensitive_string(value):
        return _DROP
    normalized = value.strip().casefold()
    if normalized not in allowed_values:
        return _DROP
    return normalized


def _looks_sensitive_string(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in SENSITIVE_DIRECT_VALUES:
        return True
    return any(pattern.search(value) for pattern in SENSITIVE_STRING_PATTERNS)


def _utc_now() -> datetime:
    return datetime.now(UTC)


audit_store = InMemoryAuditStore()
