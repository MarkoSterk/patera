# patera-desktop

Desktop windows for Patera applications, with pywebview, and packaging them as programs with PyInstaller. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

> **Experimental.** This package is not yet ready for production use; its API may change in any release.

## Installation

```sh
pip install patera-desktop
pip install "patera-desktop[pyinstaller]"   # to package the application
# or, with uv
uv add "patera-desktop[pyinstaller]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Running in a window

Register the extension:

```python
from patera.desktop import Desktop


@app(__name__, configs=Config)
class App(Patera):
    app_extensions = [Desktop]
```

Then run:

```sh
uv run patera cli desktop:run        # the development server, with auto-reload
uv run patera cli desktop:run prod   # the production server
```

The command starts the application in a separate process, as `patera dev` or `patera prod`
would, on `127.0.0.1` and the application's `PORT` setting. When it answers, a window opens the
index page; closing the window stops the application.

### Settings

The window is set up by the `DESKTOP` settings:

```python
from patera.desktop import DesktopConfig


class Config(BaseConfig):
    ...
    DESKTOP: DesktopConfig = DesktopConfig(
        INDEX_PAGE="/dashboard",
        WIDTH=1200,
        HEIGHT=800,
        BACKGROUND_COLOR="#17191C",
    )
```

| Setting | Default | Meaning |
|---|---|---|
| `INDEX_PAGE` | `"/"` | The page the window opens: a path relative to `URL_PREFIX`, or an absolute URL. |
| `TITLE` | `APP_NAME` | The window's title. |
| `WIDTH`, `HEIGHT` | 1024 × 720 | The window's size at the first start. |
| `MIN_WIDTH`, `MIN_HEIGHT` | 480 × 360 | The smallest the user can make it. |
| `REMEMBER_GEOMETRY` | `True` | Reopen the window with the size, position and maximized state it had when it was closed. A window whose screen is gone opens centered. |
| `MAXIMIZED`, `FULLSCREEN` | `False` | Open maximized, or in full screen (which is not remembered). |
| `RESIZABLE`, `ON_TOP` | `True`, `False` | |
| `CONFIRM_CLOSE` | `False` | Ask before the window closes. |
| `BACKGROUND_COLOR` | `"#FFFFFF"` | Shown before the page has loaded; match the page to avoid a flash. |
| `TEXT_SELECT` | `True` | The user can select and copy the page's text. |
| `ZOOMABLE` | `False` | The user can zoom with Ctrl and +/-. |
| `PERSIST_STORAGE` | `True` | Keep cookies and local storage between starts (so a signed-in user stays signed in). Off: they are forgotten when the window closes. |
| `ICON` | `None` | Icon file relative to the application's folder (`.ico` on Windows, `.icns` on macOS, `.png` on Linux). Linux shows it on the window; Windows and macOS show the executable's icon, which `desktop:spec` takes from this setting. |
| `DEV_TOOLS` | `None` | The web inspector, from the page's context menu ("Inspect"). Not set: on for `desktop:run` in dev mode and when `DEBUG` is on. |
| `GUI` | `None` | pywebview's toolkit, for example `"qt"` or `"gtk"` on Linux. |

The window's last size and position (`window.json`) and the web view's storage (`webview/`) are
kept in the user's data folder (see below), not in pywebview's own folder, which every pywebview
program shares.

## Packaging a program

```sh
uv run patera cli desktop:package                  # into dist/desktop
uv run patera cli desktop:package installer/files  # into another folder
```

The command runs PyInstaller. The result is a folder, `dist/desktop/<APP_NAME>/`, with the
executable and everything it needs; ship the whole folder (an installer such as Inno Setup can
wrap it). PyInstaller builds for the system it runs on, so build the Windows program on Windows.

The packaged program runs the server inside its own process, on `127.0.0.1`, in production mode,
and closes it with the window. It listens on the port of its last start when that is free, and
otherwise on a free one, which it keeps for the next start: browsers keep local storage per origin,
port included, so the page's storage stays with it.

### The spec file

PyInstaller builds from a spec file, a Python file that lists what goes into the program. When
the application needs more than the defaults, write one and edit it:

```sh
uv run patera cli desktop:spec                     # writes desktop.spec
uv run patera cli desktop:spec specs/windows.spec  # or another file
```

`desktop:package` builds with `desktop.spec` when the project has one (another file:
`desktop:package dist/desktop specs/windows.spec`), otherwise with a generated one in
`build/desktop/`. `pyinstaller desktop.spec` works too. `desktop:spec` does not overwrite an
existing file; delete it to start again. The settings at the top of the file:

| Setting | Default | What it is for |
|---|---|---|
| `PACKAGE_EXCLUDES` | runtime files | Files and folders of the application package that are not copied (see below). |
| `HIDDEN_IMPORTS` | `[]` | Modules PyInstaller does not find, such as ones imported by name (plugins, `importlib`). |
| `COLLECT_SUBMODULES` | the app package, `uvicorn` | Packages included with every module they have. |
| `COLLECT_DATA` | `patera` and the extensions used | Packages whose data files (templates, static files) are included. Add an extension the application starts using later. |
| `DATAS`, `BINARIES` | `[]` | More files, folders and DLLs: `(source, folder in the program)`. |
| `EXCLUDES` | `mypy`, `pytest` | Modules left out. |
| `ICON` | `None` | The program's icon (`.ico` on Windows, `.icns` on macOS). |
| `CONSOLE` | `False` | Show a console window with the program's output, handy when debugging. |
| `ONE_FILE` | `False` | One executable file instead of a folder. It is unpacked at every start, so it starts slower. |
| `ENTRY_SCRIPT` | `None` | Your own entry script instead of the generated one. |

Paths are relative to the spec file. Below the settings is ordinary PyInstaller code
(`Analysis`, `EXE`, `COLLECT`), which you can change as well.

The generated entry script is three lines; write your own with `run_in_window` (and set
`ENTRY_SCRIPT`) if you need to prepare something first:

```python
from app import App
from patera.desktop import run_in_window

