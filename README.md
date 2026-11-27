# workflows

Reusable GitHub Actions workflows and composite actions, shared across my
repositories.

**This repository is public and must stay free of anything private** — no
secrets, no internal hostnames, no infrastructure detail. Callers pass what a
workflow needs as inputs; secrets stay in the calling repository.

Being public also removes a constraint: a private reusable workflow is only
callable after enabling *Settings → Actions → General → Access → accessible from
repositories owned by the user*. A public one is callable from anywhere,
including private repositories, with no extra configuration.

## Available workflows

| Workflow | Purpose |
|---|---|
| [`docker-build-push.yml`](.github/workflows/docker-build-push.yml) | Build a Dockerfile and push it to GHCR using the automatic `GITHUB_TOKEN` |
| [`nix-check.yml`](.github/workflows/nix-check.yml) | Run `nix flake check`; callers start it only for changes to Nix files |
| [`nix-devshell-check.yml`](.github/workflows/nix-devshell-check.yml) | Run a check command in the caller's flake devshell, for a toolchain that exists only in Nix |
| [`security-scan.yml`](.github/workflows/security-scan.yml) | Find secrets with Betterleaks and run Semgrep CE static analysis, in one job |

## Shared checks

A shared check has one definition, in its own directory, and an adapter for
each environment. Each adapter runs the same file, so a local run and CI give
the same result.

| Check | GitHub Actions | prek (or pre-commit) | Nix |
|---|---|---|---|
| [`check-instructions`](check-instructions/) | Composite action | `.pre-commit-hooks.yaml` | `packages`, `lib.checkInstructions` |
| [`check-process-noise`](check-process-noise/) | Composite action | `.pre-commit-hooks.yaml` | `packages`, `lib.checkProcessNoise` |
| [`check-commit-facts`](check-commit-facts/) | Composite action | `.pre-commit-hooks.yaml` (`commit-msg`) | `packages`, `lib.checkCommitFacts` |
| [`check-skills`](check-skills/) | Composite action | `.pre-commit-hooks.yaml` | `packages`, `lib.checkSkills` |
| [`check-conventional-commits`](check-conventional-commits/) | Composite action | `.pre-commit-hooks.yaml` (`commit-msg`) | `packages`, `lib.checkConventionalCommits` |

### `docker-build-push.yml`

```yaml
permissions:
  contents: read
  packages: write

jobs:
  image:
    uses: ryanjdillon/workflows/.github/workflows/docker-build-push.yml@<sha> # v1.0.0
    with:
      image: ryanjdillon/my-image
```

Inputs: `image` (required), `registry`, `context`, `dockerfile`, `platforms`,
`push`. Outputs: `digest`, `tags`.

The build cache is the GitHub Actions cache. Each `image` has its own cache
scope. Thus, when one repository builds two images, one image does not
overwrite the cache of the other image.

Only a build on the default branch (a push or a manual run) writes the
cache. Pull requests and tags read it. A caller that does not build on the
default branch has no cache. To have one, build on a push to the default
branch.

The caller **must** grant `packages: write`; a reusable workflow cannot grant
itself permissions the caller does not have.

Authentication uses the automatic `GITHUB_TOKEN`, so no registry PAT is created
or rotated. This works for packages owned by the same account as the calling
repository. Note that a token good for *pushing* in CI does nothing for
*pulling* elsewhere: a private package still needs a `read:packages` credential
wherever it is consumed.

### `nix-check.yml`

Normal CI does not install Nix. Start this workflow only for changes to Nix
files, in a separate workflow of the caller:

```yaml
name: nix
on:
  pull_request:
    paths: ["**.nix", "flake.lock"]
  push:
    branches: [main]
    paths: ["**.nix", "flake.lock"]

permissions:
  contents: read

jobs:
  nix:
    uses: ryanjdillon/workflows/.github/workflows/nix-check.yml@<sha> # v1.0.0
```

Input: `command` (default `nix flake check`).

Do not make this check a required status check. When the path filter skips
the workflow, a required check stays pending, and the PR cannot merge.

### `nix-devshell-check.yml`

Use this workflow only when the toolchain exists only in Nix, for example a
CAD or EDA toolchain that has no setup action. Other repos run CI without
Nix (see `docs/ci-and-checks.md` of `ryanjdillon/agents`).

