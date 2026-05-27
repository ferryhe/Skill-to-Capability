from collections.abc import Mapping
import re
from typing import Any


REDACTED_API_KEY = "[REDACTED_API_KEY]"
REDACTED_BEARER_TOKEN = "[REDACTED_BEARER_TOKEN]"
REDACTED_PATH = "[REDACTED_PATH]"
REDACTED_SECRET = "[REDACTED_SECRET]"

_BEARER_TOKEN_PATTERN = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
_OPENAI_API_KEY_PATTERN = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{8,}\b")
_PRIVATE_KEY_BLOCK_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Z0-9_.-]*(?:API[_-]?KEY|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|"
    r"SECRET|PASSWORD|TOKEN|PRIVATE[_-]?KEY)[A-Z0-9_.-]*\s*[:=]\s*)"
    r"([\"']?)[^\"'\s,;]+([\"']?)",
    re.IGNORECASE,
)
_JSON_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"([\"'][^\"']*(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|"
    r"password|token|private[_-]?key)[^\"']*[\"']\s*:\s*)"
    r"([\"'])[^\"']+(\2)",
    re.IGNORECASE,
)
_WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![\w:])[A-Za-z]:[\\/][^\s\"'<>)]*"
)
_FILE_URI_PATH_PATTERN = re.compile(r"\bfile:///[^\s\"'<>)]*")
_POSIX_PRIVATE_PATH_PATTERN = re.compile(
    r"(?<![\w:])/(?:home|Users|root|var|etc|tmp|private|workspace|mnt|opt|run)"
    r"(?:/[^\s\"'<>)]*)?"
)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|token|"
    r"private[_-]?key)",
    re.IGNORECASE,
)


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_string(value)

    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            redacted_key = _redact_mapping_key(key)
            if _is_sensitive_key(key):
                redacted[redacted_key] = REDACTED_SECRET
            else:
                redacted[redacted_key] = redact_sensitive_data(item)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)

    if isinstance(value, set):
        return {redact_sensitive_data(item) for item in value}

    if isinstance(value, frozenset):
        return frozenset(redact_sensitive_data(item) for item in value)

    return value


def redact_sensitive_string(value: str) -> str:
    redacted = _PRIVATE_KEY_BLOCK_PATTERN.sub(REDACTED_SECRET, value)
    redacted = _BEARER_TOKEN_PATTERN.sub(f"Bearer {REDACTED_BEARER_TOKEN}", redacted)
    redacted = _OPENAI_API_KEY_PATTERN.sub(REDACTED_API_KEY, redacted)
    redacted = _JSON_SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}"
            f"{REDACTED_SECRET}{match.group(2)}"
        ),
        redacted,
    )
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}"
            f"{REDACTED_SECRET}{match.group(3)}"
        ),
        redacted,
    )
    redacted = _FILE_URI_PATH_PATTERN.sub(REDACTED_PATH, redacted)
    redacted = _WINDOWS_ABSOLUTE_PATH_PATTERN.sub(REDACTED_PATH, redacted)
    redacted = _POSIX_PRIVATE_PATH_PATTERN.sub(REDACTED_PATH, redacted)
    return redacted


def _is_sensitive_key(key: Any) -> bool:
    return isinstance(key, str) and _SENSITIVE_KEY_PATTERN.search(key) is not None


def _redact_mapping_key(key: Any) -> Any:
    if isinstance(key, str):
        return redact_sensitive_string(key)
    return key
