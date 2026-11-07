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

## Shared checks

A shared check has one definition, in its own directory, and an adapter for
each environment. Each adapter runs the same file, so a local run and CI give
the same result.

| Check | GitHub Actions | prek (or pre-commit) | Nix |
|---|---|---|---|
| [`check-instructions`](check-instructions/) | Composite action | `.pre-commit-hooks.yaml` | `packages`, `lib.checkInstructions` |

### `docker-build-push.yml`

```yaml
permissions:
  contents: read
  packages: write

jobs:
  image:
    uses: ryanjdillon/workflows/.github/workflows/docker-build-push.yml@v1
    with:
      image: ryanjdillon/my-image
```

Inputs: `image` (required), `registry`, `context`, `dockerfile`, `platforms`,
`push`. Outputs: `digest`, `tags`.

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
    uses: ryanjdillon/workflows/.github/workflows/nix-check.yml@<sha>
```

Input: `command` (default `nix flake check`).

Do not make this check a required status check. When the path filter skips
the workflow, a required check stays pending, and the PR cannot merge.

### `check-instructions`

Checks `AGENTS.md` and `SYSTEM.md` files against the agent instruction budget.
It also makes sure that an `AGENTS.md` ends with its `# SYSTEM.md` section. The
limits are defined only in
[`check-instructions.py`](check-instructions/check-instructions.py). The
reasons for them are in `docs/system-prompt.md` of `ryanjdillon/agents`.

In GitHub Actions, as a step in an existing job:

```yaml
- uses: ryanjdillon/workflows/check-instructions@<sha>
  with:
    files: AGENTS.md
```

Inputs: `files` (default `AGENTS.md`), `byte-limit`, `rule-limit`. It needs
`python3` on the runner.

With prek, in `.pre-commit-config.yaml`. pre-commit reads the same config:

```yaml
repos:
  - repo: https://github.com/ryanjdillon/workflows
    rev: <sha>
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

## Conventions

- **Third-party actions are pinned by commit SHA**, with the version in a
  trailing comment. Tags are mutable, and these workflows run with a token that
  can publish packages.
- **Version with tags.** Cut `vN.N.N` releases and move a `vN` tag to the
  newest compatible release so callers can pin `@v1`.
- **Prefer explicit `secrets:` over `secrets: inherit`.** Inherit is convenient
  and hands a shared workflow the caller's entire secret set.
- Composite actions live in top-level directories with an `action.yml` and are
  referenced as `ryanjdillon/workflows/<dir>@v1`. Use one for step-level reuse;
  use a reusable workflow for a whole job.
- **A shared check has one definition.** Its directory holds the script and
  the action. `.pre-commit-hooks.yaml` and `flake.nix` call the same script.
  Do not copy the logic into an adapter.

## Gotchas

- `env:` defined in the caller does **not** propagate into a reusable workflow.
  Pass values as inputs instead — this silently breaks migrated workflows that
  relied on caller-level `env`.
- Reusable workflows can be nested at most four levels deep.
- A reusable workflow is resolved at the ref you pin. `@main` picks up changes
  immediately, which is convenient while bootstrapping and unwise afterwards.
