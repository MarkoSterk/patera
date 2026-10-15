"""
The packaged program's settings file, ``desktop.env``.

A packaged program reads no ``.env``: that file holds development values
and often secrets. Its settings come from the configuration class and from
``desktop.env``, a file in the project that ``patera cli desktop:env``
writes from the configuration class, the developer edits and commits, and
``desktop:package`` bundles into the program. At every start the program
loads, each over the next:

1. real environment variables;
2. the installation's ``settings.env`` in the user's data folder;
3. the bundled ``desktop.env``;
4. the configuration class's defaults.

``${PATERA_DATA_DIR}`` in the files is the user's data folder, for paths
such as a SQLite database. ``desktop:run`` loads ``desktop.env`` too, under
the development ``.env``, so the window looks as it will in the program.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import textwrap
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional

from pydantic import BaseModel

#: The program's settings file, next to desktop.spec in the project.
DEFAULT_ENV_FILE = "desktop.env"
#: The user's data folder, for ${PATERA_DATA_DIR} in the settings files.
DATA_DIR_VARIABLE = "PATERA_DATA_DIR"
ENV_PREFIX = "PATERA_"

#: Settings a program sets itself or that cannot be written as text: they
#: are not listed in a new desktop.env.
SKIPPED_SETTINGS = frozenset(
    {"BASE_PATH", "APP_PACKAGE", "HOST", "PORT", "DEBUG", "LOG_FILES.PATH"}
)

#: Setting names that suggest a secret, which a program cannot keep.
SECRET_NAME = re.compile(r"SECRET|PASSWORD|PASSWD|TOKEN|API_KEY|PRIVATE_KEY", re.I)


# ---- reading the configuration class ----------------------------------------------


class Setting:
    """One variable of the configuration: its name, default and description."""

    def __init__(
        self, path: str, required: bool, default: Any, description: str
    ) -> None:
        self.path = path  # "NOTES_DB.DATABASE_URI"
        self.required = required
        self.default = default
        self.description = description

    @property
    def variable(self) -> str:
        return ENV_PREFIX + self.path.replace(".", "__")


def own_settings(config_class: type[BaseModel]) -> list[str]:
    """The fields the application's configuration classes declare (not BaseConfig's)."""
    from patera import BaseConfig

    names: list[str] = []
    for cls in reversed(config_class.__mro__):
        if not (isinstance(cls, type) and issubclass(cls, BaseConfig)):
            continue
        if cls is BaseConfig:
            continue
        for name in getattr(cls, "__annotations__", {}):
            if name in config_class.model_fields and name not in names:
                names.append(name)
    return names


def settings(config_class: type[BaseModel]) -> list[Setting]:
    """The application's own settings, settings models expanded field by field."""
    found: list[Setting] = []
    for name in own_settings(config_class):
        found.extend(_settings(config_class, name, None, ""))
    return found


def _settings(
    model: type[BaseModel], name: str, defaults: Optional[BaseModel], prefix: str
) -> Iterator[Setting]:
    field = model.model_fields[name]
    path = prefix + name
    if path in SKIPPED_SETTINGS:
        return
    if defaults is not None:
        required, default = False, getattr(defaults, name)
    elif field.is_required():
        required, default = True, None
    else:
        required, default = False, field.get_default(call_default_factory=True)

    annotation = field.annotation
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        nested = default if isinstance(default, BaseModel) else None
        for sub_name in annotation.model_fields:
            yield from _settings(annotation, sub_name, nested, path + ".")
        return
    if not required and not _writable(default):
        return
    description = (field.description or "").strip().split("\n")[0]
    yield Setting(path, required, default, description)


def _writable(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool, Enum, Path)):
        return True
    if isinstance(value, (list, tuple, dict)):
        try:
            json.dumps(value)
        except TypeError:
            return False
        return True
    return False


