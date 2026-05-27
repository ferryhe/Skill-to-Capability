from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import yaml

from gateway.app.capabilities.registry import ManifestLoadError, default_registry, load_manifest
from gateway.app.skills.converter import convert_skill_to_capability_manifest
from gateway.app.skills.frontmatter import SkillFrontmatterError


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillgw")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capabilities_parser = subparsers.add_parser("capabilities")
    capability_commands = capabilities_parser.add_subparsers(
        dest="capability_command",
        required=True,
    )

    generate_parser = capability_commands.add_parser("generate")
    generate_parser.add_argument("--skill", required=True, type=Path)
    generate_parser.add_argument("--out", required=True, type=Path)
    generate_parser.set_defaults(handler=_generate_capability)

    validate_parser = capability_commands.add_parser("validate")
    validate_parser.add_argument("manifest", type=Path)
    validate_parser.set_defaults(handler=_validate_capability)

    list_parser = capability_commands.add_parser("list")
    list_parser.set_defaults(handler=_list_capabilities)

    return parser


def _generate_capability(args: argparse.Namespace) -> int:
    skill_path: Path = args.skill
    out_path: Path = args.out

    try:
        skill_text = skill_path.read_text(encoding="utf-8")
        manifest = convert_skill_to_capability_manifest(skill_text)
        manifest_yaml = yaml.safe_dump(
            manifest.model_dump(mode="json", exclude_none=True),
            sort_keys=False,
        )
        out_path.write_text(manifest_yaml, encoding="utf-8")
    except (OSError, SkillFrontmatterError, ValueError):
        _print_error(f"Failed to generate capability manifest from {skill_path.name}.")
        return 1

    print(f"Generated capability {manifest.id}.")
    return 0


def _validate_capability(args: argparse.Namespace) -> int:
    manifest_path: Path = args.manifest
    try:
        manifest = load_manifest(manifest_path)
    except ManifestLoadError:
        _print_error(f"Invalid capability manifest {manifest_path.name}.")
        return 1

    print(f"Valid capability {manifest.id}: {manifest.name}")
    return 0


def _list_capabilities(_: argparse.Namespace) -> int:
    try:
        capabilities = default_registry().list_public()
    except ManifestLoadError:
        _print_error("Failed to load built-in capability manifests.")
        return 1

    for capability in capabilities:
        print(f"{capability['id']}\t{capability['name']}")
    return 0


def _print_error(message: str) -> None:
    print(message, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
