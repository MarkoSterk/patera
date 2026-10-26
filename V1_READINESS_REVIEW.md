# Patera v1 readiness review

Reviewed 2026-10-26: core 0.123.0 and all 12 workspace extensions. Most
extensions are 0.13.0; desktop-ui is 0.3.0 and joltui is 0.2.0.

## Resolution update

The findings below are the original audit record. All six reproduced bugs and
the desktop shutdown race have now been addressed, with JoltUI handled last.

| Finding | Resolution |
| --- | --- |
| POST caching | GET/HEAD default, explicit method opt-in, body digest, qualified handler keys, callable keys |
| Persistent jobs | Stable configurable namespace, duplicate rejection, lifecycle registration/cleanup |
| Failed initialization | Rollback of framework registrations and injection rejection of initializing instances |
| Injection overrides | Local declarations and ordinary overrides follow MRO order |
| API client lifetime | Temporary clients outside lifespan; shared lifespan client; explicit cross-loop misuse rejected |
| Desktop shutdown | Capture child identities before signaling; wait and kill with bounded child cleanup |
| JoltUI error responses | Preserve structured errors; continue enforcing HTML on successful responses |
| Naming/metadata | PUBLIC_API.md, public MigrateConfig alias, desktop-ui extra, metadata and JoltUI brand consistency |
| Release checks | RC/final explicit versions, browser syntax check, isolated wheel install script and CI matrix |

Post-fix validation: **748 passed, 1 skipped**, Ruff passed, mypy passed for
130 native source files, and the Pyodide bootstrap syntax check passed. All
13 packages built as wheels/sdists and passed strict metadata validation.
All 13 wheels also installed and imported together in a fresh environment,
including checks for the packaged browser bootstrap and agent skill assets.
Two existing upstream websocket deprecation warnings remain.

The matrix is configured for Windows/Linux/macOS and Python 3.13/3.14; this
workspace run verifies Windows/Python 3.13 only. No release was published and
package versions and maturity commitments were not promoted to 1.0.

### Original assessment

Recommendation: complete a stabilization pass before declaring the reviewed
packages stable. The API is coherent enough that a wholesale rename is not
necessary, but the correctness issues below deserve regression tests and fixes.
Core 1.0 does not require every experimental extension to become 1.0 with it.

## Confirmed correctness issues

Severity: P1 means prioritize before stable release; P2 means a concrete bug
with a narrower trigger. Six isolated reproductions pass by asserting the
current incorrect behavior. They are audit probes, not tests of desired behavior.

### 1. P1: POST response caching ignores the request body

Location: `packages/patera-caching/src/patera/caching/cache.py:170`.

`@cache` accepts POST handlers, but its default key contains only the function
name, HTTP method, path, query string, and optional user identity. Two POSTs to
the same handler with bodies `{"id": 1}` and `{"id": 2}` both receive the first
response. A cache hit also skips the handler's work.

This directly affects JolUI, where route parameters and component data travel
in the JSON body of a shared POST endpoint. The short function name also fails
to distinguish same-named methods in different groups sharing that endpoint.

Recommended fix: default to caching safe read methods only, and make POST
caching an explicit opt-in with a body-aware, handler-qualified key. Support a
callable key builder so application-specific variations can be represented.
Document that user identity alone does not cover headers or other varying data.

### 2. P1: persistent task dispatch can select another application

Locations: `packages/patera-taskmanager/src/patera/taskmanager/task_manager.py:53`,
`:71`, and `:137`.

`_TASK_MANAGERS` is process-global and keyed only by the manager class's module
and qualified name. Constructing two apps using the same manager class replaces
the first registration with the second. Calling the dispatcher used by persisted
jobs then invokes the second application's manager, even for a job belonging
to the first. This can run work against the wrong configuration or database.

The default in-memory job path uses bound methods and is not the affected path.
The reproduction calls the persistent-job dispatcher directly; it does not
require an external job-store server.

Recommended fix: give persistent managers an explicit stable application/job-store
namespace, reject ambiguous duplicate registrations, and clean up registrations
at shutdown. A random per-process identifier alone would break persisted jobs
across restarts.

