# Scheduled and background work

Install `patera-taskmanager`.

```python
from typing import TYPE_CHECKING

from patera.taskmanager import TaskManager, schedule_job

if TYPE_CHECKING:
    from app import App


class Jobs(TaskManager["App"]):
    @schedule_job("interval", seconds=60, id="heartbeat", max_instances=1)
    async def heartbeat(self):
        self.app.logger.info("Heartbeat")
```

Register Jobs in `app_extensions`; declare `JOBS: TaskManagerConfig` when
configuring it. The default AsyncIOScheduler starts/stops through lifespan; app
construction alone does not run jobs. Decorator arguments go to APScheduler.
Use explicit timezones for calendar triggers. Job IDs and replace_existing avoid
duplicate registration in a scheduler, not execution across worker processes.

Jobs have no HTTP request session. Use explicit database sessions or
`@background_session("database_name")` from `patera.database.sql`, placed below
`@schedule_job`, to give repositories a managed session scope. Keep operations
idempotent and add claims/locking when multiple workers can run them.

Default in-memory stores/executors are per instance. If supplying your own mutable
stores/executors, construct them per instance when applications must be isolated.
Persistent stores serialize jobs; do not pass arbitrary app-bound state as job
arguments. Inspect pause/resume/run-now APIs when exposing operations.

For short local work, core `run_in_background` tracks tasks and shutdown waits up
to `BACKGROUND_TASKS_SHUTDOWN_TIMEOUT`. It is not a durable queue. Pass plain data
and acquire fresh resources; copied context does not extend a request session's
lifetime. Sync functions are not automatically safe for blocking I/O on the loop.

Sources: tutorial chapters 6 and 13; architecture chapter 18.