```yaml
permissions:
  contents: read

jobs:
  check:
    uses: ryanjdillon/workflows/.github/workflows/nix-devshell-check.yml@<sha> # v1.1.0
    with:
      command: make check
      cache-paths: ~/.cache/my-tool
      cache-key-files: requirements.lock flake.lock
      artifact-name: check-output
      artifact-paths: |
        build/
```

| Input | Default | Use |
| --- | --- | --- |
| `command` | `make check` | The command. It runs with `nix develop --command bash -c`. |
| `cache-paths` | empty | Directories to cache, one on each line. |
| `cache-key-files` | empty | Space-separated globs. Their contents give the key of the `cache-paths` cache. Needed when `cache-paths` is set. |
| `artifact-name` | `check-output` | The name of the artifact. |
| `artifact-paths` | empty | Files or directories to upload, one on each line. The upload also runs when the command fails. |
| `nix-cache` | `true` | Cache the Nix store. The key is the hash of the `*.nix` files and `flake.lock`. |
| `gc-max-store-size` | `1G` | Before a new store cache is saved, collect garbage until the store is this size or has no garbage. |
| `timeout-minutes` | `60` | Cancel the job after this time. |

The workflow installs Nix with `cachix/install-nix-action`, and caches the
store with `nix-community/cache-nix-action`. Before it saves a new store
cache, it collects the garbage. The devshell is a garbage collection root, so
the cache keeps the devshell and drops old closures.

When the key files change, the `cache-paths` cache restores the newest cache
for the same `cache-paths`, and saves a new one with the new key. Thus a tool
that keys its own directories on the same files can reuse what did not change.

Cache the real directory, not a symlink to it. `actions/cache` stores a
symlink as a symlink.

### `security-scan.yml`

Use this workflow in a private repo, where GitHub code scanning and secret
scanning are not available on a personal plan. It writes the findings to the
job summary, and does not upload SARIF.

```yaml
name: security
on:
  pull_request:
  schedule:
    - cron: "17 5 * * 1"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  scan:
    uses: ryanjdillon/workflows/.github/workflows/security-scan.yml@<sha> # v1.3.0
```

| Input | Default | Use |
| --- | --- | --- |
| `semgrep-rules` | `python`, `bash`, `dockerfile`, `javascript`, `typescript`, `go`, `yaml/github-actions`, `yaml/kubernetes`, `yaml/docker-compose`, `generic/ci`, `generic/dockerfile`, `generic/nginx` | Directories of `semgrep/semgrep-rules` to run, one on each line. |
| `semgrep-fail-on-findings` | `false` | Fail the job when Semgrep has a finding. |
| `betterleaks-config` | empty | Path of a Betterleaks config file in the caller's repo. Empty uses the default rules. |
| `timeout-minutes` | `15` | Cancel the job after this time. |

The scan depends on the event:

- `pull_request`: Betterleaks scans only the commits of the PR, from the
  merge base to the head. Semgrep reports only the new findings in the
  changed files (`--baseline-commit`).
- Other events, for example `schedule` and `workflow_dispatch`: Betterleaks
  scans the full history of the branch, and Semgrep scans the full tree.

A Betterleaks finding fails the job. A Semgrep finding fails the job only
when `semgrep-fail-on-findings` is `true`. The log and the summary show only
the rule, the file and the line, never the matched text. To ignore a
Betterleaks finding, add its fingerprint to `.betterleaksignore` at the root
of the repo.

The workflow pins each tool:

- Betterleaks (MIT) is a release archive, with its SHA-256 from the
  `checksums.txt` of the release. The release signs `checksums.txt` with
  Sigstore.
- Semgrep CE (LGPL-2.1) is the `semgrep/semgrep` image, by digest. It runs
  with `--metrics=off` and no network.
