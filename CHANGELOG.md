# Changelog

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
