#!/usr/bin/env python3
"""Validate the frontmatter of every SKILL.md under one or more roots.

Standalone by design: stdlib only, so the GitHub Action, the prek hook, and
the Nix package in this repo all run this one file. This file is the only
definition of the rules.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
ALLOWED_KEYS = ("name", "description")
# A plain YAML scalar must not start with one of these characters.
YAML_SPECIAL_START = "[]{}&*!|>'\"%@`#,?:-"


class SkillError(Exception):
    pass


def parse_frontmatter(skill_file: Path) -> dict[str, str]:
    """Read the leading --- delimited block as flat `key: value` pairs.

    This is not a full YAML parser, so the script has no dependencies. Thus it
    accepts only a subset that is also valid YAML: the keys `name` and
    `description`, each on one line, with a plain scalar value. Some consumers
    read only flat `key: value` lines, and Claude Code parses YAML.
    """
    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise SkillError(f"{skill_file}: cannot read SKILL.md: {error}") from error

    if not lines or lines[0].strip() != "---":
        raise SkillError(f"{skill_file}: frontmatter must start with '---'")

    try:
        closing = next(
            i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"
        )
    except StopIteration:
        raise SkillError(f"{skill_file}: frontmatter is not closed") from None

    fields: dict[str, str] = {}
    for lineno, line in enumerate(lines[1:closing], 2):
        if not line.strip():
            continue
        if line[0].isspace():
            raise SkillError(
                f"{skill_file}:{lineno}: continuation line; put each value on one line"
            )
        if ": " not in line:
            raise SkillError(f"{skill_file}:{lineno}: expected 'key: value'")
        key, _, value = line.partition(": ")
        if key not in ALLOWED_KEYS:
            raise SkillError(
                f"{skill_file}:{lineno}: key {key!r} is not allowed;"
                f" use only {', '.join(ALLOWED_KEYS)}"
            )
        if key in fields:
            raise SkillError(f"{skill_file}:{lineno}: duplicate key {key!r}")
        fields[key] = check_plain_scalar(skill_file, lineno, key, value.strip())

    return fields


def check_plain_scalar(skill_file: Path, lineno: int, key: str, value: str) -> str:
    """Refuse a value that YAML does not read as one plain string."""
    where = f"{skill_file}:{lineno}: {key!r}"
    if not value:
        raise SkillError(f"{where} has no value on its line")
    if value[0] in YAML_SPECIAL_START:
        raise SkillError(f"{where} starts with the YAML character {value[0]!r}")
    if ": " in value or value.endswith(":"):
        raise SkillError(f"{where} contains ': ', which is not valid YAML here")
    if " #" in value:
        raise SkillError(f"{where} contains ' #', which YAML reads as a comment")
    return value


def validate_symlinks(skill_dir: Path) -> None:
    root = skill_dir.resolve(strict=True)
    for directory, directories, files in os.walk(skill_dir, followlinks=False):
        for name in sorted(directories + files):
            link = Path(directory) / name
            if not link.is_symlink():
                continue
            target = os.readlink(link)
            if os.path.isabs(target):
                raise SkillError(f"{link}: absolute symlink target is unsafe: {target}")
            try:
                resolved = link.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise SkillError(
                    f"{link}: broken or cyclic symlink: {target}"
                ) from error
            if os.path.commonpath((str(root), str(resolved))) != str(root):
                raise SkillError(f"{link}: symlink escapes skill directory: {target}")


def validate(skill_file: Path) -> str:
    fields = parse_frontmatter(skill_file)

    name = fields.get("name")
    if not name:
        raise SkillError(f"{skill_file}: frontmatter 'name' is required")
    if len(name) > MAX_NAME:
        raise SkillError(f"{skill_file}: 'name' exceeds {MAX_NAME} characters")
    if NAME_RE.fullmatch(name) is None:
        raise SkillError(
            f"{skill_file}: invalid skill name {name!r}; expected ^[a-z0-9]+(-[a-z0-9]+)*$"
        )

    description = fields.get("description", "")
    if not description.strip():
        raise SkillError(f"{skill_file}: frontmatter 'description' must be non-empty")
    if len(description) > MAX_DESCRIPTION:
        raise SkillError(
            f"{skill_file}: 'description' exceeds {MAX_DESCRIPTION} characters"
        )

    directory = skill_file.parent.name
    if name != directory:
        raise SkillError(
            f"{skill_file}: name {name!r} does not match directory {directory!r}"
        )

    validate_symlinks(skill_file.parent)
    return name


def main(argv: list[str]) -> int:
    roots = [Path(argument) for argument in argv[1:]] or [Path("skills")]

    skill_files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            print(f"skill root {root} is not a directory", file=sys.stderr)
            return 1
        skill_files.extend(
            sorted(
                Path(directory) / filename
                for directory, _, files in os.walk(root, followlinks=False)
                for filename in files
                if filename == "SKILL.md"
            )
        )

    errors: list[str] = []
    seen: dict[str, Path] = {}
    for skill_file in skill_files:
        try:
            name = validate(skill_file)
        except SkillError as error:
            errors.append(str(error))
            continue
        if name in seen:
            errors.append(
                f"duplicate skill name {name!r}: {seen[name]} and {skill_file}"
            )
            continue
        seen[name] = skill_file

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1

    print(f"validated {len(seen)} skill(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