### 3. P2: a failed extension remains registered and is later reused

Location: `src/patera/base_extension.py:21`.

The constructor calls `app.add_extension(self)` before `self.init()`. If `init()`
raises and a caller catches the error, later injection finds the partially
initialized object and succeeds without retrying initialization. Reproduced by
injecting an extension whose `init()` always raises: first consumer fails;
second consumer receives the broken extension, with only one initialization attempt.

Recommended fix: track initializing versus ready instances and roll back the
registration on failure. Preserve dependency-cycle detection and account for
initialization side effects such as registered middleware and callbacks.

### 4. P2: JolUI converts normal decorator error responses into exceptions

Location: `packages/patera-joltui/src/patera/joltui/interface.py:88`.

An ordinary `@consumes(...)` decorator returns a JSON 415 response for an
unsupported media type. JolUI's unconditional HTML-response check rejects that
response with `TypeError`, turning the intended client error into a server error
(the test transport surfaces the exception). This conflicts with normal endpoint
decorator compatibility.

Recommended fix: distinguish successful component output from framework-generated
error responses. Keep successful handlers returning HTML `Response` objects;
preserve decorator status codes, or deliberately render their errors as HTML
without replacing them with a 500. Test both decorator orders and lifecycle hooks.

### 5. P2: overriding an inherited injection does not remove it

Location: `src/patera/injectable.py:138`.

An inherited `dependency: Inject[Dependency]` survives a subclass declaration
`dependency: str = "disabled"`. The annotation merge only adds injections; it
does not remove overridden declarations. Instantiation silently overwrites the
string with a dependency instance. This differs from the override handling of
JolUI component-group annotations.

Recommended fix: remove inherited injection metadata for explicitly overridden
attributes before merging local injections. Define and test both annotated and
unannotated overrides, including multiple inheritance.

### 6. P2: switching event loops abandons the previous API client

Location: `packages/patera-apiinterface/src/patera/apiinterface/api_interface.py:518`.

The `client` property creates another HTTPX client when the running event loop
changes, replacing the only reference to the previous client. `aclose()` closes
only the latest one. Reproduced with two `asyncio.run()` invocations: after
`api.aclose()`, the first client remains open and the second is closed.

The docstring explicitly supports different loops for CLI calls, so this is a
supported-use-case lifetime gap. The probe verifies client state without making
network requests; resource leakage depends on actual client use.

Recommended fix: close clients within their owning loop's lifecycle. Merely
collecting old clients and closing them after their loops have stopped is not
a reliable fix for live asynchronous connections.

## Reproduced Windows shutdown failure

Location: `packages/patera-desktop/src/patera/desktop/desktop.py:235`.

`test_a_real_server_starts_answers_and_stops[dev]` fails in the full suite and
when rerun alone. `stop_server()` waits for the parent process, but a connection
to the worker's port can still succeed immediately after it returns. A subsequent
inspection found no listener on the test ports. This supports a shutdown race,
not a claim that the worker remains alive permanently.

Recommended fix: make completion include child-process/listener shutdown, with
a bounded timeout and process-tree fallback. Verify repeated start/stop cycles
on Windows. The corresponding production-server test passed in this run.

## Naming and public API decisions

These are consistency and discoverability issues, not runtime failures. Preserve
existing names with aliases/deprecations if changing them.

