#!/usr/bin/env bash
# Test the prek hook of check-skills. Needs prek and git.
#
# The hook runs from this checkout with `prek try-repo`, on a scratch repo
# with its skills in the default root, `skills`:
#   1. A valid skill. The hook must pass.
#   2. A skill with an invalid name. The hook must fail.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
testdata="$here/testdata"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git -C "$scratch" init -q
cp -r "$testdata/pass/skills" "$scratch/skills"
git -C "$scratch" add skills

run_hook() {
  (cd "$scratch" && prek try-repo "$repo" check-skills --all-files)
}

echo "== a valid skill: must pass"
run_hook

echo "== a skill with an invalid name: must fail"
cp -r "$testdata/fail/skills/bad-name" "$scratch/skills/"
git -C "$scratch" add skills
if run_hook; then
  echo "error: the hook passed on $testdata/fail/skills/bad-name" >&2
  exit 1
fi
echo "ok: the hook failed as expected"
