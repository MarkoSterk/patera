"""Deterministic, allowlisted browser builds; no application imports."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from importlib import import_module, metadata
from pathlib import Path, PurePosixPath

PORTABLE_MODULES = (
    "__init__.py",
    "application.py",
    "browser.py",
    "components.py",
    "controller.py",
    "exceptions.py",
    "discovery.py",
    "routing.py",
    "view.py",
    "lifecycle.py",
    "cache.py",
    "metadata.py",
    "properties.py",
    "updates.py",
    "lists.py",
)
SOURCE_SUFFIXES = {
    ".py",
    ".html",
    ".css",
    ".js",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".woff",
    ".woff2",
}
EXCLUDED = {"__pycache__", "node_modules", "build", "dist", "logs"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def safe_relative(value):
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(p in {".", ".."} for p in value.split("/"))
    ):
        raise ValueError(f"Unsafe asset path: {value!r}")
    return path


def read_asset(root, relative):
    path = root.joinpath(*safe_relative(relative).parts)
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError(f"Asset escapes its root: {relative}")
    return path.read_bytes()


def lock_runtime(
    folder, *, pyscript, interpreter, pyscript_version, pyodide_version, python_version
):
    """Record hashes for a locally provisioned, complete offline runtime."""
    folder = Path(folder).resolve()
    safe_relative(pyscript)
    safe_relative(interpreter)
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Runtime symlink is not allowed: {path}")
        if path.is_file() and path.name != "runtime.json":
            relative = path.relative_to(folder).as_posix()
            files[relative] = digest(read_asset(folder, relative))
    if pyscript not in files or interpreter not in files:
        raise ValueError(
            "PyScript and interpreter entry files must exist inside the runtime folder"
        )
    manifest = {
        "pyscript": pyscript,
        "interpreter": interpreter,
        "pyscript_version": pyscript_version,
        "pyodide_version": pyodide_version,
        "python_version": python_version,
        "files": files,
    }
    _atomic_write(folder / "runtime.json", json_bytes(manifest))
    return folder / "runtime.json"


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ui-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build(source, runtime, output, *, entrypoint, asset_url):
    source, runtime, output = (Path(p).resolve() for p in (source, runtime, output))
    if output.is_relative_to(source) or output.is_relative_to(runtime):
        raise ValueError("Build output must be outside source and runtime folders")
    module, separator, attribute = entrypoint.partition(":")
    if (
        not separator
        or not attribute.isidentifier()
        or not all(p.isidentifier() for p in module.split("."))
    ):
        raise ValueError("ENTRYPOINT must be module:attribute")
    if module.split(".")[0] == "patera":
        raise ValueError("Application entrypoint cannot replace the patera namespace")
    runtime_manifest = json.loads(
        (runtime / "runtime.json").read_text(encoding="utf-8")
    )
    for required in (
        "pyscript",
        "interpreter",
        "pyscript_version",
        "pyodide_version",
        "python_version",
        "files",
    ):
        if not runtime_manifest.get(required):
            raise ValueError(f"Runtime manifest is missing {required}")
    python_version = tuple(
        int(p) for p in runtime_manifest["python_version"].split(".")[:2]
    )
    if (
        len(python_version) != 2
        or python_version[0] != 3
        or not (10 <= python_version[1] <= sys.version_info.minor)
    ):
        raise ValueError(
            "Build Python must support the selected browser Python (3.10 or newer)"
        )
    runtime_files = {}
    for relative, expected in runtime_manifest["files"].items():
        data = read_asset(runtime, relative)
        if digest(data) != expected:
            raise ValueError(f"Runtime checksum mismatch: {relative}")
        runtime_files["runtime/" + relative] = data
    for key in ("pyscript", "interpreter"):
        if "runtime/" + runtime_manifest[key] not in runtime_files:
            raise ValueError(f"Runtime manifest does not include {key}")

    package = Path(__file__).parent
    # Browser-only parent initializers: never import native Patera/desktop code.
    archive = {"patera/__init__.py": b"", "patera/desktop/__init__.py": b""}
    for name in PORTABLE_MODULES:
        archive["patera/desktop/ui/" + name] = (package / name).read_bytes()
    dependency_versions = {}
    dependency_licenses = {}
    for dependency in ("jinja2", "markupsafe"):
        dependency_versions[dependency] = metadata.version(dependency)
        dependency_root = Path(import_module(dependency).__file__).parent
        # MarkupSafe falls back to _native.py when its optional C module is absent.
        for file in sorted(dependency_root.rglob("*.py")):
            archive[dependency + "/" + file.relative_to(dependency_root).as_posix()] = (
                file.read_bytes()
            )
        distribution = metadata.distribution(dependency)
        for file in distribution.files or ():
            if "LICENSE" in file.name.upper():
                dependency_licenses[f"licenses/{dependency}/{file.name}"] = (
                    distribution.locate_file(file).read_bytes()
                )
    templates, resources = {}, {}
    if not source.is_dir():
        raise ValueError(f"Frontend source folder does not exist: {source}")
    for file in sorted(source.rglob("*")):
        relative = file.relative_to(source)
        if any(p.startswith(".") or p in EXCLUDED for p in relative.parts):
            continue
        if file.is_symlink():
            raise ValueError(f"Source symlink is not allowed: {relative}")
        if not file.is_file() or file.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        name = relative.as_posix()
        if relative.parts[0] in {"patera", "jinja2", "markupsafe"} or relative.name in {
            "jinja2.py",
            "markupsafe.py",
        }:
            raise ValueError(
                "Frontend source cannot replace the patera namespace or bundled dependencies"
            )
        data = read_asset(source, name)
        if file.suffix == ".py":
            archive[name] = data
        elif file.suffix == ".html":
            templates[name] = data.decode("utf-8")
        else:
            resources["public/" + name] = data
    module_path = module.replace(".", "/")
    if (
        module_path + ".py" not in archive
        and module_path + "/__init__.py" not in archive
    ):
        raise ValueError(f"Entrypoint module is missing from frontend source: {module}")
    # zipimport needs real package initializers; reject accidental namespace gaps.
    for name, data in list(archive.items()):
        ast.parse(data, filename=name, feature_version=python_version)
        parent = PurePosixPath(name).parent
        while str(parent) != ".":
            if (parent / "__init__.py").as_posix() not in archive:
                raise ValueError(f"Frontend packages require {parent}/__init__.py")
            parent = parent.parent
    archive.update(dependency_licenses)
    archive["ui.json"] = json_bytes(
        {
            "entrypoint": entrypoint,
            "templates": templates,
            "dependencies": dependency_versions,
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(archive.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, data)
    files = {**runtime_files, **resources, "patera-ui.zip": buffer.getvalue()}
    for name in ("bootstrap.py", "adapter.js"):
        files[name] = (package / "assets" / name).read_bytes()
    identity = {
        "files": {name: digest(data) for name, data in sorted(files.items())},
        "runtime": runtime_manifest,
        "asset_url": asset_url,
    }
    build_id = digest(json_bytes(identity))[:24]
    base = asset_url.rstrip("/") + "/" + build_id
    files["config.json"] = json_bytes(
        {
            "interpreter": base + "/runtime/" + runtime_manifest["interpreter"],
            "files": {base + "/patera-ui.zip": "patera-ui.zip"},
        }
    )
    manifest = {
        "format": 1,
        "id": build_id,
        "runtime": runtime_manifest,
        "files": {name: digest(data) for name, data in sorted(files.items())},
    }
    destination = output / build_id
    for name, data in files.items():
        path = destination / name
        if not path.is_file() or digest(path.read_bytes()) != digest(data):
            _atomic_write(path, data)
    _atomic_write(destination / "manifest.json", json_bytes(manifest))
    # Readers see the complete old build or the complete new build.
    _atomic_write(output / "current.json", json_bytes(manifest))
    return manifest


def prepare_package(*, base_dir, source, runtime, output, entrypoint, asset_url):
    """Desktop packaging contribution, also called by standalone .spec files."""
    base = Path(base_dir)
    destination = base / output
    manifest = build(
        base / source,
        base / runtime,
        destination,
        entrypoint=entrypoint,
        asset_url=asset_url,
    )
    return [
        (str(destination / "current.json"), "patera_ui"),
        (str(destination / manifest["id"]), f"patera_ui/{manifest['id']}"),
    ]
