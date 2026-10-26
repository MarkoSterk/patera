# Desktop applications

!!! warning "Experimental"

    This package is not yet ready for production use; its API may change in any release.

`patera-desktop` shows a Patera application in a native window
([pywebview](https://pywebview.flowrl.com)) and packages it as a program with
[PyInstaller](https://pyinstaller.org).

```sh
uv add "patera[desktop]"
uv add "patera-desktop[pyinstaller]"   # to package the application
```

For Python-authored browser pages and components, add [Desktop UI](desktop-ui/index.md).
Applications using ordinary HTML and JavaScript do not need it.

## Running in a window

Register the extension; it adds the `desktop:*` CLI commands:

```python
from patera.desktop import Desktop


@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Desktop]
```

```sh
uv run patera cli desktop:run        # the development server, with auto-reload
uv run patera cli desktop:run prod   # the production server
```

The command starts the application in a separate process, as `patera dev` or `patera prod`
would, on `127.0.0.1` and the application's `PORT` setting. Once it answers, a window titled with
`APP_NAME` (or `DESKTOP.TITLE`) opens the index page. Closing the window stops the application.

## Window settings

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
kept in the user's data folder (see below), not in pywebview's shared folder.

## Packaging a program

```sh
uv run patera cli desktop:package                  # into dist/desktop
uv run patera cli desktop:package installer/files  # into another folder
```

The result is a folder, `dist/desktop/<APP_NAME>/`, with the executable and everything it needs;
ship the whole folder (an installer such as Inno Setup can wrap it). PyInstaller builds for the
system it runs on, so build the Windows program on Windows.

The packaged program runs the server in a background thread inside its own process, on
`127.0.0.1`, in production mode, through `run_in_window(App)`, and closes it with the window. It
listens on the port of its last start when that is free, otherwise on a free one, which it keeps
for the next start: browsers keep local storage per origin, port included.

### The spec file

PyInstaller builds from a spec file. When the application needs more than the defaults, write
one and edit it:

```sh
uv run patera cli desktop:spec                     # writes desktop.spec
uv run patera cli desktop:spec specs/windows.spec  # or another file
```

`desktop:package` builds with `desktop.spec` when the project has one (another file:
`desktop:package dist/desktop specs/windows.spec`), otherwise with a generated one in
`build/desktop/`. `pyinstaller desktop.spec` works too. `desktop:spec` does not overwrite an
existing file; delete it to start again.

| Setting | Default | What it is for |
|---|---|---|
| `PACKAGE_EXCLUDES` | runtime files | Files and folders of the application package that are not copied (see below). |
| `HIDDEN_IMPORTS` | `[]` | Modules PyInstaller does not find, such as ones imported by name (plugins, `importlib`). |
| `COLLECT_SUBMODULES` | the app package, `uvicorn` | Packages included with every module they have. |
| `COLLECT_DATA` | `patera` and the extensions used | Packages whose data files (templates, static files) are included. |
| `DATAS`, `BINARIES` | `[]` | More files, folders and DLLs: `(source, folder in the program)`. |
| `EXCLUDES` | `mypy`, `pytest` | Modules left out. |
| `ICON` | `None` | The program's icon (`.ico` on Windows, `.icns` on macOS). |
| `CONSOLE` | `False` | Show a console window with the program's output, handy when debugging. |
| `ONE_FILE` | `False` | One executable file instead of a folder. It is unpacked at every start, so it starts slower. |
| `ENTRY_SCRIPT` | `None` | Your own entry script instead of the generated one. |

Paths are relative to the spec file. Below the settings is ordinary PyInstaller code
(`Analysis`, `EXE`, `COLLECT`), which you can change as well.

The generated entry script is three lines; write your own (and set `ENTRY_SCRIPT`) if you need to
prepare something first:

```python
from app import App
from patera.desktop import run_in_window

if __name__ == "__main__":
    run_in_window(App)
```

### The program's settings

A packaged program reads no `.env`: that file holds development values and often secrets. Its
settings come from `desktop.env`, a file in the project that is bundled into the program:

```sh
uv run patera cli desktop:env      # writes desktop.env from the configuration class
```

The file lists every setting the configuration class declares (not the built-in ones), with its
default in a commented line; remove the `#` to change one. A required setting is an empty line,
and `desktop:package` refuses to build until it has a value. Values are never copied from `.env`.
`${PATERA_DATA_DIR}` is the user's data folder:

```sh
PATERA_MAIN_DB__DATABASE_URI=sqlite+aiosqlite:///${PATERA_DATA_DIR}/app.db
PATERA_DESKTOP__WIDTH=1200
```

At every start the program loads, each over the next: environment variables, the
installation's `settings.env` in the data folder (`settings_file(APP_NAME)`), `desktop.env`, and
the configuration class's defaults. `desktop:run` loads `desktop.env` too, under the development
`.env`. `APP_NAME` names the data folder, so it comes from the class, `desktop.env` or the
environment, not from `settings.env`.

!!! warning "Secrets"

    Anyone with a copy of the program can read `desktop.env`, so it holds no passwords, keys or
    tokens; `desktop:package` warns about values whose names look like secrets. When the
    configuration declares `SECRET_KEY`, the program makes a key of its own at its first start and
    keeps it in the installation's `settings.env`, unless a variable sets one.

### Things to keep in mind

- The application must be in a package (`app/__init__.py`). The package folder is copied next to
  the executable, because Patera finds controllers, exception handlers, middleware and templates
  through its files. What running and developing leave in it is skipped: `__pycache__`, `logs`
  and the folder of `LOG_FILES.PATH`, `*.log`, SQLite databases and their journals, `.env` files
  and tool caches. Change `PACKAGE_EXCLUDES` for more, or remove `"*.db"` to ship a database.
- What differs per user or installation goes into `settings_file(APP_NAME)`. The application may
  write it, for example from a settings page; changes apply at the next start.
- The program's own folder may not be writable (Program Files) and is replaced by every update.
  Keep data in `user_data_dir(APP_NAME)` (`%APPDATA%\<name>` on Windows,
  `~/Library/Application Support/<name>` on macOS, `~/.local/share/<name>` on Linux), with
  `${PATERA_DATA_DIR}` in `desktop.env` or `user_data_dir(APP_NAME)` in code. The packaged program
  writes its log files there by default.

A complete notes program with a database, a page and a spec file lives in
[`examples/desktop_notes`](https://github.com/MarkoSterk/Patera/tree/main/examples/desktop_notes).
