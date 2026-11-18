#!/usr/bin/env python3
"""Check that commit messages name a source for the facts they state.

A part number in a commit message must come from a source, for example a
datasheet or a distributor page, and the message must name it on a `Source:`
line. A message that says a fact is "from memory" fails.

Standalone by design: stdlib only, so the GitHub Action, the prek hook, and
the Nix package in this repo all run this one file. This file is the only
definition of the default patterns.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# An LCSC part number: the letter C and 3 to 8 digits.
PART_PATTERNS = (r"\bC\d{3,8}\b",)
SOURCE_RE = re.compile(r"^Source:\s*\S", re.MULTILINE)
MEMORY_RE = re.compile(r"\bfrom memory\b", re.IGNORECASE)
# git puts the diff under this line with `commit --verbose`.
SCISSORS = "# ------------------------ >8 ------------------------"


@dataclass(frozen=True)
class Message:
    name: str
    text: str


def strip_comments(text: str) -> str:
    """Remove the lines that git removes from a message in a commit-msg hook."""
    text = text.split(SCISSORS, 1)[0]
    return "\n".join(line for line in text.splitlines() if not line.startswith("#"))


def check_message(message: Message, part_patterns: list[re.Pattern[str]]) -> list[str]:
    errors: list[str] = []
    subject = message.text.strip().splitlines()[0] if message.text.strip() else ""
    where = f"{message.name} ({subject})" if subject else message.name

    parts = sorted(
        {
            found.group(0)
            for pattern in part_patterns
            for found in pattern.finditer(message.text)
        }
    )
    if parts and not SOURCE_RE.search(message.text):
        errors.append(
            f"{where}: names {', '.join(parts)} with no 'Source:' line;"
            " add a line that names the datasheet or page it came from"
        )
    for found in MEMORY_RE.finditer(message.text):
        errors.append(
            f"{where}: says {found.group(0)!r}; read the fact from a source and name it"
        )
    return errors


def range_messages(revision_range: str) -> list[Message]:
    """Read the messages of the non-merge commits in a git revision range."""
    shas = subprocess.run(
        ["git", "rev-list", "--no-merges", revision_range],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    messages: list[Message] = []
    for sha in shas:
        text = subprocess.run(
            ["git", "log", "-1", "--format=%B", sha],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        messages.append(Message(sha[:12], text))
    return messages


def file_messages(paths: list[Path]) -> list[Message]:
    return [
        Message(str(path), strip_comments(path.read_text(encoding="utf-8")))
        for path in paths
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="commit message files, as git gives to a commit-msg hook",
    )
    parser.add_argument(
        "--range",
        dest="revision_range",
        help="a git revision range, for example BASE..HEAD; checks each commit in it",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help=f"regex for a part number; replaces the default ({' '.join(PART_PATTERNS)})",
    )
    args = parser.parse_args(argv)

    if bool(args.files) == bool(args.revision_range):
        parser.error("give commit message files, or --range, but not both")

    part_patterns = [
        re.compile(source)
        for source in (PART_PATTERNS if args.patterns is None else args.patterns)
    ]
    try:
        if args.revision_range:
            messages = range_messages(args.revision_range)
        else:
            messages = file_messages(args.files)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        print(f"error: cannot read the commit messages: {error}", file=sys.stderr)
        return 1

    errors = [
        error for message in messages for error in check_message(message, part_patterns)
    ]
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"checked {len(messages)} commit message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
