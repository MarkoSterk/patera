# /// script
# requires-python = ">=3.13"
# dependencies = ["packaging>=24,<27"]
# ///
"""Shared release operations; shell wrappers only locate this file and invoke uv."""

import argparse
from dataclasses import dataclass
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile

from packaging.requirements import Requirement
from packaging.utils import (
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import Version


@dataclass
class Package:
    name: str
    version: str
    path: Path
    project: dict


def run(root, *args, env=None):
    subprocess.run(args, cwd=root, env=env, check=True)


def discover(root):
    """Release core and packages/* only, never example workspace members."""
    config = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    if config["project"]["name"] != "patera":
        raise ValueError("Release helper must live in the Patera repository")
    members = config["tool"]["uv"]["workspace"]["members"]
    packages = {}
    for path in [
        root / "pyproject.toml",
        *sorted(root.glob("packages/*/pyproject.toml")),
    ]:
        if path.is_symlink() or path.parent.is_symlink() or path.parent.is_junction():
            raise ValueError(f"Linked package path: {path}")
        if path.parent != root and not any(
            path.parent in root.glob(pattern) for pattern in members
        ):
            raise ValueError(f"Package is not a workspace member: {path.parent}")
        project = tomllib.loads(path.read_text("utf-8"))["project"]
        name = canonicalize_name(project["name"])
        if name in packages:
            raise ValueError(f"Duplicate package: {name}")
        Version(project["version"])
        packages[name] = Package(name, project["version"], path, project)

    edges = {}
    for name, package in packages.items():
        required = [
            Requirement(value) for value in package.project.get("dependencies", [])
        ]
        extras = [
            Requirement(value)
            for values in package.project.get("optional-dependencies", {}).values()
            for value in values
        ]
        for req in required + extras:
            dependency = packages.get(canonicalize_name(req.name))
            if dependency and (
                req.url
                or not req.specifier.contains(dependency.version, prereleases=True)
            ):
                raise ValueError(f"{name}: {req} excludes local {dependency.version}")
        # Include conditional runtime dependencies conservatively, but not extras:
        # core extras refer back to extensions which themselves require core.
        edges[name] = {
            canonicalize_name(req.name) for req in required
        } & packages.keys()
    ordered = []
    while edges:
        ready = sorted(name for name, dependencies in edges.items() if not dependencies)
        if not ready:
            raise ValueError(f"Cyclic release dependencies: {', '.join(edges)}")
        for name in ready:
            ordered.append(packages[name])
            del edges[name]
        for dependencies in edges.values():
            dependencies.difference_update(ready)
    return ordered


def distributions(folder):
    return sorted(p for p in folder.iterdir() if p.name.endswith((".whl", ".tar.gz")))


def artifact_groups(folder, packages):
    expected = {p.name: p for p in packages}
    groups = {p.name: [] for p in packages}
    kinds = set()
    for path in distributions(folder):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Not a regular artifact: {path}")
        wheel = path.name.endswith(".whl")
        if wheel:
            name, version, _, _ = parse_wheel_filename(path.name)
            with zipfile.ZipFile(path) as archive:
                entries = [
                    n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
                ]
                if len(entries) != 1:
                    raise ValueError(f"Expected one METADATA: {path.name}")
                metadata = archive.read(entries[0])
        else:
            name, version = parse_sdist_filename(path.name)
            with tarfile.open(path) as archive:
                entries = [
                    m
                    for m in archive.getmembers()
                    if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")
                ]
                if len(entries) != 1 or not entries[0].isfile():
                    raise ValueError(f"Expected one PKG-INFO: {path.name}")
                metadata = archive.extractfile(entries[0]).read()
        package = expected.get(name)
        if package is None or version != Version(package.version):
            raise ValueError(f"Unknown/stale artifact: {path.name}")
        parsed = BytesParser().parsebytes(metadata)
        if (
            canonicalize_name(parsed["Name"] or "") != name
            or parsed["Version"] != package.version
        ):
            raise ValueError(f"Artifact metadata mismatch: {path.name}")
        kind = (name, wheel)
        if kind in kinds:
            raise ValueError(f"Multiple artifacts of the same type: {name}")
        kinds.add(kind)
        groups[name].append(path)
    for name, files in groups.items():
        if len(files) != 2:
            raise ValueError(
                f"Expected a wheel and sdist for {name}; build all packages first"
            )
    return groups


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_dist(root):
    path = root / "dist"
    if path.is_symlink() or path.is_junction() or (path.exists() and not path.is_dir()):
        raise ValueError("dist must be an ordinary directory inside the repository")
    return path


def build(root, packages):
    target = safe_dist(root)
    # Stage within the repository so promotion uses same-filesystem renames.
    with tempfile.TemporaryDirectory(prefix=".release-", dir=root) as temporary:
        stage = Path(temporary) / "new"
        stage.mkdir()
        for package in packages:
            run(
                root,
                "uv",
                "build",
                "--package",
                package.name,
                "--no-sources",
                "--out-dir",
                str(stage),
            )
        groups = artifact_groups(stage, packages)
        files = [p for values in groups.values() for p in values]
        run(root, "uvx", "twine", "check", "--strict", *map(str, files))
        manifest = {p.name: digest(p) for p in files}
        (stage / "release.json").write_text(
            json.dumps(manifest, indent=2) + "\n", "utf-8"
        )
        target.mkdir(exist_ok=True)
        old = distributions(target) + (
            [target / "release.json"] if (target / "release.json").exists() else []
        )
        if any(p.is_symlink() or not p.is_file() for p in old):
            raise ValueError("dist contains non-regular release artifacts")
        backup = Path(temporary) / "old"
        backup.mkdir()
        moved, installed = [], []
        try:
            for path in old:
                path.replace(backup / path.name)
                moved.append(path)
            for path in [*files, stage / "release.json"]:
                destination = target / path.name
                path.replace(destination)
                installed.append(destination)
        except BaseException:
            for path in installed:
                path.unlink()
            for path in moved:
                (backup / path.name).replace(path)
            raise
    print(f"Built and checked {len(packages)} packages in {target}")


def credentials(root):
    env = os.environ.copy()
    path = root / ".env.pypi"
    allowed = {"UV_PUBLISH_USERNAME", "UV_PUBLISH_PASSWORD", "UV_PUBLISH_TOKEN"}
    if path.exists():
        for line in path.read_text("utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not separator or key not in allowed:
                raise ValueError(
                    ".env.pypi supports only UV_PUBLISH_USERNAME, UV_PUBLISH_PASSWORD, UV_PUBLISH_TOKEN assignments"
                )
            if value.startswith(("'", '"')):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError("Unclosed quote in .env.pypi")
                value = value[1:-1]
            env.setdefault(key, value)
    if not env.get("UV_PUBLISH_TOKEN") and not (
        env.get("UV_PUBLISH_USERNAME") and env.get("UV_PUBLISH_PASSWORD")
    ):
        raise ValueError(
            "Set UV_PUBLISH_TOKEN or UV_PUBLISH_USERNAME and UV_PUBLISH_PASSWORD"
        )
    return env


def publish(root, packages, dry_run=False):
    folder = safe_dist(root)
    groups = artifact_groups(folder, packages)
    manifest_path = folder / "release.json"
    if manifest_path.is_symlink():
        raise ValueError("Linked release manifest")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    actual = {p.name: digest(p) for values in groups.values() for p in values}
    if actual != manifest:
        raise ValueError("Release hashes differ; rebuild all packages")
    run(
        root,
        "uvx",
        "twine",
        "check",
        "--strict",
        *(str(p) for values in groups.values() for p in values),
    )
    if dry_run:
        for package in packages:
            print(f"Would publish {package.name} {package.version}")
        return
    env = credentials(root)
    # Do not allow inherited custom registry configuration to redirect this PyPI workflow.
    for key in ("UV_PUBLISH_URL", "UV_PUBLISH_INDEX"):
        env.pop(key, None)
    for package in packages:
        run(
            root,
            "uv",
            "publish",
            "--publish-url",
            "https://upload.pypi.org/legacy/",
            "--check-url",
            "https://pypi.org/simple/",
            *map(str, groups[package.name]),
            env=env,
        )


def bump(root, packages, part, update_floors=False, dry_run=False):
    versions = {}
    for package in packages:
        old = Version(package.version)
        if not re.fullmatch(r"\d+\.\d+\.\d+", package.version):
            raise ValueError(
                f"Only stable major.minor.patch versions are supported: {package.name}"
            )
        major, minor, patch = old.release
        versions[package.name] = {
            "major": f"{major + 1}.0.0",
            "minor": f"{major}.{minor + 1}.0",
            "patch": f"{major}.{minor}.{patch + 1}",
        }[part]
    for package in packages:
        print(f"{package.name}: {package.version} -> {versions[package.name]}")
    if dry_run:
        print(f"Update internal >= floors: {update_floors}")
        return
    paths = [p.path for p in packages]
    lock = root / "uv.lock"
    before = {p: p.read_bytes() if p.exists() else None for p in [*paths, lock]}
    try:
        for package in packages:
            run(
                root,
                "uv",
                "version",
                "--package",
                package.name,
                versions[package.name],
                "--frozen",
            )
        if update_floors:
            for path in paths:
                source = path.read_text("utf-8")

                def replace(match):
                    name = canonicalize_name(match["name"])
                    return (
                        (match["prefix"] + versions[name])
                        if name in versions
                        else match[0]
                    )

                source = re.sub(
                    r"(?P<prefix>[\"'](?P<name>[A-Za-z0-9_.-]+)(?:\[[^\]\r\n]+\])?\s*>=\s*)\d+(?:\.\d+)*(?:[A-Za-z0-9.+-]*)",
                    replace,
                    source,
                )
                path.write_text(source, "utf-8")
        discover(root)  # Reject incompatible pins/upper bounds before resolving.
        run(root, "uv", "lock")
    except BaseException:
        for path, content in before.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("--dry-run", action="store_true")
    bump_parser = commands.add_parser("bump")
    bump_parser.add_argument(
        "part", nargs="?", default="patch", choices=["major", "minor", "patch"]
    )
    bump_parser.add_argument("--update-dependency-floors", action="store_true")
    bump_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        packages = discover(root)
        if args.command == "build":
            build(root, packages)
        elif args.command == "publish":
            publish(root, packages, args.dry_run)
        else:
            bump(root, packages, args.part, args.update_dependency_floors, args.dry_run)
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
