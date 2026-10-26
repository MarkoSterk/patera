# /// script
# requires-python = ">=3.13"
# dependencies = ["packaging>=24,<27"]
# ///
"""Build, preview and publish the versioned documentation (Zensical + mike).

Shell wrappers (docs.sh, docs.ps1, publish_docs.sh, publish_docs.ps1) only locate
this file and invoke uv. Tools run through ``uvx``, so nothing is added to the
project environment. See DOCS_PUBLISHING.md for the release workflow.
"""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent

# Zensical's fork of mike (reads zensical.toml, builds with `zensical build`).
# Pin a commit (git+...mike.git@<sha>) for fully reproducible publishing.
MIKE_SOURCE = "mike @ git+https://github.com/squidfunk/mike.git"
DOC_PLUGINS = ["mkdocstrings-python"]

BRANCH = "gh-pages"
REMOTE = "origin"
LATEST = "latest"
DEV = "dev"


class DocsError(Exception):
    pass


def tool(program):
    """Command prefix that runs `zensical` or `mike` in a uvx environment."""
    with_args = [arg for plugin in DOC_PLUGINS for arg in ("--with", plugin)]
    if program == "zensical":
        return ["uvx", *with_args, "zensical"]
    return ["uvx", "--from", MIKE_SOURCE, *with_args, "mike"]


def run(cmd, dry_run=False, capture=False):
    print("$ " + shlex.join(cmd), flush=True)
    if dry_run and not capture:
        return ""
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    if result.returncode != 0:
        raise DocsError(f"Command failed (exit code {result.returncode}): {cmd[0]}")
    return result.stdout or ""


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode, result.stdout.strip()


def core_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    if project["name"] != "patera":
        raise DocsError("docs.py must live in the Patera repository")
    return Version(project["version"])


def docs_version(version):
    """Documentation versions are per minor release: 0.123.4 -> 0.123."""
    return f"{version.major}.{version.minor}"


def sync_docs_branch():
    """Fast-forward the local docs branch to the remote one, so mike sees every version."""
    code, _ = git("ls-remote", "--exit-code", "--heads", REMOTE, BRANCH)
    if code != 0:
        return
    code, _ = git("fetch", "--quiet", REMOTE, f"{BRANCH}:{BRANCH}")
    if code != 0:
        print(
            f"! Could not fast-forward the local {BRANCH} branch to {REMOTE}/{BRANCH}; "
            "it has local commits (for example from --no-push)."
        )


def deployed_versions():
    """Versions on the docs branch, as (name, aliases); empty before the first deploy."""
    code, _ = git("rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}")
    if code != 0:
        return []
    output = run([*tool("mike"), "list", "--json"], capture=True)
    return [
        (item["version"], item.get("aliases", []))
        for item in json.loads(output or "[]")
    ]


def newest(names):
    parsed = []
    for name in names:
        try:
            parsed.append(Version(name))
        except InvalidVersion:
            continue  # "dev" and other non-release names
    return max(parsed, default=None)


def check_repository(args, name):
    if args.allow_dirty:
        print("! Skipping the clean working tree check (--allow-dirty)")
    else:
        _, status = git("status", "--porcelain", "--untracked-files=no")
        if status:
            raise DocsError(
                "The working tree has uncommitted changes. Commit them, or pass --allow-dirty."
            )
    if args.dev:
        return
    # Release docs come from a release tag of the same minor version (v0.123.0, v0.123.1, ...).
    _, tags = git("tag", "--points-at", "HEAD")
    matching = [tag for tag in tags.split() if tag.startswith(f"v{name}.")]
    if matching:
        print(f"✓ HEAD is at release tag {matching[0]}")
        return
    problem = f"HEAD is not at a v{name}.* release tag."
    if args.allow_untagged:
        print(f"! {problem} Continuing (--allow-untagged).")
        return
    raise DocsError(
        f"{problem} Release docs are built from the release tag so the API reference "
        f"matches the published code, for example `git checkout v{name}.0`. "
        "Pass --allow-untagged to publish from the current commit anyway."
    )


def cmd_serve(args):
    run([*tool("zensical"), "serve", *args.extra])


def cmd_build(args):
    run([*tool("zensical"), "build", "--clean", *args.extra])


def cmd_list(args):
    sync_docs_branch()
    run([*tool("mike"), "list"])


def cmd_serve_versions(args):
    run([*tool("mike"), "serve"])


