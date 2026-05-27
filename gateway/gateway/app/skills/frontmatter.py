from dataclasses import dataclass
from typing import Any

import yaml


class SkillFrontmatterError(ValueError):
    """Raised when SKILL.md frontmatter is missing or invalid."""


@dataclass(frozen=True)
class SkillDocument:
    metadata: dict[str, Any]
    body: str


def parse_skill_frontmatter(text: str) -> SkillDocument:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SkillFrontmatterError("SKILL.md must start with YAML frontmatter")

    closing_index = _find_closing_delimiter(lines)
    if closing_index is None:
        raise SkillFrontmatterError("SKILL.md frontmatter must end with ---")

    frontmatter_text = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1 :])

    try:
        metadata = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise SkillFrontmatterError(f"Invalid SKILL.md frontmatter YAML: {exc}") from exc

    if not isinstance(metadata, dict):
        raise SkillFrontmatterError("SKILL.md frontmatter must be a YAML object")

    return SkillDocument(metadata=metadata, body=body)


def _find_closing_delimiter(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return index
    return None
