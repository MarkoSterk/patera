# Writing the documentation

The documentation is built with [Zensical](https://zensical.org) from the Markdown files in
`docs/` and the configuration in `zensical.toml` at the repository root. The Python API pages are
generated from the source code with [mkdocstrings](https://mkdocstrings.github.io), and versions
are published with Zensical's fork of [mike](https://zensical.org/docs/compatibility/mkdocs/mike/).

## Preview and build

Run from the repository root:

```sh
uvx --with mkdocstrings-python zensical serve           # http://localhost:8000, live reload
uvx --with mkdocstrings-python zensical build --clean   # static site in site/
```

`site/` is build output; keep it out of version control.

## Structure

| Folder | Content | Style |
| --- | --- | --- |
| `getting-started/` | installation and a first application | step by step, for newcomers |
| `guide/` | one page per core feature | explains concepts with examples |
| `extensions/` | one page per extension package | setup, settings, usage |
| `deployment.md` | running in production | checklist |
| `reference/` | configuration options, CLI, public API, Python API | complete, terse look-up |
| `project/` | changelog, versioning, contributing, these notes | |

Add a new page to the `nav` in `zensical.toml`, or it will not appear in the navigation.

- The [changelog](changelog.md) and [license](license.md) pages include `CHANGELOG.md` and
  `LICENSE` from the repository root with snippets (`--8<-- "CHANGELOG.md"`); edit the originals.
- The Python API pages use `::: patera.module` blocks. Docstrings use the Sphinx style
  (`:param name:`). A new public module needs a page under `reference/api/`.
- Keep examples runnable and consistent with the
  [`examples/`](https://github.com/MarkoSterk/Patera/tree/main/examples) applications.
- Changes to public behaviour should update the documentation in the same pull request.

## Publishing versions

Each documentation version is a separate build, stored on the `gh-pages` branch by mike
(Zensical's fork, which reads `zensical.toml`). The version selector in the header lists them
(`project.extra.version` in `zensical.toml`). Versions are created per minor release (`0.123`,
`1.0`); a patch release redeploys its minor version. See [Versioning](versioning.md).

Publishing is scripted in `scripts/`. The step-by-step instructions and the per-release checklist
are in
[`scripts/DOCS_PUBLISHING.md`](https://github.com/MarkoSterk/Patera/blob/main/scripts/DOCS_PUBLISHING.md).

```sh
git checkout v0.123.0                 # release docs are built from the release tag
./scripts/publish_docs.sh --dry-run   # checks + the commands it would run
./scripts/publish_docs.sh             # build --strict, deploy 0.123, move `latest`, push
git checkout main
./scripts/publish_docs.sh --dev       # docs of the unreleased main branch
```

On Windows use `.\scripts\publish_docs.ps1` (`-DryRun`, `-Dev`, ...). Other commands:

| Command | Purpose |
| --- | --- |
| `./scripts/docs.sh serve` | live preview of the working tree |
| `./scripts/docs.sh build` | build into `site/` |
| `./scripts/docs.sh list` | show published versions and aliases |
| `./scripts/docs.sh serve-versions` | preview the versioned site from `gh-pages` locally |
| `./scripts/docs.sh delete 0.120` | remove a version |

!!! note "Transitional tooling"

    Zensical's mike fork is transitional until Zensical ships native versioning. Commands and the
    `gh-pages` layout stay compatible with mike 2.x.

### GitHub Actions

The same script can publish automatically: release docs when a release tag is pushed, and the
`dev` version on every push to `main`.

```yaml
# .github/workflows/docs.yml
name: Documentation
on:
  push:
    branches: [main]
    tags: ["v*"]
permissions:
  contents: write
concurrency:
  group: docs-publish
  cancel-in-progress: false
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v7
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      - name: Publish dev docs
        if: github.ref == 'refs/heads/main'
        run: bash scripts/publish_docs.sh --dev
      - name: Publish release docs
        if: startsWith(github.ref, 'refs/tags/v')
        run: bash scripts/publish_docs.sh
```
