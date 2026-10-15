"""
PyInstaller hook (used by ``patera cli desktop:package``).

Patera's extensions (patera.auth, patera.database, ...) are separate
distributions that install into the ``patera`` namespace, and an editable
or workspace install keeps each of them in a folder of its own. Patera
joins those folders at run time (``pkgutil.extend_path``); PyInstaller
only sees the core package's folder unless this hook names the others.
"""

import patera


def pre_safe_import_module(api):  # type: ignore[no-untyped-def]
    for path in patera.__path__:
        api.append_package_path(path)