def env_value(value: Any) -> str:
    """``value`` as it is written in an env file."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, (list, tuple, dict)):
        return "'" + json.dumps(value) + "'"
    text = str(value)
    if re.search(r"[\s#'\"\\]", text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


# ---- writing desktop.env ----------------------------------------------------------


def env_text(app: Any) -> str:
    """A desktop.env for ``app``: its settings with their defaults, to edit."""
    lines = [
        f'# Settings of the packaged program "{app.app_name}", made by "patera cli desktop:env".',
        "#",
        "# desktop:package bundles this file into the program, which loads it at every",
        "# start. Environment variables, then the installation's settings.env, win over",
        "# it; the configuration class's defaults apply to whatever it leaves out.",
        "# desktop:run loads it too, under the development .env.",
        "#",
        "# Anyone with a copy of the program can read this file: no passwords, keys or",
        "# tokens. ${PATERA_DATA_DIR} is the user's data folder, for example",
        "#   PATERA_MAIN_DB__DATABASE_URI=sqlite+aiosqlite:///${PATERA_DATA_DIR}/app.db",
        "# The program runs in production mode unless PATERA_DEBUG says otherwise.",
        "#",
        "# Commented lines show the defaults: remove the # to change one. Lines without a",
        "# value are required: desktop:package refuses to build until they have one.",
    ]
    group = None
    for setting in settings(type(app.configs)):
        top = setting.path.split(".")[0]
        if top != group:
            group = top
            lines.append("")
        label = setting.path + (" (required)" if setting.required else "")
        comment = f"{label}: {setting.description}" if setting.description else label
        lines.extend(
            "# " + line
            for line in textwrap.wrap(comment, width=86, subsequent_indent="  ")
        )
        if setting.required:
            lines.append(f"{setting.variable}=")
        else:
            lines.append(f"# {setting.variable}={env_value(setting.default)}")
    return "\n".join(lines) + "\n"


def write_env_file(app: Any, path: Path) -> Path:
    if path.exists():
        raise FileExistsError(
            f"{path} already exists. Delete it (or give another path) to make a new one."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(env_text(app), encoding="utf-8")
    return path


# ---- checking it before packaging ----------------------------------------------


def missing_required(app: Any, path: Path) -> list[str]:
    """Required settings that ``path`` gives no value (all of them without a file)."""
    from dotenv import dotenv_values

    values = dotenv_values(path, interpolate=False) if path.is_file() else {}
    return [
        setting.variable
        for setting in settings(type(app.configs))
        if setting.required and not values.get(setting.variable)
    ]


def secret_like(path: Path) -> list[str]:
    """Variables with a value in ``path`` whose names suggest a secret."""
    from dotenv import dotenv_values

    if not path.is_file():
        return []
    values = dotenv_values(path, interpolate=False)
    return [
        name for name, value in values.items() if value and SECRET_NAME.search(name)
    ]


# ---- loading it in the program -----------------------------------------------------


def bundled_env_file() -> Path:
    """desktop.env as the program finds it: bundled, or in the current folder."""
    base = (
        Path(getattr(sys, "_MEIPASS", ""))
        if getattr(sys, "frozen", False)
        else Path.cwd()
    )
    return base / DEFAULT_ENV_FILE


def program_app_name(config_class: type[BaseModel], env_file: Path) -> str:
    """
    APP_NAME as the program will see it, before its settings are loaded: it
    names the data folder in which the installation's settings.env lives,
    so it comes from the environment, desktop.env or the class only.
    """
    from dotenv import dotenv_values

    name = os.environ.get(ENV_PREFIX + "APP_NAME")
    if not name and env_file.is_file():
        name = dotenv_values(env_file, interpolate=False).get(ENV_PREFIX + "APP_NAME")
    if not name:
        name = config_class.model_fields["APP_NAME"].get_default(
            call_default_factory=True
        )
    return str(name)


def load_program_env(
    config_class: type[BaseModel],
    env_file: Path,
    data_folder: Path,
    installation_settings: Optional[Path] = None,
) -> None:
    """
    Loads the program's settings into the environment, under the variables
    already set: the installation's settings.env, then desktop.env.
    """
    from dotenv import load_dotenv

    os.environ.setdefault(DATA_DIR_VARIABLE, data_folder.as_posix())
    if installation_settings is not None and installation_settings.is_file():
        load_dotenv(installation_settings, override=False)
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def ensure_secret_key(config_class: type[BaseModel], settings_path: Path) -> None:
    """
    A program whose configuration declares SECRET_KEY gets a key of its own,
    made at its first start and kept in the installation's settings.env: a
    key shipped with the program would be the same for every user and
    readable by anyone who has a copy.
    """
    variable = ENV_PREFIX + "SECRET_KEY"
    if "SECRET_KEY" not in config_class.model_fields or os.environ.get(variable):
        return
    key = secrets.token_urlsafe(48)
    existing = (
        settings_path.read_text(encoding="utf-8") if settings_path.is_file() else ""
    )
    separator = "" if not existing or existing.endswith("\n") else "\n"
    settings_path.write_text(
        f"{existing}{separator}# Made at the first start; keep it secret.\n{variable}={key}\n",
        encoding="utf-8",
    )
    os.environ[variable] = key
