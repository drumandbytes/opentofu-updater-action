# Contributing to OpenTofu Updater

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.12 or higher
- pip

### Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/drumandbytes/opentofu-updater-action.git
   cd opentofu-updater-action
   ```

2. Install dependencies:
   ```bash
   pip install aiohttp pyyaml packaging pytest pytest-asyncio ruff
   ```

3. Run tests:
   ```bash
   pytest tests/ -v
   ```

4. Run linting:
   ```bash
   ruff check .github/scripts/
   ruff format --check .github/scripts/
   ```

## Project Structure

```
.
├── action.yml                       # GitHub Action definition
├── .github/
│   ├── scripts/
│   │   └── update_versions.py       # Core version update logic
│   └── workflows/
│       ├── ci.yml                   # CI pipeline
│       └── release-please.yml     # Release automation (release-please)
├── tests/                           # Unit tests
│   ├── conftest.py
│   ├── test_parsers.py              # HCL parsing tests
│   ├── test_updaters.py             # File update function tests
│   └── test_edge_cases.py          # Edge case and error handling tests
├── examples/                        # Example workflow files
└── README.md                        # User documentation
```

## Making Changes

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and return values
- Keep functions focused and single-purpose
- Use async/await for I/O operations

### Testing

- Add tests for new functionality
- Ensure all existing tests pass
- Test edge cases and error conditions

Run tests with:
```bash
pytest tests/ -v
```

### Linting

We use Ruff for linting and formatting:
```bash
# Check for issues
ruff check .github/scripts/

# Auto-fix issues
ruff check --fix .github/scripts/

# Check formatting
ruff format --check .github/scripts/

# Auto-format
ruff format .github/scripts/
```

## Submitting Changes

### Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests and linting
5. Commit with a clear message: `git commit -m "feat: add new feature"`
6. Push to your fork: `git push origin feature/my-feature`
7. Open a Pull Request

### Commits and releases

Releases are automated with [release-please](https://github.com/googleapis/release-please).
It reads the commit history on `main`, keeps a rolling **release PR** with the next
version + changelog, and cuts the release (tag, GitHub Release, `CHANGELOG.md`) when
that PR is merged. The floating `v1` / `v1.N` tags are moved automatically.

For this to work, **squash-merge every PR** with a
[Conventional Commits](https://www.conventionalcommits.org/) title:

| Prefix | Effect | Example |
| --- | --- | --- |
| `feat:` | minor bump | `feat: add support for Azure Container Registry images` |
| `fix:` / `perf:` | patch bump | `fix: handle timeouts when fetching a Helm index.yaml` |
| `feat!:` or `BREAKING CHANGE:` in body | major bump | `feat!: drop Terraform <1.5` |
| `chore:` `docs:` `ci:` `test:` `refactor:` `build:` | no release | `docs: update the README` |

Dependabot is configured to prefix its PRs with `fix(deps):`, so dependency bumps
become patch releases on their own.

The old `release:major` / `release:minor` / `release:patch` labels are gone.
Don't hand-edit `CHANGELOG.md`, `version.txt`, or tags — release-please owns them.

### Pull Request Guidelines

- Keep PRs focused on a single change
- Update documentation if needed
- Add tests for new functionality
- Ensure CI passes before requesting review

## Reporting Issues

When reporting bugs, please include:

1. **Description**: Clear description of the issue
2. **Steps to Reproduce**: How to reproduce the problem
3. **Expected Behavior**: What you expected to happen
4. **Actual Behavior**: What actually happened
5. **Environment**: Python version, OS, relevant workflow configuration
6. **Logs**: Relevant error messages or logs

## Feature Requests

For feature requests:

1. Check existing issues to avoid duplicates
2. Describe the use case
3. Explain the expected behavior
4. Consider if it aligns with the project's goal of keeping OpenTofu/Terraform code up to date

## Questions?

If you have questions, feel free to open an issue with the "question" label.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
