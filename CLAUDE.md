# CLAUDE.md

## Project Overview

A composite GitHub Action (`drumandbytes/opentofu-updater-action`) that scans `.tf` files and opens PRs bumping OpenTofu/Terraform provider, module, Helm chart, and container image versions. All logic lives in one script, `.github/scripts/update_versions.py`, run by `action.yml`'s composite steps — there's no package/CLI entry point.

Sibling repo [argocd-gitops-updater-action](https://github.com/drumandbytes/argocd-gitops-updater-action) does the equivalent for ArgoCD/Helm image tags; same shape, different domain. Don't assume identical internals.

## Contract (action.yml)

- Inputs: `working-directory`, `versions-file` (default `versions.tf`), `ignore`, `skip-providers`/`skip-helm`/`skip-modules`/`skip-images`, `create-pr`, `pr-title`/`pr-branch`/`pr-base`/`commit-message`, `dry-run`, `github-token`, `dockerhub-username`/`dockerhub-token`, `ghcr-token`, notification webhooks (Telegram/Slack/Discord/Teams).
- Outputs: `changes-detected`, `update-report`, `pr-number`, `pr-url`.
- PR creation is `peter-evans/create-pull-request`, pinned by commit SHA.

## Version constraint behaviour (non-obvious)

Provider versions come from the OpenTofu registry API (`registry.opentofu.org/v1/providers/{source}/versions`), not the Terraform registry. Module sources are normalized by stripping a leading `registry.opentofu.org/` or `registry.terraform.io/` prefix before lookup.

Constraint bumping (`new_constraint()` in `update_versions.py`):
- Exact (`1.2.3`) → bumped straight to latest stable.
- `~> 1.2` → bumped within the same major; a cross-major update is flagged for manual review, not applied.
- `~> 1.2.3` → bumped within major.minor; a cross-minor update rewrites to `~> 1.3.0`.

Major bumps are never auto-applied — they land in the PR body under "Major bumps — manual review required". Image registry support is Docker Hub + GHCR only; Quay/GCR/ECR are unimplemented.

## Test / lint

```bash
uv run --with pytest --with pytest-asyncio --with 'aiohttp>=3.9.0,<3.12' --with pyyaml --with packaging --with aioresponses pytest
ruff check . && ruff format --check .
```

No committed venv. CI (`python-action-ci.yml@v1` reusable workflow) gates on `ruff check`, `ruff format --check`, **and** `pytest` — `ruff check` passing alone is not sufficient, formatting drift fails CI separately.

## Release mechanism

release-please (`release-type: simple`, no `v` component in tag) opens the release PR as `dnb-robot[bot]`. Auto-merge (`auto-merge.yml@v1` reusable workflow) is restricted to `patch-only-authors: ["dnb-robot[bot]"]` and merges via an app token (`use-app-token-for-merge: true`) — a plain `GITHUB_TOKEN` merge wouldn't cascade into the next release-please run. Minor/major release PRs need a human merge. Consumers pin `@v1`; `move-floating-tags: true` keeps that tag following releases.
