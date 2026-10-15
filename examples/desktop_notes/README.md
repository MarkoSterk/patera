# Desktop notes example

Patera Notes, a small notes program: a list of notes with search, an editor that saves as you
type, and a SQLite database in the user's data folder. It is an ordinary Patera application
(a page, a JSON API and a database) shown in a desktop window by `patera-desktop`.

```sh
uv add "patera[dev]" patera-database "patera-desktop[pyinstaller]"

uv run patera cli desktop:run        # in a window, reloading on changes
uv run patera cli desktop:run prod   # in a window, with the production server
uv run patera dev                    # or in a browser: http://localhost:3000
```

Package it as a program:

```sh
uv run patera cli desktop:package    # -> dist/desktop/Patera Notes/
```

Ship the whole `Patera Notes` folder (an installer such as Inno Setup can wrap it). PyInstaller
builds for the system it runs on, so build the Windows program on Windows. The window uses the
system's web view: WebView2 on Windows (part of Windows 10 and 11), WebKit on macOS, and GTK or
Qt on Linux (`pip install "pywebview[qt]"` if neither is installed).

## What it shows

| File | What it shows |
| --- | --- |
| `app/__init__.py` | The `Desktop` extension in `app_extensions`, after the databases. |
| `app/configs.py` | The database in `user_data_dir(APP_NAME)`, and the window's settings (`DESKTOP`). |
| `app/database.py` | The model, and `NotesDb` creating its tables at startup: a program has no setup command for its users. |
| `app/api/notes_api.py` | The JSON API the page uses: list and search, create, update, delete. |
| `app/public/pages_controller.py` | The page the window opens, with the data folder and settings file. |
| `app/templates/`, `app/static/` | The page, its stylesheet and its script (plain JavaScript, `fetch`). |
| `desktop.spec` | The PyInstaller build file from `desktop:spec`, with one edit (below). |

The page works the same in the window and in a browser, because the window is a browser
showing the application on `127.0.0.1`.

## Where the notes are

The program keeps its data in the user's data folder, never next to the executable, whose folder
may be read-only and is replaced by every update:

| System | Folder |
| --- | --- |
| Windows | `%APPDATA%\Patera Notes` |
| macOS | `~/Library/Application Support/Patera Notes` |
| Linux | `~/.local/share/Patera Notes` |

It holds `notes.db`, the installation's settings file `settings.env`, and what the window
keeps: its last size and position (`window.json`) and the web view's cookies and storage
(`webview/`). A packaged program also keeps its `logs/` and the port it listens on (`port`) there.
The page shows the folder and the settings file under "Patera Notes 1.0.0" in the sidebar.

## Settings for one computer

A packaged program reads no `.env`. Settings that differ per computer go into `settings.env`
in the data folder, with the same names as environment variables. For example, to keep the
notes in a synced folder:

```sh
PATERA_NOTES_DB__DATABASE_URI=sqlite+aiosqlite:///D:/Sync/notes.db
```

The program reads the file when it starts. Real environment variables win over it. During
development (`desktop:run`, `patera dev`), use `.env` instead, as in any Patera project.

## The spec file

`desktop.spec` was written by `uv run patera cli desktop:spec` and changed in one place:

```python
HIDDEN_IMPORTS = ["aiosqlite"]
```

SQLAlchemy imports the database driver named in `DATABASE_URI` by name, so PyInstaller cannot
find it by following imports, and the program would stop at startup with
`No module named 'aiosqlite'`. `desktop:package` builds with `desktop.spec` because it is in
this folder. Change the other settings at its top as the program needs, for example `ICON`, or
`ONE_FILE = True` for a single executable.

## Next steps

`NotesDb.create_tables` creates missing tables, which is enough for a first version. Once the program has
users, a change to an existing table needs a migration (`patera-migrate`), which the program then
has to apply when it starts, since its users run no commands.
