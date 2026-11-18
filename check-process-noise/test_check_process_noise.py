"""Tests for check-process-noise.py. Run: python3 -m unittest discover -s check-process-noise"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check-process-noise.py"

spec = importlib.util.spec_from_file_location("check_process_noise", SCRIPT)
noise = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = noise
spec.loader.exec_module(noise)

DEFAULTS = noise.compile_patterns(noise.ISSUE_PATTERN, list(noise.REVIEW_PATTERNS))


def write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class CheckFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def words(self, name: str, text: str, patterns=DEFAULTS) -> list[tuple[int, str]]:
        path = write(self.tmp, name, text)
        return [(match.line, match.word) for match in noise.check_file(path, patterns)]

    def test_python_comment_and_docstring_match(self) -> None:
        source = (
            '"""Module text."""\n'
            "\n"
            "class Board:\n"
            '    """Line one.\n'
            "\n"
            '    The Reviewer asked for this."""\n'
            "\n"
            "    def pin(self):  # see DIL-00\n"
            "        return 1\n"
        )
        self.assertEqual(
            self.words("board.py", source), [(6, "Reviewer"), (8, "DIL-00")]
        )

    def test_python_strings_do_not_match(self) -> None:
        source = 'LABEL = "blocker DIL-0"\nx = f"finding {1}"\n'
        self.assertEqual(self.words("labels.py", source), [])

    def test_each_default_word_matches(self) -> None:
        source = "".join(
            f"# {word}\n"
            for word in (
                "blocker",
                "should-fix",
                "finding 2",
                "re-review",
                "hand-back",
                "handback",
                "reviewers",
                "reviewer's",
            )
        )
        self.assertEqual(len(self.words("words.py", source)), 8)

    def test_words_inside_other_words_do_not_match(self) -> None:
        source = "# unblocker, findings, preview, handbook, CANDIL-3\n"
        self.assertEqual(self.words("words.py", source), [])

    def test_shell_reads_only_whole_line_comments(self) -> None:
        source = '# DIL-0\necho "# blocker"\n'
        self.assertEqual(self.words("run.sh", source), [(1, "DIL-0")])

    def test_makefile_is_known(self) -> None:
        self.assertEqual(self.words("Makefile", "# blocker\n"), [(1, "blocker")])

    def test_unknown_file_type_is_an_error(self) -> None:
        path = write(self.tmp, "notes.txt", "blocker\n")
        with self.assertRaises(noise.UnknownSyntax):
            noise.check_file(path, DEFAULTS)

    def test_patterns_replace_the_defaults(self) -> None:
        patterns = noise.compile_patterns("", [r"\btodo\b"])
        source = "# TODO: DIL-0 blocker\n"
        self.assertEqual(self.words("a.py", source, patterns), [(1, "TODO")])

    def test_issue_pattern_is_an_input(self) -> None:
        patterns = noise.compile_patterns(r"\bABC-\d+\b", [])
        source = "# ABC-7 and DIL-0\n"
        self.assertEqual(self.words("a.py", source, patterns), [(1, "ABC-7")])


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)

    def test_testdata(self) -> None:
        self.assertEqual(run(HERE, "testdata/pass/clean.py").returncode, 0)
        result = run(HERE, "testdata/fail/noisy.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("noisy.py:5: 'reviewer'", result.stderr)
        self.assertIn("noisy.py:6: 'DIL-0'", result.stderr)

    def test_no_files_checks_tracked_python(self) -> None:
        write(self.tmp, "src/a.py", "# blocker\n")
        write(self.tmp, "untracked.py", "# blocker\n")
        write(self.tmp, "run.sh", "# blocker\n")
        subprocess.run(["git", "add", "src/a.py", "run.sh"], cwd=self.tmp, check=True)
        result = run(self.tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/a.py:1", result.stderr)
        self.assertNotIn("untracked.py", result.stderr)
        self.assertNotIn("run.sh", result.stderr)

    def test_glob_and_exclude(self) -> None:
        write(self.tmp, "run.sh", "# blocker\n")
        write(self.tmp, "testdata/bad.sh", "# blocker\n")
        subprocess.run(
            ["git", "add", "run.sh", "testdata/bad.sh"], cwd=self.tmp, check=True
        )
        result = run(self.tmp, "--glob", "*.sh", "--exclude", "testdata/*")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run.sh:1", result.stderr)
        self.assertNotIn("testdata", result.stderr)

    def test_syntax_error_fails(self) -> None:
        path = write(self.tmp, "broken.py", "def (:\n")
        result = run(self.tmp, str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot check", result.stderr)


if __name__ == "__main__":
    unittest.main()
