"""Tests for check-skills.py. Run: python3 -m unittest discover -s check-skills"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check-skills.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def skill(root: Path, directory: str, frontmatter: str) -> None:
    path = root / directory / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\n{frontmatter}---\n\n# Title\n", encoding="utf-8")


class CheckSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_testdata(self) -> None:
        self.assertEqual(run(str(HERE / "testdata/pass/skills")).returncode, 0)
        result = run(str(HERE / "testdata/fail/skills"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad-name", result.stderr)
        self.assertIn("allowed-tools", result.stderr)

    def test_name_must_match_directory(self) -> None:
        skill(self.tmp, "one", "name: two\ndescription: Text.\n")
        self.assertIn("does not match directory", run(str(self.tmp)).stderr)

    def test_value_with_colon_space_fails(self) -> None:
        skill(self.tmp, "one", "name: one\ndescription: Use when: always.\n")
        self.assertIn("': '", run(str(self.tmp)).stderr)

    def test_duplicate_names_across_roots_fail(self) -> None:
        skill(self.tmp / "a", "one", "name: one\ndescription: Text.\n")
        skill(self.tmp / "b", "one", "name: one\ndescription: Text.\n")
        result = run(str(self.tmp / "a"), str(self.tmp / "b"))
        self.assertIn("duplicate skill name", result.stderr)

    def test_symlink_out_of_the_skill_fails(self) -> None:
        skill(self.tmp, "one", "name: one\ndescription: Text.\n")
        (self.tmp / "one" / "link").symlink_to("../..")
        self.assertIn("escapes skill directory", run(str(self.tmp)).stderr)

    def test_missing_root_fails(self) -> None:
        self.assertEqual(run(str(self.tmp / "none")).returncode, 1)


if __name__ == "__main__":
    unittest.main()
