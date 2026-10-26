# Coding agents

Patera can generate instructions and a Patera skill for AI coding agents such as Codex and
Claude. Run the command from the project directory, even before an application exists:

```sh
patera agents             # AGENTS.md and .agents/skills/patera/
patera agents claude      # CLAUDE.md and .claude/skills/patera/
patera agents all         # both layouts; CLAUDE.md imports AGENTS.md
patera agents all --dry-run
```

The bundled skill covers application construction, configuration, injection, controllers,
requests and responses, middleware, errors, CLI controllers, WebSockets, templates, logging,
testing, deployment, custom extensions and all official extension packages. Its `SKILL.md`
routes to focused reference files. Generation works offline from the installed package and does
not require the optional extensions.

## Behaviour

- Existing instruction files keep their content outside a marked Patera section.
- Repeated runs skip identical files.
- A conflicting skill file stops generation before any writes; use `--force` to replace the
  bundled files deliberately. Unrelated files are preserved.
- `--dry-run` never writes, even with `--force`.
- Malformed section markers and linked destinations require manual repair and are not bypassed by
  `--force`.
- The command writes to the current directory, without searching for an app or loading
  environment files. The application options `--app`, `--env-file` and `--list` do not apply.
