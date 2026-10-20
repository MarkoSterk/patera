# Quick Exams

A complete Patera example with an instructor workspace, Patera Admin, and
public student exams. It uses Patera controllers and services, `patera-database`
repositories with `@transactional` request sessions, `patera-migrate`,
`patera-auth` with stateless JWT access tokens, and `patera-admin`. The browser
UI is a Jinja page with plain JavaScript; no frontend build or external QR
service is needed.

## Run

From `examples/quick_exams`, with the repository's virtual environment
(or `uv sync` for an independent installation):

```powershell
../../.venv/Scripts/patera.exe cli migrate:init
../../.venv/Scripts/patera.exe cli migrate:migrate
../../.venv/Scripts/patera.exe cli migrate:validate
../../.venv/Scripts/patera.exe cli users:create instructor@example.com both
../../.venv/Scripts/patera.exe dev
```

Open <http://localhost:3000>. `patera dev` and `patera cli` load the first of
`.env`, `.env.dev` and `.env.local` they find in the current folder. The
`.env.dev` file is ready for local development: it has a development
secret key and uses a separate `exams.dev.sqlite3` database. Never use it
elsewhere.

For any other environment, copy `.env.example` to `.env` (which takes
precedence and is ignored by Git) and set your own values. The application
refuses to start without a `PATERA_SECRET_KEY` of at least 32 characters;
generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### Settings

Every field of `app/configs.py` can be set from the environment or `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PATERA_SECRET_KEY` | (required) | Signs the JWT access tokens. |
| `PATERA_PUBLIC_URL` | `http://localhost:3000` | Origin used in exam QR codes; `https://` also makes the auth cookie Secure. |
| `PATERA_EXAMS_DB__DATABASE_URI` | `sqlite+aiosqlite:///…/examples/quick_exams/exams.sqlite3` | The exams database. |
| `PATERA_EXAMS_DB__SQLITE_FOREIGN_KEYS` | `true` | Enforce foreign keys on SQLite; the schema's cascades and restrictions rely on it. |
| `PATERA_JWT_LIFETIME_SECONDS` | `28800` (8 hours) | How long a sign-in lasts. |

For students on other devices, use a reachable host and set `PATERA_PUBLIC_URL`
to that origin. Use HTTPS for a hosted deployment and apply login and request
rate limits at the reverse proxy.

### Create users with the Patera CLI

```sh
patera cli users:create teacher@example.com instructor
patera cli users:create administrator@example.com admin
patera cli users:create owner@example.com both
```

The role defaults to `instructor` and is case-insensitive. The command prompts
for the password (12+ characters) and a confirmation; passwords are never
command-line arguments. Duplicate emails, unknown roles, short passwords and
mismatched confirmations fail without creating a user. The command
(`app/cli/users_cli.py`) runs in a database session opened by `@cli_session`.

## Structure

```
app/
  __init__.py          App: extensions and services
  configs.py           typed settings (Config)
  database.py          ExamsDb (SqlDatabase + Migrate) and its manager
  models/              ORM models; Admin hooks delegate to the services
  repository/          Repository subclasses with the queries
  schemas/             Pydantic request and response bodies
  errors.py            domain errors, free of HTTP
  exceptions/          ExamExceptionHandler: maps domain errors to HTTP responses
  services/            accounts (passwords, JWT), authoring, attempts, reports
  api/                 JSON controllers
  public/              the HTML page
  middleware/          JwtAuthentication, BrowserSecurity
  cli/                 users:create
  migrations/          versioned SQL for Patera Migrate
tests/                 pytest suite (PateraTestClient)
```

## Authentication

Staff sign in at `POST /api/auth/login`. The response contains a signed JWT
(HS256, `PATERA_SECRET_KEY`), and the same token is set in an HttpOnly,
SameSite=Strict cookie so the browser UI and Patera Admin never handle the
token in JavaScript. API clients send `Authorization: Bearer <token>`.

There is no server-side session store. `JwtAuthentication`
(`app/middleware/auth_middleware.py`) is a `patera-auth` `Authentication`
middleware: for every endpoint marked `@login_required` or `@role_required`,
it verifies the token's signature and expiry and loads the user. The user's
database row decides on every request:

- roles are read from the database, so a role change takes effect at once;
- the token carries the user's `token_version`; changing a password (in the
  workspace or in Patera Admin) increments it and invalidates all earlier
  tokens of that user;
- a user without roles has no staff access and cannot sign in.

