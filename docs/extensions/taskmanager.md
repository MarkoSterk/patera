# Task manager

`patera-taskmanager` schedules jobs with [APScheduler](https://apscheduler.readthedocs.io/en/3.x/).

```sh
uv add "patera[taskmanager]"
```

```python
from patera.taskmanager import TaskManager, schedule_job


class Jobs(TaskManager):

    @schedule_job("interval", minutes=5, id="cleanup")
    async def cleanup(self) -> None:
        self.app.logger.info("Cleaning up")

    @schedule_job("cron", hour=3, id="nightly")
    async def nightly(self) -> None: ...
```

Register `Jobs` in `app_extensions`; the scheduler starts and stops with the application
lifespan (constructing the app alone does not run jobs). Decorator arguments go to APScheduler;
use explicit timezones for calendar triggers.

- A job without an `id` gets `<class>.<method>` (`Jobs.cleanup`).
- A job is replaced at every start, so it is never stored twice.

## Settings

```python
from patera.taskmanager import TaskManagerConfig

class Config(BaseConfig):
    ...
    JOBS: TaskManagerConfig = TaskManagerConfig(NICE_NAME="Jobs", DAEMON=True)
```

## Runtime API

| Method | Description |
| --- | --- |
| `add_job(func, trigger, **kwargs)` | add a job |
| `remove_job(job)`, `pause_job(job)`, `resume_job(job)` | manage a job |
| `run_job_now(job)` | run a job immediately |
| `get_job(id)`, `jobs` | look up jobs |
| `is_job_running(job)` | state |
| `run_background_task(func, *args)` | fire-and-forget work |

Customize the scheduler with the class attributes `scheduler_cls`, `job_stores`, `executors` and
`job_defaults`.

## Database access in jobs

Jobs have no HTTP request session. Use explicit sessions or `@background_session("main")` from
`patera.database.sql`, placed **below** `@schedule_job`, to give repositories a managed session:

```python
from patera.database.sql import background_session


class Jobs(TaskManager):
    notes: Inject[NoteRepository]

    @schedule_job("interval", hours=1, id="purge")
    @background_session("main")
    async def purge(self) -> None:
        ...
```

## Persistent job stores

With a job store that keeps jobs outside the process, such as `SQLAlchemyJobStore`, declared jobs
and task manager methods passed to `add_job()` are stored by name and find the running task
manager when they run.

- Set `TaskManagerConfig(JOB_NAMESPACE="my-app-jobs")`. Keep the namespace stable across
  restarts and unique for separate applications or stores using the same manager class.
- An empty namespace preserves existing stored job identifiers, but only one such manager may be
  active per process. A duplicate fails at startup instead of redirecting jobs to another app.
  Registrations are removed at shutdown.
- Separate applications need separate job store instances; do not share a store object.
- Persistent stores serialize jobs; do not pass application-bound state as job arguments.

## Several workers

Job IDs prevent duplicate registration within one scheduler, **not** execution in several
processes. With several workers, choose one scheduler owner or add distributed coordination, and
keep jobs idempotent.

For short in-process work without scheduling, the core `run_in_background()` is enough; see
[The application class](../guide/application.md#background-tasks).
