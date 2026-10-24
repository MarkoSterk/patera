# Desktop applications (experimental)

Install `patera-desktop` (or `patera-desktop[pyinstaller]` for packaging). Imports
come from `patera.desktop`: `Desktop`, `DesktopConfig`, `run_in_window`,
`user_data_dir`, and `settings_file`. Register `Desktop` in `app_extensions`;
declare `DESKTOP: DesktopConfig` on the backend configuration class. It wraps
the same ASGI app in pywebview; existing HTTP controllers remain unchanged.

For Python-authored browser pages, install the separate `patera-desktop-ui`
distribution and read [desktop UI](desktop-ui.md). Ordinary HTML/JavaScript
desktop apps do not need that package. Keep desktop-specific behavior in these
optional extensions rather than changing core discovery or imports.

## Development and window configuration

Run commands from the project containing the backend app:

```sh
uv run patera cli desktop:run
uv run patera cli desktop:run prod
```

Development starts a reloadable backend subprocess, waits for readiness, then
opens the window. Closing the window stops the backend. Use `DESKTOP.INDEX_PAGE`
for the opening route (relative to `URL_PREFIX`), along with `WIDTH`, `HEIGHT`,
`MIN_WIDTH`, `MIN_HEIGHT`, and `BACKGROUND_COLOR` for window presentation.
`DEV_TOOLS=None` follows dev/debug mode. `REMEMBER_GEOMETRY` and `PERSIST_STORAGE`
retain window geometry and browser storage in the app's user data directory.
For a Python UI, `patera cli ui:run` also builds and watches frontend sources;
`desktop:run` alone does not run the UI watcher.

For a custom executable entry script, put `run_in_window(App)` inside
`if __name__ == "__main__":`. Packaged startup runs the backend in-process on
loopback, preferring the previous port and falling back to a free port. Stable
ports preserve the browser storage origin.

## Configuration and writable data

Keep the packaged server on loopback. `desktop.env` contains distributable
defaults generated from configuration declarations, not a copy of development
`.env`. Required empty values block packaging. Per-user `settings.env` and data
live in the platform's app data directory; `${PATERA_DATA_DIR}` can appear in
paths. Store mutable SQLite databases/logs there, not next to an executable in a
read-only installation folder. Do not ship private credentials in defaults.

Generate defaults with `patera cli desktop:env`. Frozen startup precedence is
environment variables, user `settings.env`, bundled `desktop.env`, then class
defaults; it does not read development `.env`. Development `desktop:run` loads
`desktop.env` below the development `.env`. `APP_NAME` determines the data
directory and cannot be changed by `settings.env`. A declared `SECRET_KEY` is
generated per installation if no value was supplied; do not distribute one
shared key. Use `user_data_dir(APP_NAME)` and `settings_file(APP_NAME)` from
native Python when paths are needed programmatically.

## Packaging

```sh
uv run patera cli desktop:env
uv run patera cli desktop:spec
uv run patera cli desktop:package
```

`desktop:spec [path]` writes an editable spec and refuses to overwrite it.
`desktop:package [output] [spec]` uses the project's `desktop.spec` if present,
otherwise generates one under `build/desktop`. Default output is
`dist/desktop/<APP_NAME>/`; distribute the entire directory. PyInstaller builds
for the host OS, not a different target OS.

The app must be a Python package. Packaging includes app source/resources for
filesystem discovery and excludes runtime files such as logs, databases, caches,
and `.env`. Review `PACKAGE_EXCLUDES`, `COLLECT_DATA`, `COLLECT_SUBMODULES`,
`HIDDEN_IMPORTS`, `DATAS`, and `BINARIES` for the actual app. Spec paths are
relative to the spec file. `ENTRY_SCRIPT` allows custom startup and `CONSOLE`
helps diagnose frozen startup. Keep extension asset preparation in generated
specs: Python UI builds require `DESKTOP_ASSETS` and `prepare_desktop_assets`.

Verify server readiness/shutdown, persistent settings, and the built executable
on the target OS. For UI apps also check offline startup, deep links, API calls,
and frozen resource lookup; a successful PyInstaller build alone is insufficient.

Sources: `packages/patera-desktop/README.md` and `src/patera/desktop/` in that
package; architecture chapter 19.
