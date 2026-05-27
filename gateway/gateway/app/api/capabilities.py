from fastapi import APIRouter, HTTPException
from uuid import uuid4

from ..capabilities.manifest import SecurityPolicy
from ..capabilities.registry import default_registry
from ..runners.base import CapabilityRunner
from ..runners.mock_runner import MockCapabilityRunner
from ..security.input_policy import (
    InputPolicy,
    InputPolicyViolation,
    WorkspaceInputFile,
    WorkspaceInputText,
    validate_workspace_context_inputs,
)
from ..tasks.models import CapabilityRunRequest, CapabilityTaskResult

router = APIRouter(prefix="/v1")


@router.get("/capabilities")
def list_capabilities() -> dict[str, list[dict]]:
    registry = default_registry()
    return {"capabilities": registry.list_public()}


@router.get("/capabilities/{capability_id}")
def get_capability(capability_id: str) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    return capability.public_view()


@router.post("/capabilities/{capability_id}/run")
def run_capability(
    capability_id: str,
    request: CapabilityRunRequest,
) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None:
        raise HTTPException(status_code=404, detail="Capability not found")

    workspace_files = _workspace_files_from_request(request)
    text_inputs = _text_inputs_from_request(request)
    try:
        validated_files = validate_workspace_context_inputs(
            workspace_files,
            text_inputs,
            _input_policy_from_security(capability.security),
        )
    except InputPolicyViolation as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    runner: CapabilityRunner = MockCapabilityRunner()
    result = runner.run(capability, request, validated_files)
    task_result = CapabilityTaskResult(
        task_id=f"task_{uuid4().hex}",
        status="completed",
        result=result,
    )
    return task_result.model_dump()


def _workspace_files_from_request(
    request: CapabilityRunRequest,
) -> list[WorkspaceInputFile]:
    if request.workspace is None:
        return []
    files = [
        WorkspaceInputFile(
            path=file.path,
            content=file.content,
            sha256=file.sha256,
        )
        for file in request.workspace.files
    ]
    if request.workspace.selection is not None:
        files.append(
            WorkspaceInputFile(
                path=request.workspace.selection.path,
                content=request.workspace.selection.content,
            )
        )
    return files


def _text_inputs_from_request(
    request: CapabilityRunRequest,
) -> list[WorkspaceInputText]:
    if request.workspace is None or request.workspace.git_diff is None:
        return []
    return [
        WorkspaceInputText(
            label="workspace.git_diff",
            content=request.workspace.git_diff,
        )
    ]


def _input_policy_from_security(security: SecurityPolicy | None) -> InputPolicy:
    default_policy = InputPolicy()
    if security is None:
        return default_policy

    return InputPolicy(
        max_files=security.max_files,
        max_total_input_bytes=security.max_total_input_bytes,
        deny_file_globs=(
            security.deny_file_globs
            if security.deny_file_globs is not None
            else default_policy.deny_file_globs
        ),
        allow_file_globs=security.allow_file_globs,
    )
