#!/usr/bin/env bash
# Test the prek hook of check-process-noise. Needs prek and git.
#
# The hook runs from this checkout with `prek try-repo`, on a scratch repo:
#   1. A Python file with clean comments. The hook must pass.
#   2. A Python file with an issue id in a comment. The hook must fail.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
testdata="$here/testdata"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git -C "$scratch" init -q
cp "$testdata/pass/clean.py" "$scratch/"
git -C "$scratch" add clean.py

run_hook() {
  (cd "$scratch" && prek try-repo "$repo" check-process-noise --all-files)
}

echo "== clean comments: must pass"
run_hook

echo "== an issue id in a comment: must fail"
cp "$testdata/fail/noisy.py" "$scratch/"
git -C "$scratch" add noisy.py
if run_hook; then
  echo "error: the hook passed on $testdata/fail/noisy.py" >&2
  exit 1
fi
echo "ok: the hook failed as expected"