Signing out (`GET /api/auth/logout`, also used by Patera Admin's logout button)
removes the cookie. Because tokens are stateless, a token copied elsewhere stays
valid until it expires; keep the lifetime short for hosted deployments.

Passwords are hashed with `AuthUtils` (bcrypt over SHA-256). Werkzeug hashes
from earlier versions of this example still verify and are replaced with the
new format at the next sign-in.

`BrowserSecurity` rejects cross-site state-changing requests and marks API and
Admin responses `Cache-Control: no-store`. JSON endpoints use `@consumes`, so
other content types are answered with 415 and invalid bodies with 422.

## API

| Method and path | Access | Purpose |
| --- | --- | --- |
| `POST /api/auth/login` | public | Sign in; returns the token and sets the cookie. |
| `GET /api/auth/logout` | public | Remove the cookie. |
| `GET /api/auth/me` | signed in | The current user and roles. |
| `GET, POST /api/categories/`, `PUT, DELETE /api/categories/<id>` | INSTRUCTOR | Own categories. |
| `GET, POST /api/questions/`, `PUT, DELETE /api/questions/<id>` | INSTRUCTOR | Own questions. |
| `GET, POST /api/exams/`, `PUT, DELETE /api/exams/<id>` | INSTRUCTOR | Own exams. |
| `GET /api/exams/<id>/qr` | INSTRUCTOR | SVG QR code of the student link. |
| `GET /api/reports/` | INSTRUCTOR | Reports of own exams. |
| `GET /api/admin/overview` | ADMIN | Users, counts and all reports. |
| `POST /api/admin/users`, `PUT /api/admin/users/<id>` | ADMIN | Create and edit users. |
| `POST /api/attempts/` | public | Start an attempt (`exam_id`, `email`). |
| `POST /api/attempts/<id>/submit` | public | Submit answers; returns the score. |

Every endpoint that writes is `@transactional`: its request session commits
when the handler succeeds and rolls back when it raises. The generated OpenAPI
document is at `/openapi/docs`.

## Database and migrations

The database uses named relational columns. `app/models/` defines the ORM
models and `app/migrations/` creates their schema through Patera Migrate; the
application never creates or alters tables at startup.

| Table | Data |
| --- | --- |
| `users` | Email, password hash, INSTRUCTOR and ADMIN role flags, token version |
| `categories` | Instructor ID and category name |
| `questions` | Instructor/category IDs, question text, image, four answer columns, correct answer index, points |
| `exams` | Instructor ID, title, availability timestamps, pass percentage |
| `exam_questions` | Exam/question links and display position |
| `attempts` | Student email, timestamps, copied exam settings, grade |
| `attempt_questions` | Copied question text, image, answers and points, plus the student's selected answer |

`V1_1__stateless_jwt_auth.sql` removes the former `sessions` table and adds
`users.token_version`. An existing database is upgraded with
`patera cli migrate:migrate`; staff then sign in again once. Keep applied
migration files unchanged and add new versions for later changes.

Timestamps are ISO 8601 UTC strings. Foreign keys, unique constraints and checks
protect references, question ordering, answer indices and point values.
Archived source exam/question IDs intentionally have no foreign key to live
content. Deleting an exam removes its live question selection, while archives
remain intact. This small example uses SQLite and suits modest exam sizes and
traffic.

## Instructor workflow

1. Create categories, then questions. Each question has exactly four answers,
   one correct answer, a positive point value (default 1), and an optional
   PNG/JPEG/GIF/WebP image (up to 2 MB) stored with the question.
2. Create an exam with a title, opening and closing date/time, and a pass
   threshold (default 50%). Date/time inputs use the browser's timezone;
   storage and enforcement use UTC.
3. Select questions manually, or choose categories and generate a random set
   (default 10). The sample is drawn once when the exam is saved, so every
   student receives the same selection.
4. Expand **Share exam** to copy or open the link or download its SVG QR code.
5. Open **Reports** after submissions: count, pass rate, mean, minimum and
   maximum score, and each submission with its answers. Download a report as JSON.

Instructors see and change only their own records; another instructor's record
is answered with 404. A question used by a live exam must be removed from that
exam first, and a category must be empty before deletion (409). There is no
archive deletion API.

## Students and grading

Anyone with the unpredictable exam link can enter an email and start during the
availability window. The email is self-reported, not verified; repeat attempts
are allowed and reported separately. Starting copies the exam, its pass
threshold, deadline, questions, images and answer keys into the archive, so
later edits or deletion of the live exam do not change a started attempt.

Students select one answer for every question and submit before the copied
deadline. Scores are weighted by question points; an answer earns all of its
question's points or none. Answer keys are never sent to students. Submission
uses the random 192-bit attempt id kept only in page memory and returns only
that attempt's score; repeating a submission returns the same result.
Refreshing an unfinished student page starts a new attempt.

## Administration

The **Admin** link in the header opens Patera Admin at `/admin/en/dashboard`
(or `/admin`). Its sign-in page and logout button use the same JWT endpoints,
configured by `Config.ADMIN`. Users with the ADMIN role receive every Admin
permission; an INSTRUCTOR without ADMIN is sent to Admin's "unauthorized" page.

All seven models are registered under **Databases → Quick Exams**. Admin forms
go through the models' `admin_clean` hooks, which call the same service rules as
the API: owners cannot change, questions must use their owner's categories,
exam windows must be valid, and the last administrator cannot be demoted.
A password typed into the User form is hashed and invalidates the user's
existing tokens. Archived attempts allow email corrections only; their copied
questions are immutable and cannot be deleted.

The models override two generated inputs with `Meta.custom_form_fields`. A
question's image is a `FileInput`: the uploaded file is checked by its content
(PNG, JPEG, GIF or WebP, up to 2 MB) and stored as a data URL. An update
without a new file keeps the image, and **Remove the current image** clears
it. An exam's availability uses `DateInput` date-and-time pickers in the
administrator's local time; the values are stored in UTC.

The workspace's **Users & reports** view lists users and counts, creates and
edits users and roles, and shows all archived reports. Remove both roles to
disable a user's staff access. Keep report exports and the database private:
they contain student email addresses and answer keys.

## Tests

From `examples/quick_exams`:

```powershell
../../.venv/Scripts/python.exe -m pytest -q
```

An independent installation needs the test tools first: `pip install "patera[testing]"`.

The tests run the application through `PateraTestClient` with a migrated
temporary database. They cover JWT sign-in by cookie and bearer token, expired
and forged tokens, token invalidation on password and role changes, role
checks, cross-origin and content-type protection, ownership, student answer-key
privacy, validation, snapshot isolation, availability windows, weighted grades,
archive retention, Admin CRUD through the domain rules, the CLI, the upgrade of
legacy password hashes, and the OpenAPI document.
