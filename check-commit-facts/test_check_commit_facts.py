"""Tests for check-commit-facts.py. Run: python3 -m unittest discover -s check-commit-facts"""

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
SCRIPT = HERE / "check-commit-facts.py"

spec = importlib.util.spec_from_file_location("check_commit_facts", SCRIPT)
facts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = facts
spec.loader.exec_module(facts)

PARTS = [re.compile(source) for source in facts.PART_PATTERNS]
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def errors(text: str, patterns=PARTS) -> list[str]:
    return facts.check_message(facts.Message("msg", text), patterns)


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class CheckMessageTest(unittest.TestCase):
    def test_part_with_no_source_fails(self) -> None:
        self.assertEqual(len(errors("Use C0000 for R1\n")), 1)

    def test_part_with_source_passes(self) -> None:
        self.assertEqual(errors("Use C0000 for R1\n\nSource: datasheet p. 3\n"), [])

    def test_source_must_start_a_line_and_have_a_value(self) -> None:
        self.assertEqual(len(errors("Use C0000. See Source: x\n")), 1)
        self.assertEqual(len(errors("Use C0000\n\nSource:\n")), 1)

    def test_short_and_embedded_numbers_pass(self) -> None:
        self.assertEqual(errors("Add C12 and AC1000 to the board\n"), [])

    def test_from_memory_fails_with_a_source(self) -> None:
        self.assertEqual(len(errors("Set R1\n\nSource: From memory\n")), 1)

    def test_patterns_replace_the_default(self) -> None:
        patterns = [re.compile(r"\bLM\d{3}\b")]
        self.assertEqual(len(errors("Use LM317\n", patterns)), 1)
        self.assertEqual(errors("Use C0000\n", patterns), [])

    def test_strip_comments_removes_git_lines(self) -> None:
        text = f"Subject\n# C0000 in a comment\n{facts.SCISSORS}\n+C1111\n"
        self.assertEqual(facts.strip_comments(text), "Subject")


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.tmp,
            env=GIT_ENV,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, message: str) -> str:
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_testdata(self) -> None:
        passing = sorted(str(path) for path in (HERE / "testdata/pass").iterdir())
        self.assertEqual(run(HERE, *passing).returncode, 0)
        for path in (HERE / "testdata/fail").iterdir():
            with self.subTest(path=path.name):
                self.assertEqual(run(HERE, str(path)).returncode, 1)

    def test_range_checks_each_commit(self) -> None:
        self.git("init", "-q")
        base = self.commit("Start")
        self.commit("Use C0000 for R1\n\nSource: datasheet")
        self.commit("Use C1111 for R2")
        result = run(self.tmp, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("C1111", result.stderr)
        self.assertNotIn("C0000", result.stderr)

    def test_range_with_good_commits_passes(self) -> None:
        self.git("init", "-q")
        base = self.commit("Use C1111 for R2")
        self.commit("Add a test")
        result = run(self.tmp, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked 1 commit message", result.stdout)

    def test_files_and_range_together_is_an_error(self) -> None:
        result = run(self.tmp, "--range", "a..b", "msg.txt")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