| Area | Current names | Recommendation before freezing the API |
| --- | --- | --- |
| AI extension | Distribution/import `patera-aiinterface` / `patera.aiinterface`, main class `AiService` | Explain the mapping clearly, or provide a deliberate alias. Avoid a disruptive package rename solely for symmetry. |
| JolUI extension | `PateraJoltui`, `JoltuiConfig`, `JoltuiGroupHandler` | Decide whether the vendor prefix is intentional; other extension entry classes do not have it. The original requested name was `PateraJoltui`, so this is a choice, not an implementation mistake. |
| Acronyms | `ApiInterface`, `AiService`, `SqlDatabase`, but `DesktopUI` | Document one convention for future names. Existing readable names do not all need renaming. |
| Config models | `EmailClient` / `EmailConfig`, `AdminInterface` / `AdminConfig`, `AiService` / `AiServiceConfig` | Choose role-based or exact-class-based naming for new APIs; list current pairs in the extension guide. |
| Migrations | Configuration model is private `_PateraPywayConfigs` | Decide whether typed migration configuration is a public supported API; expose a stable model if so. |
| SQL imports | SQL types are exported from `patera.database.sql`, not `patera.database` | Keep examples consistent with the intentional SQL submodule boundary. |
| Installation extras | `patera[all]` excludes AI, desktop and desktop-ui; no core `desktop-ui` extra | Define what “all” promises. Document its selected scope or offer an explicitly named complete bundle. |
| Brand | Prose uses `JolUI`; distribution/import uses `joltui` | Use the author's chosen brand consistently in prose and keep the established code spelling explicit. |

JolUI and desktop-ui also lack the author, project URL and maturity classifiers
present in the older packages. Complete their PyPI metadata before public
promotion. Core and most packages currently say Beta; AI and desktop say Alpha.
Only change maturity classifiers for packages actually covered by the stability
commitment.

## Original verification and scope

| Check | Result |
| --- | --- |
| Full pytest suite | 732 passed, 3 failed, 1 skipped; 2 dependency deprecation warnings |
| Isolated audit probes | 6 passed, each confirming one bug described above |
| Desktop dev shutdown rerun | Failed again |
| Ruff across `src` and `packages` | Passed |
| Broad mypy invocation | 2 errors, both in browser-only Pyodide bootstrap |
| Release build dry-run | Passed; discovered core plus all 12 extensions in dependency order |

The other two pytest failures are
`test_run_in_window_loads_the_installation_settings` and
`test_run_in_window_works_without_a_settings_file`. They spoof `sys.platform`
as Linux on Windows; Loguru's enqueue setup then enters POSIX multiprocessing
and cannot import `_posixsubprocess`. Fix the platform simulation in the tests
(or isolate logging setup) rather than treating these as Linux runtime failures.

The broad mypy command was `mypy src/patera packages --follow-imports=silent`.
The errors concern the browser `js` module and top-level `await` in
`packages/patera-desktop-ui/src/patera/desktop/ui/assets/bootstrap.py`.
Configure a separate browser-source check; these are not evidence that the
Pyodide bootstrap is invalid in its intended runtime.

Review included core injection, routing/lifecycle and package configuration;
admin, AI/API interfaces, authentication, caching, SQL database, desktop,
desktop-ui, email, JolUI, migration and task-manager implementation paths;
and release tooling. No additional confirmed issue is asserted for packages
not named in the findings. Passing tests and source inspection do not establish
absence of bugs or constitute a security audit.

Validation ran on this Windows workspace with Python 3.13. It did not establish
Linux/macOS or Python 3.14 compatibility, test live external providers, or build
and install fresh release wheels into a clean environment. No packages were
published or versions changed.

## Suggested release sequence

1. Fix the confirmed bugs and add tests asserting the corrected behavior.
2. Resolve the Windows shutdown race and platform-dependent test failures.
3. Settle documented names, extras, package metadata and the stable/experimental
   package boundary. Retain compatibility aliases where appropriate.
4. Run the supported Python/OS matrix and clean wheel/sdist installation tests,
   including combined namespace-package installs and example applications.
5. Exercise a release candidate before the final 1.0 announcement. The current
   bump helper accepts only stable `major.minor.patch` versions, so RC versioning
   needs a deliberate workflow rather than assuming the helper supports it.

Local audit probes and logs are retained under `build/v1-audit/` (Git-ignored).
To rerun the probes from PowerShell:

```powershell
$env:PYTHONPATH='.;packages/patera-joltui/src'
.venv/Scripts/python.exe -m pytest -p tests.conftest build/v1-audit/v1_audit_repros.py -q -s
```

The original audit probes assert the old bugs. Use the corrected regression
tests under `tests/` to verify the fixes; the probes are retained only as history.
