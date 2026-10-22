# Desktop applications (experimental)

Install `patera-desktop` and check its current exports. It wraps the same ASGI
application in a pywebview window; it is not a separate controller model. Register
the Desktop extension to expose `desktop:run`, `desktop:env`, `desktop:spec`, and
`desktop:package` commands. Inspect `patera cli --list` for installed arguments.
`run_in_window` supports programmatic startup.

Keep the packaged server on loopback. `desktop.env` contains distributable
defaults generated from configuration declarations, not a copy of development
`.env`. Required empty values block packaging. Per-user `settings.env` and data
live in the platform's app data directory; `${PATERA_DATA_DIR}` can appear in
paths. Store mutable SQLite databases/logs there, not next to an executable in a
read-only installation folder. Do not ship private credentials in defaults.

`REMEMBER_GEOMETRY` and `PERSIST_STORAGE` control window/browser persistence.
Packaging uses PyInstaller with namespace/discovery support and includes app
source/resources. `desktop:spec` creates an editable build configuration and
refuses to overwrite an existing one. Review its resource inclusions/exclusions
and test the built app on its target OS. PyInstaller does not cross-compile.

Sources: architecture chapter 19; experimental desktop package source.
