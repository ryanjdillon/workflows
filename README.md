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

## Gotchas

- `env:` defined in the caller does **not** propagate into a reusable workflow.
  Pass values as inputs instead — this silently breaks migrated workflows that
  relied on caller-level `env`.
- Reusable workflows can be nested at most four levels deep.
- A reusable workflow is resolved at the ref you pin. `@main` picks up changes
  immediately, which is convenient while bootstrapping and unwise afterwards.
