#!/usr/bin/env python3
"""Check agent instruction files (SYSTEM.md, AGENTS.md) against their budget.

Standalone by design: stdlib only, so the GitHub Action, the pre-commit hook,
and the Nix package in this repo all run this one file. This file is the only
definition of the limits. The reasons for them are in docs/system-prompt.md of
ryanjdillon/agents.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BYTE_LIMIT = 8192
RULE_LIMIT = 60
PROMOTION_HEADING = "# SYSTEM.md"
DOCS = "https://github.com/ryanjdillon/agents/blob/main/docs"

RULE_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
H1_RE = re.compile(r"^# \S")


def strip_non_prose(lines: list[str]) -> list[str]:
    """Remove fenced code blocks and HTML comments.

    A list item inside a code sample or a comment is not a rule that the agent
    is told to obey, so it must not count against the rule limit.
    """
    prose: list[str] = []
    in_fence = False
    in_comment = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
            continue
        prose.append(line)
    return prose


def count_rules(lines: list[str]) -> int:
    return sum(1 for line in strip_non_prose(lines) if RULE_RE.match(line))


def check_promotion_section(path: Path, lines: list[str]) -> list[str]:
    """A repo AGENTS.md ends with the `# SYSTEM.md` section.

    The promotion process finds the section by its heading and reads it to the
    end of the file, so the heading must exist and be the last level-one heading.
    """
    headings = [line.rstrip() for line in strip_non_prose(lines) if H1_RE.match(line)]
    if PROMOTION_HEADING not in headings:
        return [f"{path}: no '{PROMOTION_HEADING}' section; see {DOCS}/promotion.md"]
    if headings[-1] != PROMOTION_HEADING:
        return [f"{path}: '{PROMOTION_HEADING}' must be the last level-one section"]
    return []


def check_file(
    path: Path, byte_limit: int, rule_limit: int
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"{path}: cannot read: {error}"], []

    lines = text.splitlines()
    size = len(text.encode("utf-8"))
    rules = count_rules(lines)
    print(
        f"{path}: {size} bytes (limit {byte_limit}), {rules} rules (warn above {rule_limit})"
    )

    if size > byte_limit:
        errors.append(
            f"{path}: larger than {byte_limit} bytes; move rules out of it "
            f"(see {DOCS}/system-prompt.md) before you increase the limit"
        )
    if rules > rule_limit:
        warnings.append(
            f"{path}: more than {rule_limit} rules; apply the admission test "
            f"in {DOCS}/system-prompt.md"
        )
    if path.name == "AGENTS.md":
        errors.extend(check_promotion_section(path, lines))
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files", nargs="+", type=Path, help="SYSTEM.md or AGENTS.md files"
    )
    parser.add_argument("--byte-limit", type=int, default=BYTE_LIMIT)
    parser.add_argument("--rule-limit", type=int, default=RULE_LIMIT)
    args = parser.parse_args(argv)

    failed = False
    for path in args.files:
        errors, warnings = check_file(path, args.byte_limit, args.rule_limit)
        for message in warnings:
            print(f"warning: {message}", file=sys.stderr)
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        failed = failed or bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
