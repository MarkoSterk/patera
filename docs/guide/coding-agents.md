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

## Application conventions

- Type backend controllers and application-specific extensions with the concrete
  application class, for example `Controller["App"]` and
  `BaseExtension["App", AuditConfig]`. Import `App` under `if TYPE_CHECKING:`
  to avoid circular imports. Keep config models and injected classes available
  at runtime.

- Use named members of `patera.HttpStatus` wherever application code specifies or
  compares an HTTP status, including decorators, exceptions and test assertions.
  For example, write `assert response.status_code == HttpStatus.OK`.
- Put application setting values in `.env`, including defaults and nested extension
  settings. Declare custom fields on `Config` with type annotations only. Assign a
  value there only when it requires Python, such as `REQUEST_CLASS` or
  `RESPONSE_CLASS`, or is more practical to compute, such as `BASE_PATH` derived
  from `__file__`.
- Group related utility functions in a purpose-specific class and define each
  with `@staticmethod`. Avoid standalone utility functions.

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
