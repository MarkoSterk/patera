# Release scripts

Bash and PowerShell wrappers use the same `release.py` helper. Run them from any
directory; paths are relative to the repository, not your shell. Install `uv`;
it provisions Python >=3.13 and the declared `packaging` dependency if needed.
Metadata checks use `uvx twine`.

Core and every `packages/*/pyproject.toml` workspace package are discovered from
metadata, including desktop UI. Example workspace members are not released.
Required internal dependencies determine build/upload order; optional extras are
checked for compatibility but do not create ordering cycles.

## Version bumps

```powershell
.\scripts\bump_version.ps1 patch -DryRun
.\scripts\bump_version.ps1 patch
.\scripts\bump_version.ps1 minor -UpdateDependencyFloors
```

```sh
./scripts/bump_version.sh patch --dry-run
./scripts/bump_version.sh patch
./scripts/bump_version.sh minor --update-dependency-floors
```

Each package increments its own version, independently of core. Only stable
`major.minor.patch` versions are accepted. All versions update without
intermediate resolution, followed by internal compatibility checks and one
`uv lock`. Failure restores original package metadata and the lockfile; the
development environment is not synced. Review the resulting diff. Rollback
covers command failures, not abrupt power loss.

Dependency minimums stay unchanged by default. The explicit floor option
updates existing `>=` minimums for release packages in dependencies and extras,
including core extras. It does not rewrite pins, upper bounds or example apps.
Incompatible constraints stop and roll back the bump. Raising minimums changes
compatibility and is not required for every patch release.

## Build

Windows: `.\scripts\build_all.ps1`
Linux/macOS: `./scripts/build_all.sh`

Builds wheel/sdist pairs with `uv build --no-sources` in staging, verifies their
names, versions and embedded metadata, and runs `twine check --strict`. Only
when every package passes are release artifacts replaced in `dist/`. Unrelated
files/directories (including `dist/desktop`) are preserved. Failed builds retain
the previous release. Linked output directories/artifacts are rejected.
`release.json` records SHA-256 hashes; retain it with the distributions.

## Publish

```powershell
.\scripts\publish_all.ps1 -DryRun
.\scripts\publish_all.ps1
```

```sh
./scripts/publish_all.sh --dry-run
./scripts/publish_all.sh
```

Before uploading, every package must have exactly one wheel and one sdist for
its current version. Unknown, stale, duplicate, missing, metadata-mismatched or
hash-mismatched artifacts stop the release. Strict metadata checking runs again.
Dry run performs this preflight and prints upload order without credentials or
uploads. An old `dist/` without `release.json` must be rebuilt first.

Supply `UV_PUBLISH_TOKEN` or both `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD`
through the environment or repository `.env.pypi`. Environment values take
precedence. Username/password token authentication uses username `__token__`.
The file accepts only these three `KEY=value` settings, optional matching quotes,
blank lines and whole-line comments. It is data, never executed shell code; do
not use `export`, interpolation or inline comments. Never commit credentials.

Uploads target PyPI explicitly in dependency order and stop on failure.
`--check-url https://pypi.org/simple/` permits retries after partial uploads.
Remote publication cannot be transactional: earlier packages may already be
published when an upload fails. Retain verified artifacts for retries; do not
rebuild different contents under an already published version.

## Release checklist

1. Bump versions, review compatibility and the lockfile.
2. Update `CHANGELOG.md`.
3. Run relevant tests, lint/type checks, and UI browser/frozen checks as applicable.
4. Build distributions and inspect contents when resources change.
5. Run publish dry-run, then publish when ready.
6. Tag the release (`git tag v<core-version>`) and push the tag.

Local release tests: `python -m pytest tests/unit/test_release_scripts.py`.
