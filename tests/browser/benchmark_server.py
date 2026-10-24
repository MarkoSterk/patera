"""Isolated, seeded notes backend for the optional browser benchmark."""

import argparse
import asyncio
import os
from pathlib import Path
import sqlite3
import sys


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", type=int, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18743)
    parser.add_argument("--framework", action="store_true")
    parser.add_argument("--baseline-ref")
    args = parser.parse_args()
    if sys.platform not in {"win32", "linux"}:
        parser.error(
            "This isolated-data harness currently supports Windows and Linux only."
        )
    root = Path(__file__).resolve().parents[2]
    folder = args.folder.resolve()
    # Never seed or modify the user's normal application data.
    folder.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        {
            "APPDATA": str(folder / "data"),
            "XDG_DATA_HOME": str(folder / "data"),
            "PATERA_DEBUG": "false",
            "PATERA_DEFAULT_LOGGER__ENQUEUE": "false",
            "PATERA_LOG_FILES__ENQUEUE": "false",
            "PATERA_LOG_FILES__PATH": str(folder / "server.jsonl"),
            "PATERA_DESKTOP_UI__RUNTIME": str(args.runtime.resolve()),
            "PATERA_DESKTOP_UI__OUTPUT": str(folder / "ui"),
        }
    )
    sys.path.insert(0, str(root / "examples" / "desktop_ui_notes"))
    if args.framework:
        os.environ["PATERA_DESKTOP_UI__SOURCE"] = str(
            Path(__file__).parent / "framework_fixture"
        )
        os.environ["PATERA_DESKTOP_UI__ENTRYPOINT"] = "fixture:app"
    if args.baseline_ref:
        # Build an isolated comparison bundle; never rewrite the checkout.
        import importlib
        import shutil
        import subprocess

        builder = importlib.import_module("patera.desktop.ui.build")
        package = Path(builder.__file__).parent
        baseline = folder / "baseline-package"
        baseline.mkdir()
        for name in builder.PORTABLE_MODULES:
            shutil.copyfile(package / name, baseline / name)
        shutil.copytree(package / "assets", baseline / "assets")
        for name in ("browser.py", "components.py", "view.py", "assets/adapter.js"):
            data = subprocess.check_output(
                [
                    "git",
                    "show",
                    args.baseline_ref
                    + ":packages/patera-desktop-ui/src/patera/desktop/ui/"
                    + name,
                ],
                cwd=root,
            )
            (baseline / name).write_bytes(data)
        builder.__file__ = str(baseline / "build.py")
    from app import App
    from patera.desktop import user_data_dir
    from patera.desktop.ui import DesktopUI
    import uvicorn

    application = App()
    application._remove_logger_sinks()
    database = user_data_dir(application.app_name) / "notes.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO notes VALUES (?, ?, ?)",
            (
                (
                    i,
                    f"Benchmark note {i:06d} · Research",
                    (
                        "Planning a local-first workspace. Record decisions, review the design, "
                        "and keep useful references together. Focus on clear navigation and a quiet reading experience.\n\n"
                    )
                    * 5
                    + ("narrowtoken" if i % 100 == 0 else ""),
                )
                for i in range(1, args.notes + 1)
            ),
        )
    connection.close()
    application.get_extension(DesktopUI).build()
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host="127.0.0.1",
            port=args.port,
            log_level="error",
            access_log=False,
        )
    )

    async def watch_stop():
        while not server.should_exit:
            if (folder / "stop").exists():
                server.should_exit = True
                return
            await asyncio.sleep(0.2)

    monitor = asyncio.create_task(watch_stop())
    try:
        await server.serve()
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
