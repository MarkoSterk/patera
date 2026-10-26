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

Each documentation version is a separate build, stored on the `gh-pages` branch by mike. The
version selector in the header lists them (`project.extra.version` in `zensical.toml`).

Install the Zensical fork of mike (it reads `zensical.toml` and runs `zensical build`):

```sh
uv tool install "mike @ git+https://github.com/squidfunk/mike.git" \
    --with mkdocstrings-python --with-executables-from zensical
```

Deploy a release from its **Git tag**, so the generated API reference matches the released code:

```sh
git checkout v0.123.0
mike deploy --push --update-aliases 0.123 latest   # first time: also run the next line
mike set-default --push latest
```

The development documentation of `main`:

```sh
git checkout main
mike deploy --push dev
```

Useful commands:

| Command | Purpose |
| --- | --- |
| `mike list` | show deployed versions and aliases |
| `mike serve` | preview the versioned site from `gh-pages` locally |
| `mike delete --push 0.120` | remove a version |
| `mike retitle --push 0.123 "0.123 (beta)"` | change the title in the selector |

Versions are created per minor release (`0.123`, `1.0`); a patch release redeploys its minor
version. See [Versioning](versioning.md).

!!! note "Transitional tooling"

    Zensical's mike fork is transitional until Zensical ships native versioning. Commands and the
    `gh-pages` layout stay compatible with mike 2.x.

### GitHub Actions

Publish the documentation automatically when a release tag is pushed, and the `dev` version on
every push to `main`. Enable GitHub Pages for the `gh-pages` branch in the repository settings.

```yaml
# .github/workflows/docs.yml
name: Documentation
on:
  push:
    branches: [main]
    tags: ["v*"]
permissions:
  contents: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.13"
      - run: >
          uv tool install "mike @ git+https://github.com/squidfunk/mike.git"
          --with mkdocstrings-python --with-executables-from zensical
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      - name: Deploy dev
        if: github.ref == 'refs/heads/main'
        run: mike deploy --push dev
      - name: Deploy release
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          VERSION=$(echo "${GITHUB_REF_NAME#v}" | cut -d. -f1,2)
          mike deploy --push --update-aliases "$VERSION" latest
          mike set-default --push latest
```
