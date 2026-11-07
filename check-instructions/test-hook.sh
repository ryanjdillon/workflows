#!/usr/bin/env bash
# Test the prek hook of check-instructions. Needs prek and git.
#
# The hook runs from this checkout with `prek try-repo`, on a scratch repo:
#   1. A good root AGENTS.md and SYSTEM.md, and a vendored AGENTS.md with no
#      `# SYSTEM.md` section. The hook must pass: it skips nested files.
#   2. A root AGENTS.md with no `# SYSTEM.md` section. The hook must fail.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
testdata="$here/testdata"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git -C "$scratch" init -q
mkdir -p "$scratch/vendor/dep"
cp "$testdata/pass/AGENTS.md" "$testdata/pass/SYSTEM.md" "$scratch/"
cp "$testdata/fail/AGENTS.md" "$scratch/vendor/dep/AGENTS.md"
git -C "$scratch" add -A

run_hook() {
  (cd "$scratch" && prek try-repo "$repo" check-instructions --all-files)
}

echo "== good root files, vendored file skipped: must pass"
run_hook

echo "== root AGENTS.md with no SYSTEM.md section: must fail"
cp "$testdata/fail/AGENTS.md" "$scratch/AGENTS.md"
git -C "$scratch" add -A
if run_hook; then
  echo "error: the hook passed on $testdata/fail/AGENTS.md" >&2
  exit 1
fi
echo "ok: the hook failed as expected"
