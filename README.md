# opentofu-updater-action

A GitHub Action that keeps your OpenTofu/Terraform code up to date by automatically opening PRs when new versions are available for:

- **Providers** — via the OpenTofu registry API
- **Helm charts** — via Helm repo `index.yaml`
- **Modules** — via the OpenTofu/Terraform registry API
- **Container images** — via Docker Hub and GHCR OCI registry APIs

## Usage

```yaml
- uses: drumandbytes/opentofu-updater-action@v1
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

See [`examples/basic.yml`](examples/basic.yml) and [`examples/advanced.yml`](examples/advanced.yml) for complete workflow files.

## Inputs

| Input | Description | Default |
|---|---|---|
| `working-directory` | Directory containing `.tf` files | `.` |
| `versions-file` | File with `required_providers` block | `versions.tf` |
| `ignore` | Comma-separated providers/charts/images to skip | |
| `skip-providers` | Skip provider checks | `false` |
| `skip-helm` | Skip Helm chart checks | `false` |
| `skip-modules` | Skip module checks | `false` |
| `skip-images` | Skip container image checks | `false` |
| `create-pr` | Open a PR when updates are found | `true` |
| `pr-title` | PR title | `chore: update OpenTofu versions` |
| `pr-branch` | PR branch name | `chore/opentofu-updater` |
| `pr-base` | Base branch for the PR | `main` |
| `commit-message` | Commit message | `chore: update OpenTofu versions` |
| `dry-run` | Report changes without writing files | `false` |
| `github-token` | GitHub token for creating PRs | `github.token` |
| `dockerhub-username` | Docker Hub username (raises rate limits) | |
| `dockerhub-token` | Docker Hub access token | |
| `ghcr-token` | GitHub token for GHCR lookups | `github-token` |
| `telegram-token` | Telegram bot token for notifications | |
| `telegram-chat-id` | Telegram chat ID for notifications | |

## Outputs

| Output | Description |
|---|---|
| `changes` | `true` if any updates were found |
| `report` | Markdown report of all changes |

## Version constraint behaviour

| Constraint | Behaviour |
|---|---|
| `1.2.3` (exact) | Bumped directly to latest stable |
| `~> 1.2` | Minor bumped within major; cross-major flagged for manual review |
| `~> 1.2.3` | Patch bumped within major.minor; cross-minor bumped to `~> 1.3.0` |

Major version bumps are never applied automatically — they appear in the PR body under **"Major bumps — manual review required"**.

## Supported image registries

| Registry | Support |
|---|---|
| Docker Hub (`docker.io`) | Full, with optional auth |
| GitHub Container Registry (`ghcr.io`) | Full, uses `ghcr-token` or `github-token` |
| Quay, GCR, ECR, etc. | Not yet supported |

## Related

- [argocd-gitops-updater-action](https://github.com/drumandbytes/argocd-gitops-updater-action) — auto-updates container image tags in ArgoCD GitOps repos