def cmd_deploy(args):
    package_version = core_version()
    if args.dev:
        name = DEV
    else:
        name = args.version or docs_version(package_version)
        try:
            requested = Version(name)
        except InvalidVersion:
            raise DocsError(
                f"Not a version: {name!r} (use --dev for the development docs)"
            )
        if not args.version:
            print(f"Package version {package_version} -> documentation version {name}")
        elif docs_version(requested) != name:
            raise DocsError(
                f"Use the minor version {docs_version(requested)}, not {name}"
            )

    check_repository(args, name)

    print("\nChecking that the site builds…")
    run([*tool("zensical"), "build", "--clean", "--strict"], dry_run=args.dry_run)

    push = [] if args.no_push else ["--push"]
    title = ["--title", args.title] if args.title else []
    sync_docs_branch()

    if args.dev:
        run([*tool("mike"), "deploy", *push, *title, DEV], dry_run=args.dry_run)
    else:
        existing = deployed_versions()
        newest_deployed = newest(version for version, _ in existing)
        is_newest = newest_deployed is None or Version(name) >= newest_deployed
        if is_newest and not args.no_latest:
            run(
                [
                    *tool("mike"),
                    "deploy",
                    *push,
                    *title,
                    "--update-aliases",
                    name,
                    LATEST,
                ],
                dry_run=args.dry_run,
            )
        else:
            if not args.no_latest:
                print(
                    f"! {name} is older than {newest_deployed}: `{LATEST}` is left unchanged"
                )
            run([*tool("mike"), "deploy", *push, *title, name], dry_run=args.dry_run)
        if not existing or args.set_default:
            run([*tool("mike"), "set-default", *push, LATEST], dry_run=args.dry_run)

    where = "the local gh-pages branch" if args.no_push else f"{REMOTE}/{BRANCH}"
    action = "Would publish" if args.dry_run else "Published"
    print(f"\n✓ {action} documentation version {name} to {where}")
    if args.no_push and not args.dry_run:
        print(
            "  Preview with `docs.sh serve-versions`, push with "
            f"`git push {REMOTE} {BRANCH}`."
        )


def cmd_delete(args):
    if args.version == LATEST:
        raise DocsError("`latest` is an alias; delete the version it points to instead")
    push = [] if args.no_push else ["--push"]
    sync_docs_branch()
    run([*tool("mike"), "delete", *push, args.version], dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser(
        "serve", help="live preview of the current docs (zensical serve)"
    )
    serve.add_argument(
        "extra", nargs=argparse.REMAINDER, help="arguments for zensical serve"
    )
    serve.set_defaults(func=cmd_serve)

    build = commands.add_parser("build", help="build the current docs into site/")
    build.add_argument(
        "extra", nargs=argparse.REMAINDER, help="arguments for zensical build"
    )
    build.set_defaults(func=cmd_build)

    commands.add_parser("list", help="list published versions").set_defaults(
        func=cmd_list
    )
    commands.add_parser(
        "serve-versions", help="preview the versioned site from the gh-pages branch"
    ).set_defaults(func=cmd_serve_versions)

    deploy = commands.add_parser("deploy", help="publish a documentation version")
    target = deploy.add_mutually_exclusive_group()
    target.add_argument(
        "--version", help="docs version (default: minor version of pyproject.toml)"
    )
    target.add_argument(
        "--dev", action="store_true", help=f"publish the `{DEV}` docs of main"
    )
    deploy.add_argument("--title", help="title shown in the version selector")
    deploy.add_argument(
        "--no-latest", action="store_true", help=f"do not move the `{LATEST}` alias"
    )
    deploy.add_argument(
        "--set-default",
        action="store_true",
        help=f"make `{LATEST}` the default version (automatic on first deploy)",
    )
    deploy.add_argument(
        "--no-push",
        action="store_true",
        help=f"commit to the local {BRANCH} branch only",
    )
    deploy.add_argument(
        "--allow-untagged",
        action="store_true",
        help="publish a release version without being at its tag",
    )
    deploy.add_argument(
        "--allow-dirty", action="store_true", help="publish with uncommitted changes"
    )
    deploy.add_argument(
        "--dry-run", action="store_true", help="check and print the commands only"
    )
    deploy.set_defaults(func=cmd_deploy)

    delete = commands.add_parser("delete", help="remove a published version")
    delete.add_argument("version")
    delete.add_argument("--no-push", action="store_true")
    delete.add_argument("--dry-run", action="store_true")
    delete.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    try:
        args.func(args)
    except DocsError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
