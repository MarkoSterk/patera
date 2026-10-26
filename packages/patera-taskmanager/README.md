# patera-taskmanager

Scheduled and background jobs for Patera, based on APScheduler. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-taskmanager
# or, with uv
uv add "patera[taskmanager]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

For persistent job stores, set `TaskManagerConfig(JOB_NAMESPACE="my-app-jobs")`
on your manager's configuration. Keep the namespace stable across restarts and
unique for separate applications/stores using the same manager class. An empty
namespace preserves existing stored job identifiers, but only one such manager
may be active per process. A duplicate fails at startup instead of redirecting
jobs to another app. Registrations are removed at shutdown. Separate applications
also need separate job-store instances; do not share a store object between them.

`patera-taskmanager` schedules jobs with [APScheduler](https://apscheduler.readthedocs.io/en/3.x/):

```python
from patera.taskmanager import TaskManager, schedule_job


class Jobs(TaskManager):

    @schedule_job("interval", minutes=5, id="cleanup")
    async def cleanup(self) -> None:
        self.app.logger.info("Cleaning up")

    @schedule_job("cron", hour=3, id="nightly")
    async def nightly(self) -> None: ...
```

See the [Task manager section of the Patera documentation](https://github.com/MarkoSterk/Patera#task-manager) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
