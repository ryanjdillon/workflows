#!/usr/bin/env python3
"""Check that each commit message has an issue trailer, for example `Paperclip: PCL-12`.

A trailer links a commit to the issue that asked for it. Tools read it with
`git log --format='%(trailers:key=Paperclip)'`. The check reads the trailers
as git reads them (`git interpret-trailers --parse`), so a line that git
does not see as a trailer does not count. A commit by an exempt author, for
example the owner or a dependency bot, needs no trailer. Merge commits are
not checked.

Standalone by design: stdlib and git only, so the GitHub Action, the prek
hook, and the Nix package in this repo all run this one file. This file is
the only definition of the defaults. The defaults suit the owner's agent
repos; other callers give their own key and value pattern.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

KEY = "Paperclip"
VALUE_PATTERN = r"PCL-[1-9]\d*"
# git puts the diff under this line with `commit --verbose`.
SCISSORS = "# ------------------------ >8 ------------------------"


class ShallowClone(Exception):
    pass


@dataclass(frozen=True)
class Message:
    name: str
    author: str
    text: str


def strip_comments(text: str) -> str:
    """Remove the lines that git removes from a message in a commit-msg hook.

    Only `#` is a comment character: a `core.commentChar` setting is not read.
    """
    text = text.split(SCISSORS, 1)[0]
    return "\n".join(line for line in text.splitlines() if not line.startswith("#"))


def trailers(text: str) -> list[tuple[str, str]]:
    """Return the (key, value) trailers of a message, as git parses them."""
    parsed = subprocess.run(
        ["git", "interpret-trailers", "--parse", "--no-divider"],
        input=text,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pairs: list[tuple[str, str]] = []
    for line in parsed.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            pairs.append((key.strip(), value.strip()))
    return pairs


def check_message(
    message: Message,
    key: str,
    value: re.Pattern[str],
    exempt: frozenset[str],
) -> list[str]:
    if message.author in exempt:
        return []
    subject = message.text.strip().splitlines()[0] if message.text.strip() else ""
    where = f"{message.name} ({subject})" if subject else message.name
    values = [v for k, v in trailers(message.text) if k.lower() == key.lower()]
    if not values:
        return [
            (
                f"{where}: has no '{key}:' trailer; add '{key}: <issue>' as the"
                " last paragraph of the message"
            )
        ]
    return [
        f"{where}: the '{key}:' trailer {v!r} does not match {value.pattern!r}"
        for v in values
        if not value.fullmatch(v)
    ]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def range_messages(revision_range: str) -> list[Message]:
    """Read the author and message of each non-merge commit in a range."""
    # A shallow clone hides commits of the range, and the check would pass.
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        raise ShallowClone("the clone is shallow; fetch the full history")
    shas = git("rev-list", "--no-merges", revision_range).split()
    messages: list[Message] = []
    for sha in shas:
        author, _, text = git("log", "-1", "--format=%an%n%B", sha).partition("\n")
        messages.append(Message(sha[:12], author, text))
    return messages


def current_author() -> str:
    """The author name of the commit that git is making now."""
    # git gives GIT_AUTHOR_NAME the first place, as `git var` does. The Nix
    # sandbox has no writable home, where `git var` can fail.
    if os.environ.get("GIT_AUTHOR_NAME"):
        return os.environ["GIT_AUTHOR_NAME"].strip()
    ident = git("var", "GIT_AUTHOR_IDENT")
    return ident.split(" <", 1)[0].strip()


def file_messages(paths: list[Path]) -> list[Message]:
    author = current_author()
    return [
        Message(str(path), author, strip_comments(path.read_text(encoding="utf-8")))
        for path in paths
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="commit message files, as git gives to a commit-msg hook;"
        " the author is the author of the commit that git is making",
    )
    parser.add_argument(
        "--range",
        dest="revision_range",
        help="a git revision range, for example BASE..HEAD; checks each commit in it",
    )
    parser.add_argument("--key", default=KEY, help=f"the trailer key (default: {KEY})")
    parser.add_argument(
        "--value-pattern",
        default=VALUE_PATTERN,
        help=f"a regex that the whole trailer value must match (default: {VALUE_PATTERN})",
    )
    parser.add_argument(
        "--exempt-author",
        action="append",
        default=[],
        dest="exempt",
        help="an author name whose commits need no trailer; give it once for each name",
    )
    args = parser.parse_args(argv)

    if bool(args.files) == bool(args.revision_range):
        parser.error("give commit message files, or --range, but not both")
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.key):
        parser.error(f"the key {args.key!r} is not a git trailer token")

    value = re.compile(args.value_pattern)
    exempt = frozenset(name.strip() for name in args.exempt if name.strip())
    try:
        if args.revision_range:
            messages = range_messages(args.revision_range)
        else:
            messages = file_messages(args.files)
        errors = [
            error
            for message in messages
            for error in check_message(message, args.key, value, exempt)
        ]
    except ShallowClone as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        print(f"error: cannot read the commit messages: {error}", file=sys.stderr)
        return 1

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    skipped = sum(1 for message in messages if message.author in exempt)
    print(
        f"checked {len(messages) - skipped} commit message(s);"
        f" {skipped} by an exempt author"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
