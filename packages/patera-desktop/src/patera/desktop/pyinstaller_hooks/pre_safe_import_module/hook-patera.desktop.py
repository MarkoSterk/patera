"""Include optional desktop namespace distributions in editable installs."""

import patera.desktop


def pre_safe_import_module(api):
    for path in patera.desktop.__path__:
        api.append_package_path(path)
