# workflows

This repo holds reusable GitHub Actions workflows, and the shared checks that
many repos use. Each shared check has one script, and an adapter for each
environment: a composite action, a prek hook, and the Nix flake. The README
tells callers how to use them.

## Linear

- Team: `software` (issue prefix `DIL`)
- Project: Shared CI and dependency updates

## Common commands

```bash
python3 -m unittest discover -s <check>   # unit tests of a check
<check>/test-hook.sh                      # test the prek hook (needs prek)
nix flake check                           # test the Nix adapter
nix fmt
```

`prek try-repo` copies only the tracked files. Stage a new file before you
run `test-hook.sh`.

CI (`.github/workflows/check.yml`) also tests the action, and runs
actionlint, zizmor, and ruff. `nix.yml` tests the reusable Nix workflows.

## Invariants

- This repo is public. Do not add secrets, internal host names, or details
  of private infrastructure.
- A shared check has one script. An adapter calls the script; it does not
  copy its logic.
- The scripts use only bash or the Python standard library.
- Callers pin this repo by commit SHA. A change to an input, an output, or a
  hook `id` breaks callers. Make it only in a new major version.
- Pin each third-party action by commit SHA, with the version in a comment.
  Take a release only after it is 7 days old.

## Drift discipline

| When you change | Also update |
| --- | --- |
| A check's script or its limits | Its test data in `<check>/testdata/`, and its unit tests |
| A check's inputs or default files | The action, the hook, the flake, and the README, together |
| A workflow's inputs or outputs | The README section of that workflow |
| A workflow or an action | Run actionlint and zizmor |

# SYSTEM.md

<!-- Rules for all repos, not only this repo. A periodic process moves them to
     SYSTEM.md in ryanjdillon/agents. Keep this heading. See docs/promotion.md
     in that repo. -->
