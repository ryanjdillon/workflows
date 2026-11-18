#!/usr/bin/env python3
"""Check that commit subjects and PR titles follow Conventional Commits 1.0.

A subject has the form `type(scope)!: description`. The scope and the `!` are
optional. The type must be one of the allowed types. One space follows the
colon, and the description is not empty. A body starts after one blank line.
A `BREAKING CHANGE:` or `BREAKING-CHANGE:` footer is allowed.

Types and scopes are lowercase. This is stricter than Conventional Commits
1.0 rule 15, which lets a type have any case. A custom scope pattern sets the
case of the scope.

By default the check rejects merge commits, `fixup!`, `squash!`, and `amend!`
commits, and the revert subject that git writes (`Revert "..."`). Options
allow each of them.

Standalone by design: stdlib only, so the GitHub Action, the prek hook, and
the Nix package in this repo all run this one file. This file is the only
definition of the defaults.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)
SCOPE_PATTERN = r"[a-z0-9._/-]+"
MAX_LENGTH = 72

HEADER_RE = re.compile(
    r"^(?P<type>[^\s():!]+)(?:\((?P<scope>[^()]*)\))?(?P<bang>!)?:(?P<rest>.*)$"
)
MERGE_RE = re.compile(
    r"^Merge (pull request|branch|remote-tracking branch|tag|commit)\b"
)
AUTOSQUASH_RE = re.compile(r"^(fixup|squash|amend)! ")
GIT_REVERT_RE = re.compile(r'^Revert ".*"$')
BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE\b")
BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE: \S")
BREAKING_ANY_CASE_RE = re.compile(r"^breaking[ -]change\b", re.IGNORECASE)
ZERO_SHA_RE = re.compile(r"^0*$")
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
LOWERCASE_NOTE = (
    "types and scopes are lowercase; stricter than Conventional Commits 1.0 rule 15"
)
MERGE_PROBLEM = (
    "is a merge commit; rebase the branch instead of merging into it,"
    " or allow merge commits"
)
AUTOSQUASH_PROBLEM = (
    "is a fixup!, squash!, or amend! commit;"
    " squash it (git rebase -i --autosquash) before the merge"
)
# git puts the diff under this line with `commit --verbose`. The line starts
# with the comment character.
SCISSORS = " ------------------------ >8 ------------------------"


@dataclass(frozen=True)
class Rules:
    types: tuple[str, ...] = TYPES
    scope: re.Pattern[str] = re.compile(SCOPE_PATTERN)
    max_length: int = MAX_LENGTH
    allow_merge_commits: bool = False
    allow_autosquash: bool = False
    allow_git_revert: bool = False


@dataclass(frozen=True)
class Message:
    """A commit message or a PR title to check."""

    name: str
    text: str
    is_merge: bool = False


def comment_char() -> str:
    """Return git's comment character: core.commentChar, or `#`."""
    try:
        value = subprocess.run(
            ["git", "config", "core.commentChar"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError:
        return "#"
    # With `auto`, git picks a character that the message does not use. The
    # hook cannot know it, so it uses the default.
    return value if value and value != "auto" else "#"


def strip_comments(text: str, comment: str = "#") -> str:
    """Remove the lines that git removes from a message in a commit-msg hook."""
    text = text.split(comment + SCISSORS, 1)[0]
    lines = [line for line in text.splitlines() if not line.startswith(comment)]
    return "\n".join(lines).strip("\n")


def check_subject(subject: str, rules: Rules) -> list[str]:
    """Return the problems of one subject line. Empty means it is valid."""
    if not subject.strip():
        return ["the subject is empty"]
    if MERGE_RE.match(subject):
        if rules.allow_merge_commits:
            return []
        return [MERGE_PROBLEM]
    if AUTOSQUASH_RE.match(subject):
        if rules.allow_autosquash:
            return []
        return [AUTOSQUASH_PROBLEM]

    errors: list[str] = []
    if rules.max_length and len(subject) > rules.max_length:
        errors.append(f"is {len(subject)} characters; the limit is {rules.max_length}")
    if GIT_REVERT_RE.match(subject):
        if not rules.allow_git_revert:
            errors.append(
                "is the revert subject that git writes;"
                ' write it as "revert: <subject of the reverted commit>"'
            )
        return errors

    header = HEADER_RE.match(subject)
    if not header:
        errors.append(
            "is not in the form 'type(scope)!: description'"
            f" (types: {', '.join(rules.types)})"
        )
        return errors
    kind, scope, rest = header["type"], header["scope"], header["rest"]
    if kind not in rules.types:
        if kind.lower() in rules.types:
            errors.append(f"type {kind!r} must be {kind.lower()!r}; {LOWERCASE_NOTE}")
        else:
            errors.append(f"type {kind!r} is not one of: {', '.join(rules.types)}")
    if scope is not None and not rules.scope.fullmatch(scope):
        if scope != scope.lower() and rules.scope.fullmatch(scope.lower()):
            errors.append(
                f"scope {scope!r} must be {scope.lower()!r}; {LOWERCASE_NOTE}"
            )
        else:
            errors.append(f"scope {scope!r} does not match {rules.scope.pattern!r}")
    if not rest.strip():
        errors.append("has no description after the colon")
    elif not rest.startswith(" ") or rest[1].isspace():
        errors.append("needs exactly one space after the colon")
    return errors


def check_message(message: Message, rules: Rules) -> list[str]:
    """Return the problems of one message, each with its name and subject."""
    lines = message.text.splitlines()
    subject = lines[0] if lines else ""
    where = f"{message.name} ({subject})" if subject else message.name

    if message.is_merge:
        if rules.allow_merge_commits:
            return []
        return [f"{where}: {MERGE_PROBLEM}"]
    problems = check_subject(subject, rules)
    if problems or AUTOSQUASH_RE.match(subject) or MERGE_RE.match(subject):
        return [f"{where}: {problem}" for problem in problems]

    if len(lines) > 1 and lines[1].strip():
        problems.append("needs a blank line between the subject and the body")
    for line in footer_lines(lines):
        if BREAKING_RE.match(line) and not BREAKING_FOOTER_RE.match(line):
            problems.append(
                f"footer {line.strip()!r} must be 'BREAKING CHANGE: <description>'"
            )
    return [f"{where}: {problem}" for problem in problems]


def footer_lines(lines: list[str]) -> list[str]:
    """Return the lines of the last paragraph after the subject: the footers."""
    paragraphs: list[list[str]] = [[]]
    for line in lines[1:]:
        if line.strip():
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])
    return next((paragraph for paragraph in reversed(paragraphs) if paragraph), [])


