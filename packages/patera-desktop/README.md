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

The only setting is the index page, a path relative to `URL_PREFIX` or an absolute URL:

```python
from patera.desktop import DesktopConfig


class Config(BaseConfig):
    ...
    DESKTOP: DesktopConfig = DesktopConfig(INDEX_PAGE="/dashboard")  # default "/"
```

## Packaging a program

```sh
uv run patera cli desktop:package                  # into dist/desktop
uv run patera cli desktop:package installer/files  # into another folder
```

The command runs PyInstaller. The result is a folder, `dist/desktop/<APP_NAME>/`, with the
executable and everything it needs; ship the whole folder (an installer such as Inno Setup can
wrap it). PyInstaller builds for the system it runs on, so build the Windows program on Windows.

The packaged program runs the server inside its own process, on `127.0.0.1` and a free port, in
production mode, and closes it with the window.

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
  `~/Library/Application Support/<name>` on macOS, `~/.local/share/<name>` on Linux), for example
  a SQLite database:

  ```python
  from patera.desktop import user_data_dir

  DATA = user_data_dir("Notes")
  MAIN_DB: SqlDatabaseConfig = SqlDatabaseConfig(DATABASE_URI=f"sqlite+aiosqlite:///{DATA / 'notes.db'}")
  ```

  The packaged program writes its log files there by default.

See the [Desktop applications section of the Patera documentation](https://github.com/MarkoSterk/Patera#desktop-applications).

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
