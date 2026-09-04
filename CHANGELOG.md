# Changelog

## [1.0.2](https://github.com/drumandbytes/opentofu-updater-action/compare/v1.0.1...v1.0.2) (2026-09-04)


### Bug Fixes

* **ci:** use v5 bare output names for the tag-move step ([#7](https://github.com/drumandbytes/opentofu-updater-action/issues/7)) ([a270b35](https://github.com/drumandbytes/opentofu-updater-action/commit/a270b35c1e422077f0e5e684461749c9115cd9cd))

## [1.0.1](https://github.com/drumandbytes/opentofu-updater-action/compare/v1.0.0...v1.0.1) (2026-09-04)


### Bug Fixes

* **deps:** bump the actions group with 2 updates ([#5](https://github.com/drumandbytes/opentofu-updater-action/issues/5)) ([8812249](https://github.com/drumandbytes/opentofu-updater-action/commit/88122491b39fdbddb5fd18bc085e3d198845a571))

## [1.0.0] - 2026-07-21

### Fixed
- Use Python to write multiline `GITHUB_OUTPUT` instead of bash heredoc — shell heredoc parsing is fragile regardless of delimiter choice; Python file writes are not subject to these issues
- Report now uses plain text instead of Markdown — the report is sent inside `<pre>` tags in HTML notification mode, so Markdown syntax (`###`, backticks) rendered as literal characters rather than formatting

### Added
- Initial release: automatic updates for OpenTofu/Terraform providers, Helm charts, modules, and container images
- `~>` pessimistic constraint handling with major-bump safety flag
- Docker Hub and GHCR image tag resolution via OCI registry API
- OpenTofu registry support for providers and modules
- Telegram notifications
- `ignore` input for skipping specific resources
- `dry-run` mode
