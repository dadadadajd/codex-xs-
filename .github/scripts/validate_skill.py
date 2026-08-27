#!/usr/bin/env python3
"""Portable CI checks for the public Codex Skill package."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise ValueError(message)


def validate_skill(root: Path) -> None:
    skill_file = root / "SKILL.md"
    agent_file = root / "agents" / "openai.yaml"
    if not skill_file.is_file():
        fail("SKILL.md is missing")
    if not agent_file.is_file():
        fail("agents/openai.yaml is missing")

    text = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        fail("SKILL.md needs YAML frontmatter")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        fail("SKILL.md frontmatter must be an object")

    name = metadata.get("name")
    description = metadata.get("description")
    if name != root.name:
        fail("Skill name must match its directory")
    if not isinstance(name, str) or len(name) > 64 or not NAME_RE.fullmatch(name):
        fail("Skill name must be lowercase kebab-case and at most 64 characters")
    if not isinstance(description, str) or not 40 <= len(description) <= 1024:
        fail("Skill description must contain 40-1024 characters")
    if re.search(r"\b(?:TODO|TBD)\b", text):
        fail("SKILL.md contains an unresolved placeholder")

    agent = yaml.safe_load(agent_file.read_text(encoding="utf-8"))
    interface = agent.get("interface") if isinstance(agent, dict) else None
    if not isinstance(interface, dict):
        fail("agents/openai.yaml needs an interface object")
    for field in ("display_name", "short_description", "default_prompt"):
        if not str(interface.get(field, "")).strip():
            fail(f"agents/openai.yaml is missing interface.{field}")

    for target in LINK_RE.findall(text):
        if "://" in target or target.startswith("#"):
            continue
        resolved = (root / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            fail(f"SKILL.md link leaves the Skill directory: {target}")
        if not resolved.is_file():
            fail(f"SKILL.md link target does not exist: {target}")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_skill.py <skill-directory>", file=sys.stderr)
        return 2
    try:
        validate_skill(Path(argv[1]))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Skill validation failed: {exc}", file=sys.stderr)
        return 1
    print("Skill structure is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

