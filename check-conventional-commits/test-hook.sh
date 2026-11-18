#!/usr/bin/env bash
# Test the prek hook of check-conventional-commits. Needs prek and git.
#
# The hook runs from this checkout with `prek try-repo`, in the commit-msg
# stage, on each message in testdata/. Each message in pass/ must pass. Each
# message in fail/ must fail with the message that `expected` gives for it.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"
testdata="$here/testdata"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git -C "$scratch" init -q

run_hook() {
  cp "$1" "$scratch/COMMIT_EDITMSG"
  (cd "$scratch" && prek try-repo "$repo" check-conventional-commits \
    --stage commit-msg --commit-msg-filename COMMIT_EDITMSG)
}

declare -A expected=(
  [bad-footer.txt]="must be 'BREAKING CHANGE: <description>'"
  [fixup.txt]="is a fixup!, squash!, or amend! commit"
  [git-revert.txt]="is the revert subject that git writes"
  [merge.txt]="is a merge commit"
  [no-type.txt]="is not in the form 'type(scope)!: description'"
  [too-long.txt]="is 78 characters; the limit is 72"
)

for message in "$testdata"/pass/*; do
  echo "== $message: must pass"
  run_hook "$message"
done

for message in "$testdata"/fail/*; do
  name="$(basename "$message")"
  want="${expected[$name]:-}"
  if [ -z "$want" ]; then
    echo "error: no expected message for $name; add it to expected" >&2
    exit 1
  fi
  echo "== $message: must fail with: $want"
  if output="$(run_hook "$message" 2>&1)"; then
    echo "$output"
    echo "error: the hook passed on $message" >&2
    exit 1
  fi
  echo "$output"
  if ! grep -qF -- "$want" <<<"$output"; then
    echo "error: the hook failed on $message without: $want" >&2
    exit 1
  fi
  echo "ok: the hook failed as expected"
done
