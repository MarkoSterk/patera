### Release scripts

Run the scripts from the repository root (they use `packages/`, `dist/` and `.env.pypi`
relative to it).

##### Bump the version of all packages
WIN: `.\scripts\bump_version.ps1 major|minor|patch`
LINUX/MAC: `./scripts/bump_version.sh major|minor|patch`

##### Build all packages (into `dist/`)
WIN: `.\scripts\build_all.ps1`
LINUX/MAC: `./scripts/build_all.sh`

##### Publish all packages to PyPI
Requires a `.env.pypi` file with `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD`
(for a PyPI token: `UV_PUBLISH_USERNAME=__token__`, `UV_PUBLISH_PASSWORD=<token>`).

WIN: `.\scripts\publish_all.ps1`
LINUX/MAC: `./scripts/publish_all.sh`
