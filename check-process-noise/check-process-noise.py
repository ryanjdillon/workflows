#!/usr/bin/env python3
"""Find issue ids and review-process words in source comments and docstrings.

A comment explains why the code is as it is. A reference to an issue, or to
the review that produced the code, does not help the next person who reads
the code, and it becomes wrong when the process moves on.

Standalone by design: stdlib only, so the GitHub Action, the prek hook, and
the Nix package in this repo all run this one file. This file is the only
definition of the default patterns.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ISSUE_PATTERN = r"\bDIL-\d+\b"
REVIEW_PATTERNS = (
    r"\bblocker\b",
    r"\bshould-fix\b",
    r"\bfinding \d+\b",
    r"\bre-review\b",
    r"\bhand-?back\b",
    r"\breviewer'?s?\b",
)
DEFAULT_GLOBS = ("*.py",)

# Files that have only line comments. The check reads only lines that start
# with the marker, because a marker in the middle of a line can be in a string.
LINE_COMMENT_MARKERS = {
    "#": (".sh", ".bash", ".zsh", ".nix", ".yml", ".yaml", ".toml", ".cfg"),
    "//": (".rs", ".go", ".js", ".jsx", ".ts", ".tsx", ".c", ".h", ".cpp", ".hpp"),
}
LINE_COMMENT_NAMES = {"#": ("Makefile", "justfile", "Dockerfile")}


@dataclass(frozen=True)
class Text:
    """A comment or a docstring, with the line where it starts."""

    line: int
    text: str


@dataclass(frozen=True)
class Match:
    path: Path
    line: int
    word: str
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.word!r} in: {self.text.strip()}"


class UnknownSyntax(Exception):
    pass


def python_texts(source: str) -> Iterator[Text]:
    """Yield the comments and the docstrings of a Python file."""
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type == tokenize.COMMENT:
            yield Text(token.start[0], token.string)

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        first = node.body[0]
        for offset, line in enumerate(first.value.value.splitlines()):
            yield Text(first.lineno + offset, line)


def line_comment_texts(source: str, marker: str) -> Iterator[Text]:
    for number, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith(marker):
            yield Text(number, line)


def comment_marker(path: Path) -> str | None:
    for marker, names in LINE_COMMENT_NAMES.items():
        if path.name in names:
            return marker
    for marker, suffixes in LINE_COMMENT_MARKERS.items():
        if path.suffix in suffixes:
            return marker
    return None


def texts(path: Path, source: str) -> Iterator[Text]:
    if path.suffix in (".py", ".pyi"):
        return python_texts(source)
    marker = comment_marker(path)
    if marker is None:
        raise UnknownSyntax(f"{path}: no comment syntax is known for this file type")
    return line_comment_texts(source, marker)


def check_file(path: Path, patterns: list[re.Pattern[str]]) -> list[Match]:
    source = path.read_text(encoding="utf-8")
    matches: list[Match] = []
    for text in texts(path, source):
        for pattern in patterns:
            for found in pattern.finditer(text.text):
                matches.append(Match(path, text.line, found.group(0), text.text))
    return sorted(matches, key=lambda match: match.line)


def tracked_files(globs: list[str], exclude: list[str]) -> list[Path]:
    """List the files that git tracks and that match a glob."""
    output = subprocess.run(
        ["git", "ls-files", "-z", "--", *globs],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    paths = [name for name in output.split("\0") if name]
    return [
        Path(name)
        for name in paths
        if not any(fnmatch.fnmatch(name, pattern) for pattern in exclude)
    ]


def compile_patterns(
    issue_pattern: str, review_patterns: list[str]
) -> list[re.Pattern[str]]:
    sources = ([issue_pattern] if issue_pattern else []) + review_patterns
    return [re.compile(source, re.IGNORECASE) for source in sources]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="files to check; with none, the files that git tracks and that match --glob",
    )
    parser.add_argument(
        "--glob",
        action="append",
        dest="globs",
        help=f"a git pathspec for the tracked files (default: {' '.join(DEFAULT_GLOBS)})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="an fnmatch pattern; skip the tracked files that match it",
    )
    parser.add_argument(
        "--issue-pattern",
        default=ISSUE_PATTERN,
        help=f"regex for an issue id; empty turns it off (default: {ISSUE_PATTERN})",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="regex for a review-process word; replaces the default words",
    )
    args = parser.parse_args(argv)

    patterns = compile_patterns(
        args.issue_pattern,
        list(REVIEW_PATTERNS) if args.patterns is None else args.patterns,
    )
    files = args.files or tracked_files(args.globs or list(DEFAULT_GLOBS), args.exclude)

    errors: list[str] = []
    for path in files:
        try:
            errors.extend(str(match) for match in check_file(path, patterns))
        except (
            OSError,
            UnicodeError,
            SyntaxError,
            tokenize.TokenError,
            UnknownSyntax,
        ) as error:
            errors.append(f"{path}: cannot check: {error}")

    for message in errors:
        print(f"error: {message}", file=sys.stderr)
    if errors:
        print(
            "Comments and docstrings tell why the code is as it is. Put issue ids"
            " and review history in the commit message or the PR.",
            file=sys.stderr,
        )
        return 1
    print(f"checked {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
