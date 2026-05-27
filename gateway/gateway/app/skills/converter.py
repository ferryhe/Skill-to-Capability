import re
from typing import Any

from gateway.app.capabilities.manifest import CapabilityManifest

from .frontmatter import SkillFrontmatterError, parse_skill_frontmatter


VALID_CAPABILITY_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")

DEFAULT_DENY_FILE_GLOBS = [
    "**/.env",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/credentials.json",
]

DEFAULT_ALLOW_FILE_GLOBS = [
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.js",
    "**/*.jsx",
    "**/*.md",
    "**/*.json",
    "**/*.yaml",
    "**/*.yml",
]


def convert_skill_to_capability_manifest(text: str) -> CapabilityManifest:
    document = parse_skill_frontmatter(text)
    metadata = document.metadata
    skill_name = _required_metadata_string(metadata, "name")
    description = _required_metadata_string(metadata, "description")
    capability_id = _capability_id_from_name(skill_name)
    internal = {
        "skill_ref": skill_name,
        "runner": "hermes",
        "expose_skill_text": False,
    }
    required_env = _metadata_string_list(metadata, "required_environment_variables")
    if required_env:
        internal["required_env"] = required_env
    required_commands = _metadata_string_list(metadata, "required_commands")
    if required_commands:
        internal["required_commands"] = required_commands

    manifest: dict[str, Any] = {
        "id": capability_id,
        "name": _public_name(metadata, capability_id),
        "version": _metadata_string(metadata, "version", "0.1.0"),
        "category": _category(metadata),
        "visible_description": description,
        "input_modes": ["current_file", "selected_files", "git_diff"],
        "input_schema": {
            "type": "object",
            "required": ["instruction"],
            "properties": {
                "instruction": {
                    "type": "string",
                    "maxLength": 4000,
                },
                "files": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "required": ["path", "content"],
                        "properties": {
                            "path": {"type": "string"},
                            "content": {
                                "type": "string",
                                "maxLength": 50000,
                            },
                        },
                    },
                },
                "diff": {
                    "type": "string",
                    "maxLength": 200000,
                },
                "options": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "summary": {
                    "type": "string",
                },
                "findings": {
                    "type": "array",
                },
                "patch": {
                    "type": "string",
                },
                "recommended_tests": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "artifacts": {
                    "type": "array",
                },
                "safe_rationale": {
                    "type": "string",
                },
            },
        },
        "client_permissions": {
            "reads_workspace": True,
            "writes_workspace": "optional",
            "runs_commands": "optional",
            "sends_code_to_server": True,
        },
        "approval_policy": {
            "upload_context": "user_confirm_large",
            "apply_patch": "user_confirm",
            "run_commands": "user_confirm",
        },
        "security": {
            "max_files": 20,
            "max_total_input_bytes": 300000,
            "deny_file_globs": DEFAULT_DENY_FILE_GLOBS,
            "allow_file_globs": DEFAULT_ALLOW_FILE_GLOBS,
        },
        "internal": internal,
    }

    if manifest["category"] is None:
        del manifest["category"]

    return CapabilityManifest.model_validate(manifest)


def _required_metadata_string(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SkillFrontmatterError(f"SKILL.md frontmatter must include a non-empty {field!r}")
    return value.strip()


def _metadata_string(metadata: dict[str, Any], field: str, default: str) -> str:
    value = metadata.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _metadata_string_list(metadata: dict[str, Any], field: str) -> list[str] | None:
    value = metadata.get(field)
    if value is None:
        return None
    if not isinstance(value, list):
        raise SkillFrontmatterError(f"SKILL.md frontmatter {field!r} must be a list of strings")

    strings = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SkillFrontmatterError(
                f"SKILL.md frontmatter {field!r} must be a list of non-empty strings"
            )
        strings.append(item.strip())
    return strings


def _capability_id_from_name(name: str) -> str:
    if VALID_CAPABILITY_ID.fullmatch(name):
        return name

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        raise SkillFrontmatterError("SKILL.md frontmatter name must contain a slug character")
    if len(slug) == 1:
        slug = f"{slug}-skill"
    slug = slug[:81].strip("-")
    if len(slug) == 1:
        slug = f"{slug}-skill"
    return slug


def _public_name(metadata: dict[str, Any], capability_id: str) -> str:
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return capability_id.replace("-", " ").title()


def _category(metadata: dict[str, Any]) -> str | None:
    tags = metadata.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.strip():
                return tag.strip()
    return None
