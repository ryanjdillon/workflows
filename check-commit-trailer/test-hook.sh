#!/usr/bin/env bash
# Test the prek hook of check-commit-trailer. Needs prek and git.
#
# The hook runs from this checkout with `prek try-repo`, in the commit-msg
# stage, on each message in testdata/. Each message in pass/ must pass, and
# each message in fail/ must fail. The hook reads the author of the commit
# from git, so this script sets it.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
testdata="$here/testdata"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git -C "$scratch" init -q
export GIT_AUTHOR_NAME="an agent" GIT_AUTHOR_EMAIL="agent@example.com"

run_hook() {
  cp "$1" "$scratch/COMMIT_EDITMSG"
  (cd "$scratch" && prek try-repo "$repo" check-commit-trailer \
    --stage commit-msg --commit-msg-filename COMMIT_EDITMSG)
}

for message in "$testdata"/pass/*; do
  echo "== $message: must pass"
  run_hook "$message"
done

for message in "$testdata"/fail/*; do
  echo "== $message: must fail"
  if run_hook "$message"; then
    echo "error: the hook passed on $message" >&2
    exit 1
  fi
  echo "ok: the hook failed as expected"
done