def message_warnings(message: Message) -> list[str]:
    """Return the problems that do not fail the check."""
    lines = message.text.splitlines()
    subject = lines[0] if lines else ""
    return [
        f"{message.name} ({subject}): footer {line.strip()!r} is not uppercase;"
        " tools read only 'BREAKING CHANGE: <description>'"
        for line in footer_lines(lines)
        if BREAKING_ANY_CASE_RE.match(line) and not BREAKING_RE.match(line)
    ]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def has_commit(revision: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "-q",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        ],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def event_range(event: dict) -> tuple[str | None, str]:
    """Return the revision range of a GitHub event, and a note on the choice.

    A pull request gives base..head, and a merge queue group gives
    base_sha..head_sha. A push gives before..after. A push that makes a
    branch has no "before" commit, and after a force push the "before" commit
    is not in the clone. Then the range is the commits that the default
    branch does not have. When that range is empty, for example after a force
    push to the default branch, it is the pushed commit only. A push that
    deletes a branch gives no range.
    """
    pull_request = event.get("pull_request")
    if pull_request:
        base = sha(pull_request["base"]["sha"])
        head = sha(pull_request["head"]["sha"])
        return f"{base}..{head}", "the pull request"
    merge_group = event.get("merge_group")
    if merge_group:
        base, head = sha(merge_group["base_sha"]), sha(merge_group["head_sha"])
        return f"{base}..{head}", "the merge group"
    if event.get("after") is None:
        raise ValueError("this event gives no commit range; set the range input")
    after = sha(event["after"])
    if ZERO_SHA_RE.match(after):
        return None, "the push deletes a branch"
    before = sha(event.get("before") or "0" * 40)
    if not ZERO_SHA_RE.match(before) and has_commit(before):
        return f"{before}..{after}", "the push"
    if ZERO_SHA_RE.match(before):
        reason = "the push makes a new branch"
    else:
        reason = "the commit before the push is not in the clone"
    default = (event.get("repository") or {}).get("default_branch")
    if (
        default
        and event.get("ref") != f"refs/heads/{default}"
        and has_commit(f"origin/{default}")
    ):
        fallback = f"origin/{default}..{after}"
        if git("rev-list", "--count", "--end-of-options", fallback).strip() != "0":
            return fallback, reason
    return f"{after}^!", reason


