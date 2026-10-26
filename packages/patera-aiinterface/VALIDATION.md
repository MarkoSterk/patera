# AI extension validation

Validated on Windows on 2026-10-26. All inference used local services; no paid
provider calls were made.

## Environment and results

- Python 3.13.13: combined AI checks with local integrations — 117 passed,
  one skipped (the missing-extra test, because augmentation is installed).
- Python 3.14.5: full framework suite before installing augmentation —
  784 passed, six skipped. Opt-in model/service tests were run separately.
- Python 3.14.5 with augmentation installed: the combined AI run also passed
  117 tests, with only the missing-extra test skipped.
- PostgreSQL 17.11 with pgvector 0.8.7: document search, history, summaries,
  overlapping transactions, and real spawned-process contention passed on
  Python 3.13 and 3.14 (39 SQLite/PostgreSQL tests per run).
- Real `sentence-transformers/all-MiniLM-L6-v2`: lazy loading, document
  ingestion, retrieval, model reuse and a second provider loading the cached
  model passed with networking disabled, on SQLite and PostgreSQL.
- Ollama 0.40.11 with `qwen2.5:0.5b`: completion, streaming, finish reasons,
  token usage and JSON output passed through both the native API and its
  OpenAI-compatible endpoint.
- Ruff and mypy passed. The full suite emits upstream websocket deprecation
  warnings; no test failure resulted.

## Fixes from these checks

Closing or cancelling an AI service stream now explicitly closes the underlying
provider iterator. The built-in providers reject streams that end without their
protocol's completion marker (`[DONE]` for OpenAI, `done` for Ollama). Ollama
stream error objects raise an error instead of becoming empty answer chunks.
Incomplete answers are not saved in history.

Regression tests cover fragmented UTF-8 and JSON, early close, cancellation,
truncation, malformed JSON, HTTP 401/429/500/503, connection errors and timeouts.
Transport/status errors are simulated deterministically; they are not claims
about a hosted provider's actual rate limits. `MAX_RETRIES` still applies to
connection establishment, not HTTP status codes or replaying interrupted streams.

The previous test named `test_two_worker_processes_do_not_collide` used two
application engines in one process. It was renamed accurately, and a separate
test now starts two Python processes, synchronizes their start, and checks
message ordering and pairing after concurrent writes.

## Repeat the local checks

Use a dedicated disposable PostgreSQL database: these fixtures create and drop
their own test tables. Enable its `vector` extension before running tests.
The containers used for this run are `patera-ai-audit-postgres` (port 55432)
and `patera-ai-audit-ollama` (port 11435), bound to loopback only.

After starting those containers, run from the repository root in PowerShell:

```powershell
$env:PATERA_TEST_PG_URI = 'postgresql+asyncpg://postgres:patera-audit-only@127.0.0.1:55432/patera_ai_audit'
$env:PATERA_TEST_OLLAMA_URL = 'http://127.0.0.1:11435'
$env:PATERA_TEST_OLLAMA_MODEL = 'qwen2.5:0.5b'
$model = Get-ChildItem '.cache/ai-models/models--sentence-transformers--all-MiniLM-L6-v2/snapshots' -Directory | Select-Object -First 1
$env:PATERA_TEST_EMBEDDING_MODEL = $model.FullName
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
.venv/Scripts/python.exe -m pytest tests/extensions -k aiinterface -q -rs
# Python 3.14 environment prepared during validation:
.cache/ai-py314/Scripts/python.exe -m pytest tests/extensions -k aiinterface -q -rs
```

The model test expects MiniLM's 384-dimensional vectors. The local provider tests
accept only loopback hosts. When their environment variables are unset, these
tests skip rather than downloading models or contacting services automatically.

## Remaining scope

OpenAI's hosted service, real hosted authentication/rate limiting, and Linux/macOS
application runs were not tested here. OpenAI compatibility against Ollama does
not establish those results. The CI operating-system matrix remains the check
for platform portability. This is functional release validation, not a sustained
load test or model-quality evaluation.

Application owners must still authorize access to history session IDs and apply
document ownership filters. Provider isolation tests do not add an authorization
policy to application code.