if __name__ == "__main__":
    run_in_window(App)
```

Things to keep in mind:

- The application must be in a package (`app/__init__.py`). The package folder is copied next
  to the executable, because Patera finds controllers, exception handlers, middleware and
  templates through its files. What running and developing the application leave in it is
  skipped: `__pycache__`, `logs` and the folder of `LOG_FILES.PATH`, `*.log`, SQLite databases
  (`*.db`, `*.sqlite`, `*.sqlite3` and their journals), `.env` files and tool caches. Change
  `PACKAGE_EXCLUDES` in the spec file for more (a name matches anywhere in the package, a pattern
  with `/` the path from the package folder, such as `"static/uploads"`), or remove `"*.db"` to
  ship a database with the program. Keep secrets and large data out of the package.
- A program has no `.env` file. Give every setting a working default in the configuration
  class, and keep `.env` for development overrides; secrets do not belong in a program at all,
  since anyone who has it can read them. What differs per user or installation goes into the
  installation's settings file, `settings_file(APP_NAME)` (`settings.env` in the data folder
  below). `run_in_window` loads it before the application starts, like `.env` during
  development: the same `PATERA_...` names, and real environment variables win. The application
  may write it, for example from a settings page; changes apply at the next start.
- The program's own folder may not be writable (Program Files) and is replaced by every update.
  Keep data in `user_data_dir(APP_NAME)` (`%APPDATA%\<name>` on Windows,
  `~/Library/Application Support/<name>` on macOS, `~/.local/share/<name>` on Linux; on iOS and
  Android, a folder in the app's private storage), for example a SQLite database:

  ```python
  from patera.desktop import user_data_dir

  DATA = user_data_dir("Notes")
  MAIN_DB: SqlDatabaseConfig = SqlDatabaseConfig(DATABASE_URI=f"sqlite+aiosqlite:///{DATA / 'notes.db'}")
  ```

  The packaged program writes its log files there by default.

See the [Desktop applications section of the Patera documentation](https://github.com/MarkoSterk/Patera#desktop-applications),
and the [notes example](https://github.com/MarkoSterk/Patera/tree/main/examples/desktop_notes), a
complete program with a database, a page and a spec file.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
