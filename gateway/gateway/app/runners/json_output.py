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
    parse_failed = False
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (TypeError, ValueError):
        parse_failed = True

    if parse_failed:
        raise HermesRunnerError(INVALID_JSON_OUTPUT_MESSAGE)

    if not isinstance(payload, Mapping):
        raise HermesRunnerError(INVALID_JSON_OUTPUT_MESSAGE)

    validation_failed = False
    try:
        result = CapabilityRunResult.model_validate(payload)
    except ValidationError:
        validation_failed = True

    if validation_failed:
        raise HermesRunnerError(INVALID_JSON_OUTPUT_MESSAGE)

    filter_failed = False
    try:
        return filter_capability_run_result(result)
    except OutputFilterViolation:
        filter_failed = True

    if filter_failed:
        raise HermesRunnerError(UNSAFE_OUTPUT_MESSAGE)

    raise HermesRunnerError(INVALID_JSON_OUTPUT_MESSAGE)


def _reject_nonstandard_json_constant(value: str) -> Any:
    raise ValueError(f"Non-standard JSON constant is not allowed: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key is not allowed.")
        result[key] = value
    return result
