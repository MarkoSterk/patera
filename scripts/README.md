### Release scripts

Run the scripts from the repository root (they use `packages/`, `dist/` and `.env.pypi`
relative to it).

##### Release checklist
1. Bump the versions (below) and the `patera>=` / `patera-*>=` floors in every `pyproject.toml`
   and in the core extras, then run `uv lock`.
2. Add the release to `CHANGELOG.md`.
3. Run the checks: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`.
4. Build and check: `build_all`.
5. Publish: `publish_all`, then tag the release (`git tag v<version>` and push the tag).

##### Bump the version of all packages
WIN: `.\scripts\bump_version.ps1 major|minor|patch`
LINUX/MAC: `./scripts/bump_version.sh major|minor|patch`

##### Build all packages (into `dist/`)
Empties `dist/`, builds the core and every extension, and checks the metadata with
`twine check --strict`.

WIN: `.\scripts\build_all.ps1`
LINUX/MAC: `./scripts/build_all.sh`

##### Publish all packages to PyPI
Requires a `.env.pypi` file with `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD`
(for a PyPI token: `UV_PUBLISH_USERNAME=__token__`, `UV_PUBLISH_PASSWORD=<token>`).
Packages are uploaded in dependency order; files already on PyPI are skipped, so a failed run
can be repeated.

WIN: `.\scripts\publish_all.ps1`
LINUX/MAC: `./scripts/publish_all.sh`
