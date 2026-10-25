"""Release preflight and failure recovery without accessing a package registry."""

import importlib.util
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
import zipfile

import pytest


spec = importlib.util.spec_from_file_location(
    "patera_release_scripts", Path(__file__).resolve().parents[2] / "scripts/release.py"
)
release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = release
spec.loader.exec_module(release)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "patera"\nversion = "1.0.0"\n'
        '[project.optional-dependencies]\nui = ["patera-desktop-ui>=1.0"]\n'
        '[tool.uv.workspace]\nmembers = ["packages/*", "examples/demo"]\n'
    )
    for name, dependency in [
        ("patera-desktop", "patera"),
        ("patera-desktop-ui", "patera-desktop"),
    ]:
        folder = tmp_path / "packages" / name
        folder.mkdir(parents=True)
        (folder / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "1.0.0"\n'
            f'dependencies = ["{dependency}>=1.0"]\n'
        )
    example = tmp_path / "examples/demo"
    example.mkdir(parents=True)
    (example / "pyproject.toml").write_text('[project]\nname="demo"\nversion="1.0.0"')
    (tmp_path / "uv.lock").write_bytes(b"original lock\r\n")
    return tmp_path


def artifacts(folder, package):
    folder.mkdir(exist_ok=True)
    prefix = f"{package.name.replace('-', '_')}-{package.version}"
    metadata = f"Metadata-Version: 2.4\nName: {package.name}\nVersion: {package.version}\n".encode()
    with zipfile.ZipFile(folder / f"{prefix}-py3-none-any.whl", "w") as archive:
        archive.writestr(f"{prefix}.dist-info/METADATA", metadata)
    with tarfile.open(folder / f"{prefix}.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo(f"{prefix}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))


def prepare(repo):
    packages = release.discover(repo)
    folder = repo / "dist"
    for package in packages:
        artifacts(folder, package)
    (folder / "release.json").write_text(
        json.dumps({p.name: release.digest(p) for p in release.distributions(folder)})
    )
    return packages


def test_discovery_dependency_order_excludes_examples(repo):
    assert [p.name for p in release.discover(repo)] == [
        "patera",
        "patera-desktop",
        "patera-desktop-ui",
    ]
    path = repo / "packages/patera-desktop/pyproject.toml"
    path.write_text(path.read_text().replace("patera>=1.0", "patera-desktop-ui>=1.0"))
    with pytest.raises(ValueError, match="Cyclic"):
        release.discover(repo)


@pytest.mark.parametrize(
    "problem", ["missing", "stale", "unknown", "tampered", "metadata"]
)
def test_publish_preflight_never_uploads_incomplete_or_changed_release(
    repo, monkeypatch, problem
):
    packages = prepare(repo)
    folder = repo / "dist"
    wheel = next(folder.glob("patera_desktop_ui-*.whl"))
    if problem == "missing":
        wheel.unlink()
    elif problem in {"stale", "unknown"}:
        fake = release.Package(
            "patera" if problem == "stale" else "unrelated", "0.1.0", repo, {}
        )
        artifacts(folder, fake)
    elif problem == "tampered":
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.writestr("changed.py", "changed = True")
    else:
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "wrong.dist-info/METADATA", "Name: wrong\nVersion: 1.0.0\n"
            )
    calls = []
    monkeypatch.setattr(release, "run", lambda *args, **kw: calls.append(args))
    with pytest.raises(ValueError):
        release.publish(repo, packages)
    assert calls == []


