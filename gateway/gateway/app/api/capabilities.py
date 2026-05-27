from fastapi import APIRouter
from uuid import uuid4

from .errors import api_error
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
from ..security.output_filter import filter_capability_run_result
from ..tasks.models import CapabilityRunRequest, CapabilityTaskResult, WorkspaceSelection

router = APIRouter(prefix="/v1")

FILE_LIKE_INPUT_MODES = {"current_file", "selected_files", "workspace_snapshot"}


@router.get("/capabilities")
def list_capabilities() -> dict[str, list[dict]]:
    registry = default_registry()
    return {"capabilities": registry.list_public()}


@router.get("/capabilities/{capability_id}")
def get_capability(capability_id: str) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None:
        raise api_error(
            status_code=404,
            code="capability_not_found",
            message="Capability not found",
        )
    return capability.public_view()


@router.post("/capabilities/{capability_id}/run")
def run_capability(
    capability_id: str,
    request: CapabilityRunRequest,
) -> dict:
    registry = default_registry()
    capability = registry.find(capability_id)
    if capability is None:
        raise api_error(
            status_code=404,
            code="capability_not_found",
            message="Capability not found",
        )

    _validate_selection_range(request)
    _validate_request_input_modes(capability.input_modes, request)
    workspace_files = _workspace_files_from_request(request)
    text_inputs = _text_inputs_from_request(request)
    try:
        validated_files = validate_workspace_context_inputs(
            workspace_files,
            text_inputs,
            _input_policy_from_security(capability.security),
        )
    except InputPolicyViolation as exc:
        raise api_error(
            status_code=400,
            code=exc.code,
            message=exc.message,
        ) from exc

    runner = _runner_for_capability(capability.internal.runner)
    raw_result = runner.run(capability, request, validated_files)
    result = filter_capability_run_result(raw_result)
    task_result = CapabilityTaskResult(
        task_id=f"task_{uuid4().hex}",
        status="completed",
        result=result,
    )
    return task_result.model_dump()


def _validate_selection_range(request: CapabilityRunRequest) -> None:
    if request.workspace is None or request.workspace.selection is None:
        return

    selection = request.workspace.selection
    if _selection_range_is_invalid(selection):
        raise api_error(
            status_code=400,
            code="invalid_selection_range",
            message=(
                "Selection start_line and end_line must be provided together, "
                "be at least 1, and end_line must be greater than or equal "
                "to start_line."
            ),
        )


def _selection_range_is_invalid(selection: WorkspaceSelection) -> bool:
    if (selection.start_line is None) != (selection.end_line is None):
        return True
    if selection.start_line is None or selection.end_line is None:
        return False
    if selection.start_line < 1 or selection.end_line < 1:
        return True
    return selection.end_line < selection.start_line


def _validate_request_input_modes(
    input_modes: list[str],
    request: CapabilityRunRequest,
) -> None:
    if request.workspace is None:
        return

    declared_modes = set(input_modes)
    if request.workspace.selection is not None and "selection" not in declared_modes:
        raise api_error(
            status_code=400,
            code="unsupported_input_mode",
            message="Capability does not accept selection input.",
        )

    if request.workspace.git_diff is not None and "git_diff" not in declared_modes:
        raise api_error(
            status_code=400,
            code="unsupported_input_mode",
            message="Capability does not accept git_diff input.",
        )

    if request.workspace.files and not declared_modes.intersection(FILE_LIKE_INPUT_MODES):
        raise api_error(
            status_code=400,
            code="unsupported_input_mode",
            message="Capability does not accept workspace files input.",
        )


def _runner_for_capability(runner_name: str) -> CapabilityRunner:
    if runner_name == "mock":
        return MockCapabilityRunner()
    raise api_error(
        status_code=501,
        code="unsupported_runner",
        message="Capability runner is not supported by this Gateway.",
    )


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
