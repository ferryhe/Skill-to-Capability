#!/usr/bin/env python3
"""Validate Skill-to-Capability JSON schemas and contract fixtures.

The contract fixtures use filename conventions:

- ``<schema>.valid.<ext>`` must validate successfully.
- ``<schema>.invalid-<reason>.<ext>`` must fail validation.

Supported schema prefixes are ``capability``, ``run-request``, and ``run-result``.
YAML and JSON fixtures are both supported. Example capability manifests are also
validated as positive capability fixtures.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
FIXTURE_DIR = ROOT / "tests" / "contracts" / "fixtures"
EXAMPLE_CAPABILITIES_DIR = ROOT / "examples" / "capabilities"

SCHEMA_FILES = {
    "capability": SCHEMA_DIR / "capability.schema.json",
    "run-request": SCHEMA_DIR / "run-request.schema.json",
    "run-result": SCHEMA_DIR / "run-result.schema.json",
}

def validation_error_matches_reason(reason: str, error: jsonschema.ValidationError) -> bool:
    error_path = list(error.path)
    if reason == "expose-skill-text":
        return error.validator == "const" and error_path == ["internal", "expose_skill_text"]
    if reason == "prompt-leak":
        return (
            error.validator == "additionalProperties"
            and error_path == []
            and "prompt" in unexpected_properties(error)
        )
    raise ValueError(f"No expected validation matcher configured for invalid fixture reason {reason!r}")


def unexpected_properties(error: jsonschema.ValidationError) -> set[str]:
    params = getattr(error, "params", None)
    if isinstance(params, dict):
        if isinstance(params.get("additionalProperty"), str):
            return {params["additionalProperty"]}
        additional_properties = params.get("additionalProperties")
        if isinstance(additional_properties, list):
            return {value for value in additional_properties if isinstance(value, str)}

    if isinstance(error.instance, dict) and isinstance(error.schema, dict):
        declared_properties = error.schema.get("properties", {})
        if isinstance(declared_properties, dict):
            return {key for key in error.instance if key not in declared_properties}

    return set(re.findall(r"'([^']+)'", error.message))


def load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    if path.suffix == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported fixture extension for {path}")


def load_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for name, path in SCHEMA_FILES.items():
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        schemas[name] = schema
    return schemas


def schema_name_for_fixture(path: Path) -> str:
    name = path.name
    for schema_name in SCHEMA_FILES:
        if name.startswith(f"{schema_name}."):
            return schema_name
    raise ValueError(
        f"Cannot infer schema for fixture {path}. Expected one of: "
        + ", ".join(f"{name}.*" for name in SCHEMA_FILES)
    )


def expect_valid(path: Path) -> bool:
    name = path.name
    if ".valid." in name:
        return True
    if ".invalid-" in name:
        return False
    raise ValueError(f"Fixture name must contain .valid. or .invalid-: {path}")


def invalid_reason(path: Path) -> str | None:
    marker = ".invalid-"
    if marker not in path.name:
        return None
    return path.name.split(marker, 1)[1].rsplit(".", 1)[0]


def invalid_fixture_matches_reason(path: Path, errors: list[jsonschema.ValidationError]) -> bool:
    reason = invalid_reason(path)
    if not reason:
        return False
    try:
        return any(validation_error_matches_reason(reason, error) for error in errors)
    except ValueError as exc:
        raise ValueError(f"{exc} in {path}") from exc


def validate_document(schema: dict[str, Any], document: Any) -> list[jsonschema.ValidationError]:
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(validator.iter_errors(document), key=lambda error: list(error.path))


def format_errors(path: Path, errors: list[jsonschema.ValidationError]) -> list[str]:
    return [format_error(path, error) for error in errors]


def format_error(path: Path, error: jsonschema.ValidationError) -> str:
    location = "/".join(str(part) for part in error.path) or "<root>"
    return f"{path}: {location}: {error.message}"


def validate_named_fixture(path: Path, schemas: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    schema_name = schema_name_for_fixture(path)
    should_pass = expect_valid(path)
    document = load_document(path)
    errors = validate_document(schemas[schema_name], document)
    formatted_errors = format_errors(path, errors)
    if should_pass and errors:
        return False, "expected valid but failed:\n" + "\n".join(formatted_errors)
    if not should_pass and not errors:
        return False, "expected invalid but passed"
    if not should_pass and not invalid_fixture_matches_reason(path, errors):
        return (
            False,
            "expected invalid fixture to fail for reason "
            f"{invalid_reason(path)!r}, but got different errors:\n" + "\n".join(formatted_errors),
        )
    return True, "ok"


def validate_example_capability(path: Path, schemas: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    document = load_document(path)
    errors = validate_document(schemas["capability"], document)
    if errors:
        return False, "example capability failed:\n" + "\n".join(format_errors(path, errors))
    return True, "ok"


def iter_fixture_files() -> list[Path]:
    if not FIXTURE_DIR.exists():
        return []
    return sorted(
        path
        for path in FIXTURE_DIR.iterdir()
        if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}
    )


def iter_example_capabilities() -> list[Path]:
    if not EXAMPLE_CAPABILITIES_DIR.exists():
        return []
    return sorted(
        path
        for path in EXAMPLE_CAPABILITIES_DIR.iterdir()
        if path.is_file() and path.suffix in {".yaml", ".yml", ".json"}
    )


def main() -> int:
    schemas = load_schemas()
    failures: list[str] = []
    checked = 0

    for path in iter_fixture_files():
        checked += 1
        ok, message = validate_named_fixture(path, schemas)
        if not ok:
            failures.append(message)

    for path in iter_example_capabilities():
        checked += 1
        ok, message = validate_example_capability(path, schemas)
        if not ok:
            failures.append(message)

    if checked == 0:
        failures.append("No contract fixtures or example capabilities were found.")

    if failures:
        print("Contract validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Contract validation passed ({checked} documents).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