def test_publish_dry_run_and_real_order(repo, monkeypatch):
    packages = prepare(repo)
    calls = []
    monkeypatch.setattr(release, "run", lambda *args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(
        release, "credentials", lambda root: {"UV_PUBLISH_TOKEN": "test"}
    )
    release.publish(repo, packages, dry_run=True)
    assert len(calls) == 1 and calls[0][0][1:3] == ("uvx", "twine")
    calls.clear()
    release.publish(repo, packages)
    assert len(calls) == 4
    for package, (args, kwargs) in zip(packages, calls[1:]):
        assert args[1:3] == ("uv", "publish")
        assert all(package.name.replace("-", "_") in str(path) for path in args[-2:])
        assert kwargs["env"]["UV_PUBLISH_TOKEN"] == "test"


def test_build_failure_preserves_old_release_and_success_preserves_desktop_output(
    repo, monkeypatch
):
    packages = prepare(repo)
    desktop = repo / "dist/desktop"
    desktop.mkdir()
    (desktop / "app.exe").write_bytes(b"keep")
    before = {p: p.read_bytes() for p in (repo / "dist").iterdir() if p.is_file()}

    def fail(root, *args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(release, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        release.build(repo, packages)
    assert all(p.read_bytes() == content for p, content in before.items())

    def build(root, *args, **kwargs):
        if args[:2] == ("uv", "build"):
            package = next(p for p in packages if p.name == args[3])
            artifacts(Path(args[-1]), package)

    monkeypatch.setattr(release, "run", build)
    release.build(repo, packages)
    assert (desktop / "app.exe").read_bytes() == b"keep"
    release.publish(repo, packages, dry_run=True)


@pytest.mark.parametrize("failure", ["version", "lock", None])
def test_bump_transaction_and_optional_floors(repo, monkeypatch, failure):
    packages = release.discover(repo)
    before = {
        p: p.read_bytes() for p in [*(x.path for x in packages), repo / "uv.lock"]
    }
    calls = []

    def run(root, *args, **kwargs):
        calls.append(args)
        if args[:2] == ("uv", "version"):
            package = next(p for p in packages if p.name == args[3])
            package.path.write_text(
                package.path.read_text().replace(
                    'version = "1.0.0"', f'version = "{args[4]}"'
                )
            )
            if failure == "version":
                raise subprocess.CalledProcessError(1, args)
        else:
            (repo / "uv.lock").write_text("new lock")
            if failure == "lock":
                raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(release, "run", run)
    if failure:
        with pytest.raises(subprocess.CalledProcessError):
            release.bump(repo, packages, "minor", update_floors=True)
        assert all(p.read_bytes() == content for p, content in before.items())
    else:
        release.bump(repo, packages, "minor", update_floors=True)
        assert calls.count(("uv", "lock")) == 1
        for package in release.discover(repo):
            assert package.version == "1.1.0"
        project = tomllib.loads((repo / "pyproject.toml").read_text())["project"]
        assert project["optional-dependencies"]["ui"] == ["patera-desktop-ui>=1.1.0"]


def test_credentials_are_data_and_environment_wins(repo, monkeypatch):
    monkeypatch.delenv("UV_PUBLISH_TOKEN", raising=False)
    monkeypatch.setenv("UV_PUBLISH_USERNAME", "__token__")
    monkeypatch.setenv("UV_PUBLISH_PASSWORD", "environment")
    (repo / ".env.pypi").write_text('UV_PUBLISH_PASSWORD="$(do-not-execute)"\n')
    assert release.credentials(repo)["UV_PUBLISH_PASSWORD"] == "environment"
    (repo / ".env.pypi").write_text("echo do-not-execute\n")
    with pytest.raises(ValueError, match="supports only"):
        release.credentials(repo)


def test_bump_dry_run_leaves_every_file_unchanged(repo, monkeypatch):
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    monkeypatch.setattr(
        release, "run", lambda *a, **kw: pytest.fail("No command expected")
    )
    release.bump(repo, release.discover(repo), "patch", dry_run=True)
    assert before == {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}


def test_build_dry_run_leaves_every_file_unchanged(repo, monkeypatch, capsys):
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    monkeypatch.setattr(
        release, "run", lambda *a, **kw: pytest.fail("No command expected")
    )
    release.build(repo, release.discover(repo), dry_run=True)
    assert before == {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert "Would build patera " in capsys.readouterr().out


def test_repository_discovery_includes_joltui_after_core():
    root = Path(__file__).resolve().parents[2]
    packages = release.discover(root)
    names = [p.name for p in packages]
    assert names.index("patera") < names.index("patera-joltui")
    assert "quick-exams" not in names


def test_new_extension_independent_bump_build_and_publish(repo, monkeypatch):
    folder = repo / "packages/patera-joltui"
    folder.mkdir()
    metadata = folder / "pyproject.toml"
    metadata.write_text(
        '[project]\nname="patera-joltui"\nversion="0.1.0"\ndependencies=["patera>=1.0"]\n'
    )
    packages = release.discover(repo)
    calls = []

    def run(root, *args, **kwargs):
        calls.append(args)
        if args[:2] == ("uv", "version"):
            package = next(p for p in packages if p.name == args[3])
            source = package.path.read_text()
            source = re.sub(r'version\s*=\s*"[^"]+"', f'version="{args[4]}"', source)
            package.path.write_text(source)
        elif args[:2] == ("uv", "build"):
            package = next(p for p in release.discover(root) if p.name == args[3])
            artifacts(Path(args[-1]), package)

    monkeypatch.setattr(release, "run", run)
    release.bump(repo, packages, "patch", update_floors=True)
    assert tomllib.loads(metadata.read_text())["project"]["version"] == "0.1.1"
    assert tomllib.loads(metadata.read_text())["project"]["dependencies"] == [
        "patera>=1.0.1"
    ]
    assert calls.count(("uv", "lock")) == 1
    packages = release.discover(repo)
    release.build(repo, packages)
    manifest = json.loads((repo / "dist/release.json").read_text())
    assert "patera_joltui-0.1.1-py3-none-any.whl" in manifest
    assert "patera_joltui-0.1.1.tar.gz" in manifest
    monkeypatch.setattr(
        release,
        "credentials",
        lambda root: pytest.fail("Dry run must not read credentials"),
    )
    release.publish(repo, packages, dry_run=True)
    assert not any(args[:2] == ("uv", "publish") for args in calls)
