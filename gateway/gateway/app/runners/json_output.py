import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from gateway.app.security.output_filter import (
    OutputFilterViolation,
    filter_capability_run_result,
)
from gateway.app.tasks.models import CapabilityRunResult


INVALID_JSON_OUTPUT_MESSAGE = "Hermes runner returned invalid JSON output."
UNSAFE_OUTPUT_MESSAGE = "Hermes runner returned unsafe output."


class HermesRunnerError(ValueError):
    """Safe public error for Hermes runner failures."""


def parse_runner_json_output(text: str) -> CapabilityRunResult:
    payload, parse_failed = _load_json_payload(text)
    if parse_failed or not isinstance(payload, Mapping):
        raise HermesRunnerError(INVALID_JSON_OUTPUT_MESSAGE)

    result, validation_failed = _validate_capability_run_result(payload)
    if validation_failed or result is None:
        raise HermesRunnerError(INVALID_JSON_OUTPUT_MESSAGE)

    filtered_result, filter_failed = _filter_capability_run_result(result)
    if filter_failed or filtered_result is None:
        raise HermesRunnerError(UNSAFE_OUTPUT_MESSAGE)

    return filtered_result


def _load_json_payload(text: str) -> tuple[Any, bool]:
    try:
        return (
            json.loads(
                text,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonstandard_json_constant,
            ),
            False,
        )
    except (TypeError, ValueError):
        return None, True


def _validate_capability_run_result(
    payload: Mapping[str, Any],
) -> tuple[CapabilityRunResult | None, bool]:
    try:
        return CapabilityRunResult.model_validate(payload), False
    except ValidationError:
        return None, True


def _filter_capability_run_result(
    result: CapabilityRunResult,
) -> tuple[CapabilityRunResult | None, bool]:
    try:
        return filter_capability_run_result(result), False
    except OutputFilterViolation:
        return None, True


def _reject_nonstandard_json_constant(value: str) -> Any:
    raise ValueError(f"Non-standard JSON constant is not allowed: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key is not allowed.")
        result[key] = value
    return result