- The rules are `semgrep/semgrep-rules` at a commit. The
  [Semgrep Rules License](https://semgrep.dev/legal/rules-license) allows
  internal use, and does not allow distribution. Thus this public repo does
  not copy the rules. Each run takes them from Semgrep's repo.

Do not make this check a required status check until the weekly scan of the
default branch passes.

### `check-instructions`

Checks `AGENTS.md` and `SYSTEM.md` files against the agent instruction budget.
It also makes sure that an `AGENTS.md` ends with its `# SYSTEM.md` section. The
limits are defined only in
[`check-instructions.py`](check-instructions/check-instructions.py). The
reasons for them are in `docs/system-prompt.md` of `ryanjdillon/agents`.

In GitHub Actions, as a step in an existing job:

```yaml
- uses: ryanjdillon/workflows/check-instructions@<sha> # v1.0.0
  with:
    files: AGENTS.md
```

Inputs: `files` (default `AGENTS.md`), `byte-limit`, `rule-limit`. It needs
`python3` on the runner.

With prek, in `.pre-commit-config.yaml`. pre-commit reads the same config:

```yaml
repos:
  - repo: https://github.com/ryanjdillon/workflows
    rev: <sha> # frozen: v1.0.0
    hooks:
      - id: check-instructions
```

The hook checks only the `AGENTS.md` and `SYSTEM.md` at the repo root, as the
action does by default. A nested `AGENTS.md`, for example in a vendored
dependency, has no `# SYSTEM.md` section. To check other files, set `files:`
on the hook.

With Nix, in a flake that has this repo as the input `workflows`:

```nix
checks.${system}.instructions = workflows.lib.checkInstructions {
  inherit pkgs;
  files = [ ./AGENTS.md ];
};
```

Or run it once: `nix run github:ryanjdillon/workflows#check-instructions -- AGENTS.md`.

### `check-process-noise`

Finds issue ids and review-process words in source comments and docstrings.
A comment tells why the code is as it is. The issue and the review history
go in the commit message and the PR. The default patterns are defined only
in [`check-process-noise.py`](check-process-noise/check-process-noise.py):
an issue id (`\bDIL-\d+\b`), and the words `blocker`, `should-fix`,
`finding N`, `re-review`, `hand-back`, and `reviewer`.

The defaults suit the owner's hardware and agent repos: their issue ids, and
the words of their agent review process. In another repo, set your own issue
pattern and words.

The check reads Python comments with `tokenize`, and docstrings with `ast`. A
string that is not a docstring does not match. For shell, Nix, YAML, TOML,
and C-family files, it reads only the lines that start with the comment
marker. For another file type, it fails.

In GitHub Actions:

```yaml
- uses: ryanjdillon/workflows/check-process-noise@<sha> # v1.1.0
  with:
    exclude: "tests/fixtures/*"
```

Inputs: `files` (default: the tracked files that match `globs`), `globs`
(default `*.py`), `exclude`, `issue-pattern`, and `patterns` (one regex on
each line; they replace the default words). It needs `python3` and `git` on
the runner.

With prek:

```yaml
  - repo: https://github.com/ryanjdillon/workflows
    rev: <sha> # frozen: v1.1.0
    hooks:
      - id: check-process-noise
        args: [--issue-pattern, '\bABC-\d+\b']
```

With Nix: `workflows.lib.checkProcessNoise { inherit pkgs; files = [ ./src/main.py ]; }`.
The Nix sandbox has no git, so give the files.

### `check-commit-facts`

Checks the commit messages. A message that names a part number must have a
`Source:` line that names the datasheet or the page. A message that says
"from memory" fails. The default part number pattern is an LCSC number
(`\bC\d{3,8}\b`). The default patterns are defined only in
[`check-commit-facts.py`](check-commit-facts/check-commit-facts.py).

The defaults suit the owner's hardware and agent repos. The default part
number pattern also matches other tokens, for example the reference
designator `C100`. In another repo, set your own part number patterns and
memory pattern.

In GitHub Actions, check out the full history, then check the commits of the
pull request or the push:

```yaml
- uses: actions/checkout@<sha> # v7.0.1
  with:
    persist-credentials: false
    fetch-depth: 0
- uses: ryanjdillon/workflows/check-commit-facts@<sha> # v1.1.0
```

Inputs: `range` (default: `base..head` of the pull request, or
`before..after` of the push), `patterns` (one regex on each line; they
replace the default), and `memory-pattern` (`none` turns it off). For a push
that makes a branch, or a force push whose `before` commit is not in the
clone, the action checks `origin/<default branch>..after`.

With prek, the hook runs in the `commit-msg` stage. Install that hook type
one time in each clone: `prek install --hook-type commit-msg`.

```yaml
  - repo: https://github.com/ryanjdillon/workflows
    rev: <sha> # frozen: v1.1.0
    hooks:
      - id: check-commit-facts
```

With Nix, `workflows.lib.checkCommitFacts` checks message files. The sandbox
has no git history, so use the action or the hook to check a branch.

### `check-skills`

Validates the frontmatter of each `SKILL.md` under the skill roots. The
frontmatter is flat: only the keys `name` and `description`, each on one line,
with a plain YAML scalar. The `name` matches the directory. The rules are
defined only in [`check-skills.py`](check-skills/check-skills.py).

```yaml
- uses: ryanjdillon/workflows/check-skills@<sha> # v1.1.0
  with:
    roots: skills
```

The prek hook checks the root `skills`. To check other roots, set `args:`.
With Nix: `workflows.lib.checkSkills { inherit pkgs; roots = [ ./skills ]; }`.

### `check-conventional-commits`

Checks that each commit subject follows
[Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope)!: description`. The scope and the `!` are optional. One space
follows the colon, and the description is not empty. A body starts after one
blank line. A `BREAKING CHANGE:` or `BREAKING-CHANGE:` footer is allowed. The
defaults are defined only in
[`check-conventional-commits.py`](check-conventional-commits/check-conventional-commits.py):

- The types `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
  `build`, `ci`, `chore`, and `revert`.
- The scope pattern `[a-z0-9._/-]+`.
- A subject of 72 characters or less.

Types and scopes are lowercase. This is stricter than Conventional Commits
1.0 rule 15, which lets a type have any case. A custom scope pattern sets
the case of the scope.

Only the last paragraph of the message is the footer block. A
`BREAKING CHANGE` line there must be `BREAKING CHANGE: <description>`. A
`breaking change:` footer in lowercase gives a warning, not a failure:
tools read only the uppercase token.

By default, the check also rejects these commits:

- A merge commit. In a range, a commit with two or more parents is a merge
  commit. In a message file or a title, a subject such as `Merge branch` or
  `Merge pull request` is a merge commit.
- A `fixup!`, `squash!`, or `amend!` commit. Squash it before the merge.
- The revert subject that git writes, `Revert "feat: x"`. Write
  `revert: feat: x` instead.

An option allows each of them.

When a repo merges pull requests with **rebase**, the commits of the pull
request go on `main` as they are. Then this check on the pull request
guards the history of `main`. When a repo merges with **squash**, the PR
title becomes the subject on `main`, so the action also checks the title.

In GitHub Actions, check out the full history, then check the commits of the
pull request or the push:

```yaml
on:
  pull_request:
    # `edited` runs the check again when the title changes.
    types: [opened, synchronize, reopened, edited]

jobs:
  check-conventional-commits:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0
      - uses: ryanjdillon/workflows/check-conventional-commits@<sha> # v1.2.0
```

| Input | Default | Use |
| --- | --- | --- |
| `range` | empty | A git revision range. Empty uses the event (see below). |
| `types` | empty | The allowed types, lowercase, separated by commas or spaces. Empty uses the default types. |
| `scope-pattern` | empty | A regex that the whole scope must match. Empty uses the default. |
| `max-length` | `72` | The subject length limit. `0` turns it off. |
| `allow-merge-commits` | `false` | `true` does not check merge commits. |
| `allow-autosquash` | `false` | `true` accepts `fixup!`, `squash!`, and `amend!` commits. |
| `allow-git-revert` | `false` | `true` accepts `Revert "..."`. |
| `check-pr-title` | `true` | Also check the PR title. It has an effect only for an event that has a pull request, for example `pull_request` or `pull_request_target`. |

With an empty `range`, the action reads the event. A pull request gives
`base..head`, a merge group gives `base_sha..head_sha`, and a push gives
`before..after`. For a push that makes a branch, or a force push whose
`before` commit is not in the clone, the action checks
`origin/<default branch>..after`. When that range is empty, or the push
is a force push to the default branch, the action checks only the pushed
commit (`after`). A push that deletes a branch has no commits to check. The commits must be in the clone, so set
`fetch-depth: 0`.

A push to a branch that gets merge commits from pull requests has those
merge commits. For that push, set
`allow-merge-commits: ${{ github.event_name == 'push' }}`, or run the check
only on pull requests. A merge queue that uses the merge method also makes
a merge commit in the group, so set `allow-merge-commits: true` for the
`merge_group` event too.

With prek, the hook runs in the `commit-msg` stage. Install that hook type
one time in each clone: `prek install --hook-type commit-msg`. The hook also
runs for `git merge`, and rejects the merge commit. It removes the comment
lines that start with `core.commentChar` (default `#`). If you make `fixup!`
commits and squash them before the merge, add `--allow-autosquash` to
`args:`. CI still rejects them.

```yaml
  - repo: https://github.com/ryanjdillon/workflows
    rev: <sha> # frozen: v1.2.0
    hooks:
      - id: check-conventional-commits
        args: [--types, "feat,fix,docs,chore"]
```

With Nix, `workflows.lib.checkConventionalCommits` checks message files, and a
title with `args = [ "--title" title ]`. The sandbox has no git history, so
use the action or the hook to check a branch. To check a range one time:
`nix run github:ryanjdillon/workflows#check-conventional-commits -- --range origin/main..HEAD`.

## Conventions

- **Third-party actions are pinned by commit SHA**, with the version in a
  trailing comment. Tags are mutable, and these workflows run with a token that
  can publish packages.
- **Callers pin a release by its commit SHA,** with the version in a comment.
  See [Releases](#releases).
- **Prefer explicit `secrets:` over `secrets: inherit`.** Inherit is convenient
  and hands a shared workflow the caller's entire secret set.
- Composite actions live in top-level directories with an `action.yml` and are
  referenced as `ryanjdillon/workflows/<dir>@<sha>`. Use one for step-level reuse;
  use a reusable workflow for a whole job.
- **A shared check has one definition.** Its directory holds the script and
  the action. `.pre-commit-hooks.yaml` and `flake.nix` call the same script.
  Do not copy the logic into an adapter.

## Releases

Callers pin a release by its commit SHA, not by its tag, because a tag is
mutable. Put the version in a comment: `# v1.2.3` after `uses:`, and
`# frozen: v1.2.3` after a prek `rev:`. Renovate reads the comment, and moves
the pin to the SHA of the next release. The shared preset (see
[Renovate](#renovate)) moves all the pins of a repo to the same release in
one PR.

Choose the version from the effect on callers:

| Change | Version |
| --- | --- |
| A fix, with no change to inputs, outputs, hook ids, or results on good files | Patch |
| A new check, workflow, or input, with a default that keeps the old behaviour | Minor |
| A removed or renamed input, output, or hook id, or a stricter default | Major |

A stricter default, for example a lower byte limit, can make a passing caller
fail. Thus it is a major change.

To release:

1. Merge to `main`, with CI green.
2. Create the release and its tag on that commit:
   `gh release create vX.Y.Z --target <sha> --generate-notes`.
3. Move the major tag to it: `git fetch --tags`, then
   `git tag -f v1 vX.Y.Z`, then `git push -f origin v1`. Only the Renovate
   preset reference uses `v1`.

## Renovate

[`renovate/default.json`](renovate/default.json) is the shared Renovate
preset. A repo extends it in its `renovate.json`:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>ryanjdillon/workflows//renovate/default#v1"]
}
```

The preset:

- Waits 7 days before it takes a new release (`minimumReleaseAge`), and
  opens the PR only after that time. Most malicious releases are found and
  removed in a few days. Releases of my own repos do not wait.
- Pins each GitHub Action and Docker image by digest, and keeps the version
  comment.
- Enables the managers that are off by default: prek (`pre-commit`) and Nix.
- Moves all pins to `ryanjdillon/workflows` in one PR.
- Runs lock file maintenance each week: `uv.lock`, `Cargo.lock`, and
  `flake.lock`.

Renovate runs as the Mend Renovate GitHub App. Install the App on each repo
that has a `renovate.json`.

## Tests

CI (`.github/workflows/check.yml`) runs each adapter of each shared check on
its test data, in `<check>/testdata/`. It also makes sure that the bad test
data fails. `nix.yml` runs `nix-check.yml` and `nix-devshell-check.yml` from this
checkout, so the Nix adapter and the reusable workflows are tested before
they merge.

To test on your machine:

- The unit tests: `python3 -m unittest discover -s <check>`.
- The prek hook: `<check>/test-hook.sh`. `prek try-repo` copies only the
  tracked files, so stage a new file before you test it.

## Gotchas

- `env:` defined in the caller does **not** propagate into a reusable workflow.
  Pass values as inputs instead — this silently breaks migrated workflows that
  relied on caller-level `env`.
- Reusable workflows can be nested at most four levels deep.
- A reusable workflow is resolved at the ref you pin. `@main` picks up changes
  immediately, which is convenient while bootstrapping and unwise afterwards.
