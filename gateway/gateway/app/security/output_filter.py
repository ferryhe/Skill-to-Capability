from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from pydantic import ValidationError

from gateway.app.security.redaction import redact_sensitive_data
from gateway.app.tasks.models import CapabilityRunResult


PROHIBITED_OUTPUT_KEYS = {
    "prompt",
    "trace",
    "skill_text",
    "internal",
    "skill_ref",
    "model_policy",
    "raw_runner_output",
    "chain_of_thought",
}

_PROHIBITED_OUTPUT_KEY_PATTERNS = (
    re.compile(r"^(?:[a-z0-9]+_)*prompt(?:_[a-z0-9]+)*$"),
    re.compile(r"^(?:[a-z0-9]+_)*trace(?:_[a-z0-9]+)*$"),
    re.compile(r"^(?:[a-z0-9]+_)*skill_(?:body|text|ref)(?:_[a-z0-9]+)*$"),
    re.compile(r"^(?:[a-z0-9]+_)*chain_of_thought(?:_[a-z0-9]+)*$"),
    re.compile(r"^(?:[a-z0-9]+_)*raw_runner_output(?:_[a-z0-9]+)*$"),
)

_SUSPECTED_LEAKAGE_PATTERNS = (
    re.compile(r"^---\s*\nname:\s*.+\ndescription:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(?:internal\s+)?(?:system|developer)\s+prompt\b", re.IGNORECASE),
    re.compile(r"\b(?:full|raw)\s+skill\s+(?:body|text)\b", re.IGNORECASE),
    re.compile(r"\bchain[-_ ]of[-_ ]thought\b", re.IGNORECASE),
)


class OutputFilterViolation(ValueError):
    code = "output_filter_violation"
    message = "Runner output was blocked by safety filters."

    def __init__(self, reason: str) -> None:
        self.details = {"reason": reason}
        super().__init__(self.message)


def filter_capability_run_result(
    result: CapabilityRunResult | Mapping[str, Any],
) -> CapabilityRunResult:
    if isinstance(result, CapabilityRunResult):
        payload = result.model_dump(mode="python")
    elif isinstance(result, Mapping):
        payload = dict(result)
    else:
        raise OutputFilterViolation("invalid_output_type")

    _reject_unsafe_output(payload)
    redacted_payload = redact_sensitive_data(payload)
    try:
        return CapabilityRunResult.model_validate(redacted_payload)
    except ValidationError as exc:
        raise OutputFilterViolation("invalid_output_shape") from exc


def _reject_unsafe_output(value: Any) -> None:
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in _SUSPECTED_LEAKAGE_PATTERNS):
            raise OutputFilterViolation("suspected_internal_leakage")
        return

    if isinstance(value, Mapping):
        for key, item in value.items():
            if _key_contains_suspected_leakage(key):
                raise OutputFilterViolation("suspected_internal_leakage")
            if _is_prohibited_key(key):
                raise OutputFilterViolation("private_output_field")
            _reject_unsafe_output(item)
        return

    if isinstance(value, (set, frozenset)):
        for item in value:
            _reject_unsafe_output(item)
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_unsafe_output(item)
        return

    if isinstance(value, Iterable):
        raise OutputFilterViolation("unsupported_output_iterable")


def _is_prohibited_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized_key = _normalize_key(key)
    return normalized_key in PROHIBITED_OUTPUT_KEYS or any(
        pattern.match(normalized_key) for pattern in _PROHIBITED_OUTPUT_KEY_PATTERNS
    )


def _key_contains_suspected_leakage(key: Any) -> bool:
    return isinstance(key, str) and any(
        pattern.search(key) for pattern in _SUSPECTED_LEAKAGE_PATTERNS
    )


def _normalize_key(key: str) -> str:
    separated = re.sub(r"[\s-]+", "_", key.strip())
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", separated)
    separated = re.sub(r"_+", "_", separated)
    return separated.strip("_").lower()
