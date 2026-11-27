"""Tests for check-commit-trailer.py. Run: python3 -m unittest discover -s check-commit-trailer"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check-commit-trailer.py"

spec = importlib.util.spec_from_file_location("check_commit_trailer", SCRIPT)
trailer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trailer
spec.loader.exec_module(trailer)

VALUE = re.compile(trailer.VALUE_PATTERN)
AGENT = "an agent"
OWNER = "The Owner"
BOT = "renovate[bot]"


def git_env(author: str = AGENT) -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": "author@example.com",
        "GIT_COMMITTER_NAME": "committer",
        "GIT_COMMITTER_EMAIL": "committer@example.com",
    }


def errors(text: str, author: str = AGENT, exempt=frozenset()) -> list[str]:
    message = trailer.Message("msg", author, text)
    return trailer.check_message(message, trailer.KEY, VALUE, exempt)


def run(cwd: Path, *args: str, author: str = AGENT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        env=git_env(author),
        capture_output=True,
        text=True,
    )


class CheckMessageTest(unittest.TestCase):
    def test_trailer_passes(self) -> None:
        self.assertEqual(errors("feat: x\n\nWhy.\n\nPaperclip: PCL-97\n"), [])

    def test_no_trailer_fails(self) -> None:
        self.assertEqual(len(errors("feat: x\n\nWhy.\n")), 1)

    def test_issue_id_in_the_body_is_not_a_trailer(self) -> None:
        self.assertEqual(len(errors("feat: x\n\nRefs PCL-97\n")), 1)

    def test_trailer_must_be_in_the_last_paragraph(self) -> None:
        self.assertEqual(len(errors("feat: x\n\nPaperclip: PCL-97\n\nWhy.\n")), 1)

    def test_subject_only_is_not_a_trailer(self) -> None:
        self.assertEqual(len(errors("Paperclip: PCL-97\n")), 1)

    def test_value_must_match_the_whole_pattern(self) -> None:
        for value in ("PCL-", "PCL-0", "PCL-12x", "DIL-12", "pcl-12"):
            with self.subTest(value=value):
                self.assertEqual(len(errors(f"feat: x\n\nPaperclip: {value}\n")), 1)

    def test_key_is_case_insensitive_as_in_git(self) -> None:
        self.assertEqual(errors("feat: x\n\npaperclip: PCL-3\n"), [])

    def test_other_trailers_in_the_block_pass(self) -> None:
        text = "feat: x\n\nSigned-off-by: A <a@example.com>\nPaperclip: PCL-3\n"
        self.assertEqual(errors(text), [])

    def test_exempt_author_needs_no_trailer(self) -> None:
        exempt = frozenset({OWNER, BOT})
        self.assertEqual(errors("feat: x\n", author=OWNER, exempt=exempt), [])
        self.assertEqual(errors("chore: y\n", author=BOT, exempt=exempt), [])
        self.assertEqual(len(errors("feat: x\n", exempt=exempt)), 1)

    def test_strip_comments_removes_git_lines(self) -> None:
        text = f"feat: x\n# Paperclip: PCL-1\n{trailer.SCISSORS}\n+diff\n"
        self.assertEqual(trailer.strip_comments(text), "feat: x")


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, author: str = AGENT) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.tmp,
            env=git_env(author),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, message: str, author: str = AGENT) -> str:
        self.git("commit", "-q", "--allow-empty", "-m", message, author=author)
        return self.git("rev-parse", "HEAD")

    def test_testdata(self) -> None:
        passing = sorted(str(path) for path in (HERE / "testdata/pass").iterdir())
        result = run(self.tmp, *passing)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (HERE / "testdata/fail").iterdir():
            with self.subTest(path=path.name):
                self.assertEqual(run(self.tmp, str(path)).returncode, 1)

    def test_commit_with_the_trailer_passes(self) -> None:
        base = self.commit("Start", author=OWNER)
        self.commit("feat: add a part\n\nPaperclip: PCL-97")
        result = run(self.tmp, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked 1 commit message", result.stdout)

    def test_commit_with_no_trailer_fails(self) -> None:
        base = self.commit("Start", author=OWNER)
        self.commit("feat: add a part\n\nPaperclip: PCL-97")
        self.commit("fix: correct the part")
        result = run(self.tmp, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("fix: correct the part", result.stderr)
        self.assertNotIn("add a part", result.stderr)

    def test_range_skips_exempt_authors_and_merges(self) -> None:
        base = self.commit("Start", author=OWNER)
        self.git("switch", "-q", "-c", "topic")
        self.commit("feat: add a part\n\nPaperclip: PCL-97")
        self.git("switch", "-q", "main")
        self.commit("docs: owner note", author=OWNER)
        self.commit("chore(deps): bump", author=BOT)
        self.git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic")
        args = ["--range", f"{base}..HEAD"]
        exempt = ["--exempt-author", OWNER, "--exempt-author", BOT]
        self.assertEqual(run(self.tmp, *args).returncode, 1)
        result = run(self.tmp, *args, *exempt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "checked 1 commit message(s); 2 by an exempt author", result.stdout
        )

    def test_hook_mode_skips_an_exempt_author(self) -> None:
        path = str(HERE / "testdata/fail/no-trailer.txt")
        self.assertEqual(run(self.tmp, path, author=OWNER).returncode, 1)
        result = run(self.tmp, "--exempt-author", OWNER, path, author=OWNER)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_key_and_value_pattern_are_inputs(self) -> None:
        base = self.commit("Start")
        self.commit("feat: x\n\nRefs: ABC-1")
        args = ["--range", f"{base}..HEAD"]
        self.assertEqual(run(self.tmp, *args).returncode, 1)
        custom = ["--key", "Refs", "--value-pattern", r"ABC-\d+"]
        result = run(self.tmp, *args, *custom)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bad_key_is_an_error(self) -> None:
        result = run(self.tmp, "--key", "Not a key", "--range", "a..b")
        self.assertEqual(result.returncode, 2)

    def test_files_and_range_together_is_an_error(self) -> None:
        result = run(self.tmp, "--range", "a..b", "msg.txt")
        self.assertEqual(result.returncode, 2)

    def test_bad_range_is_an_error(self) -> None:
        result = run(self.tmp, "--range", "nothere..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read", result.stderr)


if __name__ == "__main__":
    unittest.main()
