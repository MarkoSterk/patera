# Publishing the documentation

The documentation site (<https://patera.markosterk.com>) is built with Zensical from `docs/` and
`zensical.toml`. Every **minor** release of the core package gets its own documentation
version (`0.123`, `0.124`, `1.0`, ...). The versions are stored on the `gh-pages` branch by mike
(Zensical's fork) and served by GitHub Pages.

| Name | Meaning |
| --- | --- |
| `0.123` | docs of the 0.123.x releases, built from a `v0.123.*` tag |
| `latest` | alias of the newest released version, and the default page |
| `dev` | docs of the `main` branch (unreleased changes) |

Patch releases (`0.123.1`) redeploy their minor version (`0.123`).

## Commands

Bash and PowerShell wrappers call the same `docs.py` helper. Run them from any directory; they
need only `uv` and `git`. Zensical, mkdocstrings and mike run through `uvx` and are not added to
the project environment.

| Bash | PowerShell | Purpose |
| --- | --- | --- |
| `./scripts/docs.sh serve` | `.\scripts\docs.ps1 serve` | live preview at <http://localhost:8000> |
| `./scripts/docs.sh build` | `.\scripts\docs.ps1 build` | build into `site/` |
| `./scripts/docs.sh list` | `.\scripts\docs.ps1 list` | published versions and aliases |
| `./scripts/docs.sh serve-versions` | `.\scripts\docs.ps1 serve-versions` | preview the versioned site from `gh-pages` |
| `./scripts/publish_docs.sh` | `.\scripts\publish_docs.ps1` | publish the release you have checked out |
| `./scripts/publish_docs.sh --dev` | `.\scripts\publish_docs.ps1 -Dev` | publish `dev` from `main` |
| `./scripts/docs.sh delete 0.120` | `.\scripts\docs.ps1 delete 0.120` | remove a version |

### What `publish_docs` does

1. Reads the version from `pyproject.toml` (`0.123.1` → docs version `0.123`), or uses
   `--version`.
2. Refuses to run with uncommitted changes, or when `HEAD` has no `v0.123.*` tag. Release docs
   must come from the tag, so the generated API reference matches the published code.
3. Builds the site with `zensical build --strict`, so any warning stops the publish.
4. Updates the local `gh-pages` branch from `origin`, then deploys with mike:
   - the newest version gets the `latest` alias,
   - an older version (a fix to old docs) is deployed **without** moving `latest`,
   - on the first deploy, `latest` also becomes the default page.
5. Pushes `gh-pages` to `origin`. GitHub Pages updates within a minute or two.

### Options

| Bash | PowerShell | Effect |
| --- | --- | --- |
| `--dry-run` | `-DryRun` | run the checks and print the commands, publish nothing |
| `--version 0.122` | `-Version 0.122` | publish another minor version (check out its tag first) |
| `--dev` | `-Dev` | publish the `dev` version (no tag needed) |
| `--title "0.123 (beta)"` | `-Title "0.123 (beta)"` | title in the version selector |
| `--no-latest` | `-NoLatest` | do not move the `latest` alias |
| `--set-default` | `-SetDefault` | make `latest` the default page again |
| `--no-push` | `-NoPush` | commit to the local `gh-pages` only (preview with `serve-versions`) |
| `--allow-untagged` | `-AllowUntagged` | publish a release version from an untagged commit |
| `--allow-dirty` | `-AllowDirty` | publish with uncommitted changes |

For reproducible publishing, pin mike to a commit in `MIKE_SOURCE` at the top of `docs.py`.

## Release checklist

Do this after the packages are published to PyPI and the release is tagged (steps 1–6 of the
release checklist in [README.md](README.md)).

**Before the release**

- [ ] Documentation for every user-visible change is in `docs/` (new options in
      `docs/reference/configuration.md`, new commands in `docs/reference/cli.md`).
- [ ] New pages are listed in the `nav` of `zensical.toml`.
- [ ] New public modules have a page under `docs/reference/api/`.
- [ ] `CHANGELOG.md` is complete. The docs include it, so no copy is needed.
- [ ] `./scripts/docs.sh build` finishes with "No issues found".
- [ ] A quick look with `./scripts/docs.sh serve`: new pages, code examples and links.

**Publish**

- [ ] Check out the release tag: `git checkout v0.124.0`.
- [ ] Dry run: `./scripts/publish_docs.sh --dry-run`. Confirm the docs version is `0.124` and that
      `latest` moves.
- [ ] Publish: `./scripts/publish_docs.sh`.
- [ ] Return to `main`: `git checkout main`.
- [ ] Refresh the development docs: `./scripts/publish_docs.sh --dev`.

**After publishing**

- [ ] `./scripts/docs.sh list` shows `0.124 [latest]`.
- [ ] <https://patera.markosterk.com> opens the new version, and the version selector lists it.
- [ ] The API reference shows the released signatures (spot-check a changed class).
- [ ] HTTPS works and the custom domain is still set (repository Settings → Pages).

**For a patch release** (`0.124.1`), the same steps redeploy `0.124`. For a fix to the docs of an
older version, check out its latest tag (`v0.122.3`) and run
`./scripts/publish_docs.sh --version 0.122`; `latest` stays where it is.

## One-time setup

- GitHub Pages serves the `gh-pages` branch, root folder (repository Settings → Pages).
- Custom domain `patera.markosterk.com`: a DNS `CNAME` record `patera` → `markosterk.github.io`,
  the domain verified in the GitHub account's Pages settings, and "Enforce HTTPS" on.
- GitHub keeps the custom domain in a `CNAME` file at the root of `gh-pages`. mike leaves it
  alone. Never add a `CNAME` file to `docs/`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `HEAD is not at a v0.123.* release tag` | `git checkout v0.123.0` (or the latest patch tag), or pass `--allow-untagged` deliberately. |
| `The working tree has uncommitted changes` | Commit or stash; the docs must match a commit. |
| `Could not fast-forward the local gh-pages branch` | A `--no-push` deploy left local commits. Push them (`git push origin gh-pages`) or reset the branch: `git branch -f gh-pages origin/gh-pages`. |
| The build stops on a warning | Fix the warning shown above the error (broken reference, missing file, bad config). |
| The site shows the old version | Wait for the Pages deploy (Actions tab, "pages build and deployment"), then hard-refresh. |
| Custom domain lost | Check that `CNAME` exists at the root of `gh-pages`; re-enter the domain under Settings → Pages. |
