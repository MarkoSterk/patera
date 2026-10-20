# Quick Exams

A complete Patera example with an instructor workspace, an administration view,
and public student exams. Uses Patera controllers, Jinja, plain JavaScript and
SQLite. No external QR service or frontend build is needed.

## Run

From the repository root, install the example's additional dependency:

```powershell
uv pip install --python .venv/Scripts/python.exe -r examples/quick_exams/requirements.txt
cd examples/quick_exams
../../.venv/Scripts/patera.exe cli users:create instructor@example.com both
../../.venv/Scripts/patera.exe dev
```

The CLI command prompts for a password (at least 12 characters) and confirmation.
The example above creates both `ADMIN` and `INSTRUCTOR`. There are no default credentials.
Open <http://localhost:3000>. For an independent installation, install
`requirements.txt`, then run `patera cli users:create instructor@example.com both` and `patera dev`.

### Create users with the Patera CLI

From `examples/quick_exams`, with `patera` available in your environment:

```sh
patera cli users:create teacher@example.com instructor
patera cli users:create administrator@example.com admin
patera cli users:create owner@example.com both
```

The role defaults to `instructor` when omitted and is case-insensitive. Duplicate
email addresses, unknown roles, short passwords and mismatched confirmations fail
without creating or overwriting a user. Passwords are never command-line arguments.
The controller is `app/cli/users_cli.py`. `manage.py` remains a compatibility wrapper
with its original default of both roles.

Set these environment variables before starting, as appropriate:

| Variable | Default | Purpose |
| --- | --- | --- |
| `QUICK_EXAMS_DB` | `examples/quick_exams/exams.sqlite3` | Persistent SQLite file; back it up to retain archives. |
| `QUICK_EXAMS_PUBLIC_URL` | `http://localhost:3000` | Externally reachable origin used in QR codes, e.g. `https://exams.example.com`. |

For students on other devices, use a reachable host and set `QUICK_EXAMS_PUBLIC_URL`
to that same origin. A localhost QR code only works on the server's own device.
Use HTTPS for a hosted deployment and apply login/request rate limits at the reverse
proxy. This deliberately small example uses synchronous SQLite transactions and is
intended for modest exam sizes and traffic.

## Instructor workflow

1. Create categories, then questions. Each question has exactly four answers, one
   correct answer, a positive point value (default 1), and an optional uploaded
   PNG/JPEG/GIF/WebP image (up to 2 MB). Images are stored with the question.
2. Create an exam with a title, opening and closing date/time, and a pass threshold
   (default 50%). Date/time inputs use the instructor's browser timezone; storage
   and server enforcement use UTC.
3. Select questions manually, or choose categories and generate a random set
   (default 10). Generation samples distinct questions once when saving the exam;
   students receive that same selection. Insufficient pools produce an error.
4. Expand **Share exam** to copy/open the link or download its generated SVG QR code.
5. Inspect **Reports** after submissions. Reports show submission count, pass rate,
   mean, minimum and maximum score; expand a submission to see its email, timestamp,
   answers and complete question copy. Download the full archive as JSON.

Questions, categories and exams can be edited or deleted. A question used by a live
exam must first be removed from that exam (or the exam deleted); categories must be
empty before deletion. Archive records never reference live questions for their
content and there is intentionally no archive deletion API.

## Students and grading

Anyone with the unpredictable exam link can enter an email and start during the
availability window. Email is self-reported, not verified; repeat attempts are
allowed and reported separately. Starting freezes the exam, its pass threshold,
deadline, questions, images and answer keys in a private snapshot. Later edits or
deletion of the live exam do not change an already started attempt.

Students must select one radio answer for every question and submit before the
frozen deadline. There is no separate duration timer. Scores are weighted by question
points; an answer earns all of its question's points or zero. Passing uses the exact
percentage, while the screen displays one decimal place.

The server never sends answer keys to students. Submission uses a random 192-bit
attempt capability kept only in page memory; it returns only that attempt's score.
There is no public result list or lookup by email. Repeating the same submission is
idempotent. Refreshing an unfinished student page starts a new attempt, so students
should keep the page open until submission. Reports count submitted attempts only.

## Administration and access

The **Admin** link opens the actual `patera-admin` extension at `/admin/en/dashboard`
(or enter through `/admin`). It provides the standard logs and file explorer panels,
plus panels for configured supported extensions. `app/admin.py` registers it and
`SessionAuthentication` maps the app's `ADMIN` role to the extension's permissions.
An INSTRUCTOR without ADMIN cannot enter. No raw SQLite archive records are exposed
through editable admin database models.

The **Users & reports** view lists users and system counts, creates users, changes passwords,
assigns either/both roles, and inspects all archived reports. Remove both roles to
disable a user's staff access. The last administrator cannot lose their ADMIN role.
Only INSTRUCTOR accounts can author content; instructors manage their own content
and reports. ADMIN alone provides administration and all-report access. Links in
the extension footer lead back to the instructor workspace and Users & reports.

Passwords use Werkzeug's salted password hashes. Staff sessions expire after eight
hours, are stored in the database, and use a shared HttpOnly, SameSite=Strict cookie
for the workspace and extension. Set `QUICK_EXAMS_PUBLIC_URL` to an HTTPS origin for
Secure cookies in a hosted deployment. The API also accepts bearer tokens for clients.
JSON API mutations require application/json and reject cross-origin requests;
extension mutations also reject cross-origin requests.
Password changes revoke existing sessions; role checks use current database values
on every request. Sign out revokes the current token. Keep report exports and the
database private: they contain student email addresses and answer keys.

## Tests

From the repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_quick_exams.py -q
```

Tests exercise Patera routing, authorization, student answer-key privacy, validation,
snapshot isolation, archive retention, random selection and availability enforcement.