def sha(value: object) -> str:
    """Return a commit id from an event, or fail if it is not one."""
    if not isinstance(value, str) or not SHA_RE.match(value):
        raise ValueError(f"the event has {value!r} where a commit id must be")
    return value


def range_messages(revision_range: str) -> list[Message]:
    """Read the commits of a revision range, the oldest first."""
    output = git(
        "log",
        "-z",
        "--reverse",
        "--no-show-signature",
        "--format=%H %P%n%B",
        "--end-of-options",
        revision_range,
    )
    messages: list[Message] = []
    for record in output.split("\0"):
        if not record.strip():
            continue
        ids, _, text = record.partition("\n")
        sha, *parents = ids.split()
        messages.append(Message(sha[:12], text.strip("\n"), len(parents) > 1))
    return messages


def file_messages(paths: list[Path]) -> list[Message]:
    comment = comment_char()
    return [
        Message(str(path), strip_comments(path.read_text(encoding="utf-8"), comment))
        for path in paths
    ]


def split_types(value: str) -> tuple[str, ...]:
    return tuple(kind for kind in re.split(r"[,\s]+", value) if kind)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="commit message files, as git gives to a commit-msg hook",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--range",
        dest="revision_range",
        help="a git revision range, for example BASE..HEAD; checks each commit in it",
    )
    source.add_argument(
        "--github-event",
        type=Path,
        metavar="PATH",
        help="a GitHub event payload ($GITHUB_EVENT_PATH); checks the commits"
        " of the pull request or the push",
    )
    parser.add_argument("--title", help="a PR title to check as a subject")
    parser.add_argument(
        "--types",
        default=",".join(TYPES),
        help="the allowed types, separated by commas or spaces"
        f" (default: {','.join(TYPES)})",
    )
    parser.add_argument(
        "--scope-pattern",
        default=SCOPE_PATTERN,
        help=f"regex that the whole scope must match (default: {SCOPE_PATTERN})",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=MAX_LENGTH,
        help=f"the subject length limit; 0 turns it off (default: {MAX_LENGTH})",
    )
    parser.add_argument(
        "--allow-merge-commits",
        action="store_true",
        help="do not check merge commits",
    )
    parser.add_argument(
        "--allow-autosquash",
        action="store_true",
        help="do not check fixup!, squash!, and amend! commits",
    )
    parser.add_argument(
        "--allow-git-revert",
        action="store_true",
        help='accept the revert subject that git writes: Revert "..."',
    )
    args = parser.parse_args(argv)

    from_git = args.revision_range or args.github_event
    if args.files and from_git:
        parser.error("give commit message files, or a range, but not both")
    if not (args.files or from_git or args.title is not None):
        parser.error("give commit message files, --range, --github-event, or --title")
    types = split_types(args.types)
    if not types:
        parser.error("--types is empty")
    if any(kind != kind.lower() for kind in types):
        parser.error(f"--types: {LOWERCASE_NOTE}")
    if args.max_length < 0:
        parser.error("--max-length must be 0 or more")
    try:
        scope = re.compile(args.scope_pattern)
    except re.error as error:
        parser.error(f"--scope-pattern is not a valid regex: {error}")
    rules = Rules(
        types=types,
        scope=scope,
        max_length=args.max_length,
        allow_merge_commits=args.allow_merge_commits,
        allow_autosquash=args.allow_autosquash,
        allow_git_revert=args.allow_git_revert,
    )

    messages: list[Message] = []
    try:
        revision_range = args.revision_range
        if args.github_event:
            event = json.loads(args.github_event.read_text(encoding="utf-8"))
            revision_range, note = event_range(event)
            if revision_range is None:
                print(f"conventional-commits: {note}; no commits to check")
            else:
                print(f"conventional-commits: {note}; checking {revision_range}")
        if revision_range:
            messages = range_messages(revision_range)
        elif args.files:
            messages = file_messages(args.files)
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
    ) as error:
        detail = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError)
            else error
        )
        print(f"error: cannot read the commits: {detail}", file=sys.stderr)
        return 1
    if args.title is not None:
        messages.append(Message("PR title", args.title.strip()))

    for warning in (w for message in messages for w in message_warnings(message)):
        print(f"warning: {warning}", file=sys.stderr)
    errors = [error for message in messages for error in check_message(message, rules)]
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(
            f"conventional-commits: {len(errors)} problem(s);"
            " see https://www.conventionalcommits.org/en/v1.0.0/",
            file=sys.stderr,
        )
        return 1
    print(f"checked {len(messages)} message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
