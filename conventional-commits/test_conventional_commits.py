"""Tests for conventional-commits.py. Run: python3 -m unittest discover -s conventional-commits"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "conventional-commits.py"

spec = importlib.util.spec_from_file_location("conventional_commits", SCRIPT)
cc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cc
spec.loader.exec_module(cc)

RULES = cc.Rules()
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
ZERO = "0" * 40


def errors(text: str, rules=RULES, is_merge: bool = False) -> list[str]:
    return cc.check_message(cc.Message("msg", text, is_merge), rules)


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=cwd,
        env=GIT_ENV,
        capture_output=True,
        text=True,
    )


class SubjectTest(unittest.TestCase):
    def test_valid_subjects(self) -> None:
        for subject in (
            "feat: add a check",
            "fix(parser): accept a byte order mark",
            "docs(readme.md): describe the hook",
            "ci(workflows/check): pin the action",
            "refactor!: drop the old input",
            "feat(api)!: remove the v1 endpoints",
            "revert: feat: add a check",
        ):
            with self.subTest(subject=subject):
                self.assertEqual(cc.check_subject(subject, RULES), [])

    def test_invalid_subjects(self) -> None:
        for subject, expected in (
            ("Add a check", "not in the form"),
            ("feat add a check", "not in the form"),
            ("Feat: add a check", "type 'Feat'"),
            ("feature: add a check", "type 'feature'"),
            ("feat:add a check", "one space"),
            ("feat:  add a check", "one space"),
            ("feat: ", "no description"),
            ("feat:", "no description"),
            ("feat(): add a check", "scope ''"),
            ("feat(API): add a check", "scope 'API'"),
            ("feat(a b): add a check", "scope 'a b'"),
            ("feat!(api): add a check", "not in the form"),
            ("", "empty"),
        ):
            with self.subTest(subject=subject):
                problems = cc.check_subject(subject, RULES)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(expected, problems[0])

    def test_types_are_configurable(self) -> None:
        rules = cc.Rules(types=("feat", "deps"))
        self.assertEqual(cc.check_subject("deps: update the lock file", rules), [])
        self.assertEqual(len(cc.check_subject("fix: a bug", rules)), 1)

    def test_scope_pattern_is_configurable(self) -> None:
        rules = cc.Rules(scope=re.compile(r"[A-Z]+-\d+"))
        self.assertEqual(cc.check_subject("fix(ABC-12): a bug", rules), [])
        self.assertEqual(len(cc.check_subject("fix(parser): a bug", rules)), 1)

    def test_max_length(self) -> None:
        self.assertEqual(cc.check_subject("feat: " + "a" * 66, RULES), [])
        problems = cc.check_subject("feat: " + "a" * 67, RULES)
        self.assertEqual(len(problems), 1)
        self.assertIn("73 characters", problems[0])
        self.assertEqual(
            cc.check_subject("feat: " + "a" * 67, cc.Rules(max_length=0)), []
        )

    def test_merge_subjects(self) -> None:
        for subject in (
            "Merge pull request #1 from someone/branch",
            "Merge branch 'main' into feat/x",
            "Merge remote-tracking branch 'origin/main'",
        ):
            with self.subTest(subject=subject):
                problems = cc.check_subject(subject, RULES)
                self.assertEqual(len(problems), 1)
                self.assertIn("merge commit", problems[0])
                allow = cc.Rules(allow_merge_commits=True)
                self.assertEqual(cc.check_subject(subject, allow), [])

    def test_autosquash_subjects(self) -> None:
        for subject in ("fixup! feat: x", "squash! feat: x", "amend! feat: x"):
            with self.subTest(subject=subject):
                problems = cc.check_subject(subject, RULES)
                self.assertEqual(len(problems), 1)
                self.assertIn("squash it", problems[0])
                allow = cc.Rules(allow_autosquash=True)
                self.assertEqual(cc.check_subject(subject, allow), [])

    def test_git_revert_subject(self) -> None:
        subject = 'Revert "feat: add a check"'
        problems = cc.check_subject(subject, RULES)
        self.assertEqual(len(problems), 1)
        self.assertIn("revert: ", problems[0])
        self.assertEqual(cc.check_subject(subject, cc.Rules(allow_git_revert=True)), [])


class MessageTest(unittest.TestCase):
    def test_body_needs_a_blank_line(self) -> None:
        self.assertEqual(errors("feat: x\n\nThe body.\n"), [])
        self.assertIn("blank line", errors("feat: x\nThe body.\n")[0])

    def test_breaking_footer(self) -> None:
        self.assertEqual(errors("feat: x\n\nBREAKING CHANGE: the input is gone\n"), [])
        self.assertEqual(errors("feat: x\n\nBREAKING-CHANGE: the input is gone\n"), [])
        self.assertEqual(len(errors("feat: x\n\nBREAKING CHANGE the input\n")), 1)
        self.assertEqual(len(errors("feat: x\n\nBREAKING CHANGE:\n")), 1)

    def test_error_names_the_commit_and_subject(self) -> None:
        problem = cc.check_message(cc.Message("0123abcd", "Add x"), RULES)[0]
        self.assertTrue(problem.startswith("0123abcd (Add x): "), problem)

    def test_merge_by_parents(self) -> None:
        self.assertEqual(len(errors("feat: x", is_merge=True)), 1)
        allow = cc.Rules(allow_merge_commits=True)
        self.assertEqual(errors("anything", allow, is_merge=True), [])

    def test_strip_comments(self) -> None:
        text = f"\nfeat: x\n# a comment\n{cc.SCISSORS}\n+diff\n"
        self.assertEqual(cc.strip_comments(text), "feat: x")


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.tmp,
            env=GIT_ENV,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, message: str) -> str:
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def init(self) -> None:
        self.git("init", "-q", "-b", "main")

    def event(self, payload: dict) -> str:
        path = self.tmp / "event.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_testdata(self) -> None:
        passing = sorted(str(path) for path in (HERE / "testdata/pass").iterdir())
        result = run(HERE, *passing)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (HERE / "testdata/fail").iterdir():
            with self.subTest(path=path.name):
                self.assertEqual(run(HERE, str(path)).returncode, 1)

    def test_range_checks_each_commit(self) -> None:
        self.init()
        base = self.commit("Start")
        good = self.commit("feat: add x")
        bad = self.commit("Add y")
        result = run(self.tmp, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{bad[:12]} (Add y)", result.stderr)
        self.assertNotIn(good[:12], result.stderr)
        self.assertNotIn("Start", result.stderr)

    def test_range_rejects_a_merge_commit(self) -> None:
        self.init()
        base = self.commit("chore: start")
        self.git("switch", "-q", "-c", "side")
        self.commit("feat: on the side")
        self.git("switch", "-q", "main")
        self.commit("fix: on main")
        self.git("merge", "-q", "--no-ff", "-m", "feat: merge the side", "side")
        result = run(self.tmp, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("merge commit", result.stderr)
        result = run(self.tmp, "--range", f"{base}..HEAD", "--allow-merge-commits")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked 3 message", result.stdout)

    def test_empty_range_passes(self) -> None:
        self.init()
        self.commit("Start")
        result = run(self.tmp, "--range", "HEAD..HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked 0 message", result.stdout)

    def test_bad_range_is_an_error(self) -> None:
        self.init()
        self.commit("feat: start")
        result = run(self.tmp, "--range", "nothing..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the commits", result.stderr)

    def test_title(self) -> None:
        self.assertEqual(run(self.tmp, "--title", "feat: add x").returncode, 0)
        result = run(self.tmp, "--title", "Add x")
        self.assertEqual(result.returncode, 1)
        self.assertIn("PR title (Add x)", result.stderr)

    def test_title_with_range(self) -> None:
        self.init()
        base = self.commit("chore: start")
        self.commit("feat: add x")
        result = run(self.tmp, "--range", f"{base}..HEAD", "--title", "Add x")
        self.assertEqual(result.returncode, 1)
        self.assertIn("PR title", result.stderr)
        self.assertIn(
            "checked",
            run(self.tmp, "--range", f"{base}..HEAD", "--title", "feat: add x").stdout,
        )

    def test_event_pull_request(self) -> None:
        self.init()
        base = self.commit("chore: start")
        self.commit("Add x")
        head = self.commit("feat: add y")
        event = self.event(
            {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
        )
        result = run(self.tmp, "--github-event", event)
        self.assertEqual(result.returncode, 1)
        self.assertIn("(Add x)", result.stderr)
        self.assertNotIn("start", result.stderr)

    def test_event_push(self) -> None:
        self.init()
        self.commit("Start")
        before = self.commit("chore: before")
        after = self.commit("feat: after")
        event = self.event({"before": before, "after": after})
        result = run(self.tmp, "--github-event", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"checking {before}..{after}", result.stdout)
        self.assertIn("checked 1 message", result.stdout)

    def test_event_new_branch_uses_the_default_branch(self) -> None:
        remote = self.tmp / "remote"
        remote.mkdir()
        self.git("init", "-q", "-b", "main", cwd=remote)
        self.git("commit", "-q", "--allow-empty", "-m", "Old history", cwd=remote)
        clone = self.tmp / "clone"
        self.git("clone", "-q", str(remote), str(clone))
        self.git("switch", "-q", "-c", "feat/x", cwd=clone)
        self.git("commit", "-q", "--allow-empty", "-m", "feat: new", cwd=clone)
        after = self.git("rev-parse", "HEAD", cwd=clone)
        payload = {
            "before": ZERO,
            "after": after,
            "repository": {"default_branch": "main"},
        }
        event = self.event(payload)
        result = run(clone, "--github-event", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("makes a new branch", result.stdout)
        self.assertIn(f"checking origin/main..{after}", result.stdout)
        self.assertIn("checked 1 message", result.stdout)

    def test_event_force_push_with_no_default_branch_checks_one_commit(self) -> None:
        self.init()
        self.commit("Old history")
        after = self.commit("feat: new")
        gone = "1" * 40
        event = self.event({"before": gone, "after": after})
        result = run(self.tmp, "--github-event", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not in the clone", result.stdout)
        self.assertIn(f"checking {after}^!", result.stdout)
        self.assertIn("checked 1 message", result.stdout)

    def test_event_branch_delete_checks_nothing(self) -> None:
        event = self.event({"before": "1" * 40, "after": ZERO})
        result = run(self.tmp, "--github-event", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deletes a branch", result.stdout)

    def test_event_merge_group(self) -> None:
        self.init()
        base = self.commit("Start")
        head = self.commit("feat: queued")
        event = self.event({"merge_group": {"base_sha": base, "head_sha": head}})
        result = run(self.tmp, "--github-event", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked 1 message", result.stdout)

    def test_event_with_no_range_is_an_error(self) -> None:
        event = self.event({"inputs": {}})
        result = run(self.tmp, "--github-event", event)
        self.assertEqual(result.returncode, 1)
        self.assertIn("set the range input", result.stderr)

    def test_usage_errors(self) -> None:
        for args in (
            (),
            ("--range", "a..b", "msg.txt"),
            ("--range", "a..b", "--github-event", "e.json"),
            ("--title", "feat: x", "--types", ","),
            ("--title", "feat: x", "--scope-pattern", "("),
            ("--title", "feat: x", "--max-length", "-1"),
        ):
            with self.subTest(args=args):
                self.assertEqual(run(self.tmp, *args).returncode, 2)

    def test_options_reach_the_rules(self) -> None:
        path = HERE / "testdata/fail"
        for name, option in (
            ("merge.txt", "--allow-merge-commits"),
            ("fixup.txt", "--allow-autosquash"),
            ("git-revert.txt", "--allow-git-revert"),
        ):
            with self.subTest(option=option):
                result = run(self.tmp, option, str(path / name))
                self.assertEqual(result.returncode, 0, result.stderr)
        result = run(self.tmp, "--max-length", "100", str(path / "too-long.txt"))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run(
            self.tmp,
            "--types",
            "feat docs",
            str(path / "too-long.txt"),
            "--max-length",
            "0",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
