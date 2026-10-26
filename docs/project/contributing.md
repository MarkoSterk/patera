# Contributing

## Repository layout

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/):

| Path | Content |
| --- | --- |
| `src/patera` | the core package |
| `packages/patera-*` | the extension packages, all in the `patera` namespace |
| `examples/` | example applications |
| `tests/` | unit, integration and extension tests |
| `docs/` | this documentation ([Zensical](https://zensical.org)) |
| `scripts/` | version bump, build and publish helpers |

## Development environment

```sh
uv sync --all-packages --all-extras    # note: the AI interface pulls in PyTorch
uv run pytest                          # tests/ (unit, integration and extension tests)
PATERA_TEST_PG_URI=postgresql+asyncpg://... uv run pytest   # also run the pgvector tests
uv run pytest --cov
uv run ruff check . && uv run ruff format --check .
uv run mypy src/patera packages --follow-imports=silent
```

CI runs the tests, Ruff, mypy, a browser-bootstrap syntax check (`python scripts/check_browser.py`)
and the packaging checks on Windows, Linux and macOS with Python 3.13 and 3.14.

## Pull requests

- Changes to public behaviour come with tests and a documentation update in `docs/`.
- New public names follow the [public API conventions](../reference/public-api.md).
- Add an entry to `CHANGELOG.md` under *Unreleased*; list breaking changes first.

## Releasing

The scripts in `scripts/` share one `release.py` helper and run from any directory.

### Version bumps

=== "Linux/macOS"

    ```sh
    ./scripts/bump_version.sh patch --dry-run
    ./scripts/bump_version.sh patch
    ./scripts/bump_version.sh minor --update-dependency-floors
    ```

=== "Windows"

    ```powershell
    .\scripts\bump_version.ps1 patch -DryRun
    .\scripts\bump_version.ps1 patch
    .\scripts\bump_version.ps1 minor -UpdateDependencyFloors
    ```

Each package increments its own version. To set every release package to a coordinated
candidate, use `--version 1.0.0rc1 --update-dependency-floors --dry-run` (PowerShell:
`-Version 1.0.0rc1 -UpdateDependencyFloors -DryRun`), then `1.0.0rc2` and finally `1.0.0`.
Failures restore the original package metadata and lockfile. Dependency minimums stay unchanged
unless the floor option is given.

### Build and publish

```sh
./scripts/build_all.sh --dry-run      # preview the order
./scripts/build_all.sh                # wheel/sdist pairs, verified, twine check --strict
python scripts/smoke_wheels.py        # install all wheels together and check imports
./scripts/publish_all.sh --dry-run    # preflight without credentials
./scripts/publish_all.sh
```

Builds replace `dist/` only when every package passes, and `release.json` records SHA-256
hashes. Publishing needs `UV_PUBLISH_TOKEN` (or `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD`)
from the environment or `.env.pypi`; never commit credentials. Uploads run in dependency order and
stop on failure.

### Release checklist

1. Bump versions, review compatibility and the lockfile.
2. Update `CHANGELOG.md`.
3. Run tests, lint/type checks, and UI browser/frozen checks as applicable.
4. Build distributions and inspect contents when resources change.
5. Run the publish dry-run, then publish.
6. Tag the release (`git tag v<core-version>`) and push the tag.
7. Publish the documentation for the new version (see [Writing the documentation](documentation.md#publishing-versions)).
