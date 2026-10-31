"""Install the bundled Patera agent guidance without loading an application."""

import argparse
import sys
from importlib.resources import files
from pathlib import Path

PROFILES = {
    "codex": ("AGENTS.md", ".agents/skills/patera"),
    "claude": ("CLAUDE.md", ".claude/skills/patera"),
}
START = "<!-- patera:agents:start -->"
END = "<!-- patera:agents:end -->"


def _instructions(skill_path: str) -> str:
    return (
        "## Patera framework\n\n"
        f"For Patera work, read [{skill_path}/SKILL.md]({skill_path}/SKILL.md) "
        "and the topic references relevant to the change.\n"
        "Follow this project's existing structure and dependency versions. "
        "Use the installed framework source to resolve API differences.\n"
        "- Type backend controllers and application-specific extensions with the "
        'concrete application class: `Controller["App"]` and '
        '`BaseExtension["App", ExtensionConfig]`. Import the application class '
        "under `if TYPE_CHECKING:` to avoid circular imports. Keep configuration "
        "models and injected dependencies importable at runtime.\n"
        "- Always use named members of `HttpStatus` from `patera` for HTTP statuses "
        "in responses, decorators, exceptions, and test assertions. Never write a "
        "bare integer status code.\n"
        "- Put every application setting that can reasonably be expressed as data "
        "in the project's `.env` file. Declare custom fields on `Config` with "
        "type annotations only. Assign values there only when they require Python, "
        "such as `REQUEST_CLASS` and `RESPONSE_CLASS`, or when computing them is "
        "more practical, such as deriving `BASE_PATH` from `__file__`.\n\n"
        "Place each application class in its own file, including controllers, "
        "middleware, extensions, services, models, and schemas. Keep persistence "
        "models in models/ and Pydantic schemas in schemas/, with a separate "
        "subpackage for each model or schema unless they are directly connected. "
        "Connected classes may share a subpackage, but still use one file per class. "
        "See the skill's application reference for the directory layout.\n"
        "Group related utility functions in a utility class and define each "
        "with `@staticmethod`. Avoid standalone utility functions.\n"
        "Controllers and injected services are shared: keep request state in "
        "local variables or request context. Register infrastructure during "
        "construction and manage resources through startup/shutdown hooks.\n"
        "Run the relevant project tests; use PateraTestClient as an async "
        "context manager for HTTP tests so lifespan hooks run.\n"
    )


def _merge_instructions(existing: str, body: str) -> str:
    """Replace only our marked section; retain the surrounding text verbatim."""
    newline = "\r\n" if "\r\n" in existing else "\n"
    block = START + newline + body.replace("\n", newline) + END
    if START not in existing and END not in existing:
        separator = (
            "" if not existing else newline if existing.endswith("\n") else newline * 2
        )
        return existing + separator + block + newline
    if existing.count(START) != 1 or existing.count(END) != 1:
        raise ValueError(
            "ambiguous Patera section markers; repair them before regenerating"
        )
    start, end = existing.index(START), existing.index(END)
    if end < start:
        raise ValueError(
            "reversed Patera section markers; repair them before regenerating"
        )
    return existing[:start] + block + existing[end + len(END) :]


def _check_destination(root: Path, relative: str) -> Path:
    target = root / relative
    # Do not follow symlinks or Windows junctions, even when --force is used.
    for path in (target, *target.parents):
        if path == root:
            break
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"{relative}: linked destinations are not supported")
        if path != target and path.exists() and not path.is_dir():
            raise ValueError(f"{relative}: parent is not a directory")
    if target.exists() and not target.is_file():
        raise ValueError(f"{relative}: destination is not a regular file")
    return target


def generate_agents(
    root: Path, agent: str = "codex", *, dry_run: bool = False, force: bool = False
) -> int:
    """Preflight all files, then create/update guidance in the given directory."""
    if agent not in (*PROFILES, "all"):
        raise ValueError(f"Unknown agent: {agent}")
    root = root.resolve()
    profiles = tuple(PROFILES) if agent == "all" else (agent,)
    resources = files("patera.cli").joinpath("agent_templates")
    planned: dict[str, tuple[str, bool]] = {}
    for profile in profiles:
        instruction_file, skill_path = PROFILES[profile]
        body = (
            "@AGENTS.md\n"
            if agent == "all" and profile == "claude"
            else _instructions(skill_path)
        )
        planned[instruction_file] = (body, True)
        planned[f"{skill_path}/SKILL.md"] = (
            resources.joinpath("SKILL.md").read_text(encoding="utf-8"),
            False,
        )
        for reference in sorted(
            resources.joinpath("references").iterdir(), key=lambda p: p.name
        ):
            if reference.is_file() and reference.name.endswith(".md"):
                planned[f"{skill_path}/references/{reference.name}"] = (
                    reference.read_text(encoding="utf-8"),
                    False,
                )

    changes: list[tuple[Path, bytes]] = []
    reports: list[str] = []
    conflicts: list[str] = []
    for relative, (content, instruction) in planned.items():
        try:
            target = _check_destination(root, relative)
            previous = target.read_bytes() if target.exists() else None
            if instruction:
                content = _merge_instructions(
                    previous.decode("utf-8") if previous is not None else "", content
                )
            desired = content.encode("utf-8")
            if previous == desired:
                reports.append(f"Unchanged {relative}")
            elif previous is not None and not instruction and not force:
                conflicts.append(
                    f"{relative}: differs from bundled guidance (use --force to replace)"
                )
            else:
                reports.append(
                    f"{'Update' if previous is not None else 'Create'} {relative}"
                )
                changes.append((target, desired))
        except (OSError, UnicodeError, ValueError) as exc:
            conflicts.append(f"{relative}: {exc}")
    if conflicts:
        for conflict in conflicts:
            print(f"Conflict: {conflict}", file=sys.stderr)
        print("No files written.", file=sys.stderr)
        return 1
    for report in reports:
        print(("[dry-run] " if dry_run else "") + report)
    if not dry_run:
        for target, payload in changes:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    print(f"{'Would write' if dry_run else 'Wrote'} {len(changes)} file(s) in {root}")
    return 0


def configure_agents_parser(parser: argparse.ArgumentParser) -> None:
    parser.description = (
        "Generate Patera instructions and skills in the current directory."
    )
    parser.add_argument("agent", nargs="?", default="codex", choices=[*PROFILES, "all"])
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing files"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace conflicting Patera skill files; preserve other instructions",
    )


def run_agents(
    root: Path,
    command: str,
    agent: str = "codex",
    *,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    try:
        return generate_agents(root, agent, dry_run=dry_run, force=force)
    except (OSError, ValueError) as exc:
        print(f"patera agents: {exc}", file=sys.stderr)
        return 1
