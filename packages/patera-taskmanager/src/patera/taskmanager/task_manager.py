"""
Task manager class
"""

from typing import (
    Any,
    Callable,
    Generic,
    Tuple,
    Optional,
    Type,
    TypeVar,
    cast,
    TYPE_CHECKING,
)
from functools import wraps

from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError, BaseJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.base import BaseExecutor
from apscheduler.executors.asyncio import AsyncIOExecutor
from pydantic import BaseModel, Field

from patera.utilities import run_sync_or_async, run_in_background
from patera.base_extension import BaseExtension

if TYPE_CHECKING:
    from patera import Patera


class TaskManagerConfig(BaseModel):
    """Configuration model for TaskManager extension."""

    NICE_NAME: str = Field(
        "Task manager",
        description="Human readable name for the task manager for the admin dashboard",
    )
    DAEMON: bool = Field(
        default=True,
        description="Whether the scheduler should run as a daemon. Default True",
    )


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class TaskManager(BaseExtension[AppT, TaskManagerConfig], Generic[AppT]):
    """
    Task manager class for scheduling and managing background tasks.

    Scheduler configuration is declared on the class implementation:

    - scheduler
    - job_stores
    - executors
    - job_defaults

    Runtime configuration is loaded from application configs.
    """

    scheduler_cls: Type[BaseScheduler] = AsyncIOScheduler
    job_stores: dict[str, BaseJobStore] = {"default": MemoryJobStore()}
    executors: dict[str, BaseExecutor] = {"default": AsyncIOExecutor()}
    job_defaults: dict[str, bool | int] = {
        "coalesce": False,
        "max_instances": 3,
    }

    def init(self) -> None:
        """
        Initializes the TaskManager with the Patera app.
        """
        self._daemon: bool = True
        self._scheduler: BaseScheduler
        self._initial_jobs_methods_list: list[Tuple] = []
        self._active_jobs: dict[str, Job] = {}

        self._daemon = self.configs.DAEMON

        if not issubclass(self.scheduler_cls, BaseScheduler):
            raise TypeError(
                "scheduler_cls must be a class and subclass of BaseScheduler"
            )

        self._scheduler = self.scheduler_cls(
            jobstores=self.job_stores,
            executors=self.executors,
            job_defaults=self.job_defaults,
            daemon=self._daemon,
        )

        self._get_defined_jobs()
        self._app.add_on_startup_method(self._start_scheduler)
        self._app.add_on_shutdown_method(self._stop_scheduler)

    def pause_scheduler(self) -> None:
        """
        Pauses scheduler execution.
        """
        self.scheduler.pause()

    def resume_scheduler(self) -> None:
        """
        Resumes paused scheduler execution.
        """
        self.scheduler.resume()

    async def _start_scheduler(self) -> None:
        """
        Startup hook for starting the scheduler.
        """
        self.scheduler.start()
        self._start_initial_jobs()

    async def _stop_scheduler(self) -> None:
        """
        Shutdown hook for stopping the scheduler.
        """
        self.scheduler.shutdown()

    def _get_defined_jobs(self) -> None:
        """
        Finds methods decorated with @schedule_job.
        """
        for name in dir(self):
            method = getattr(self, name)

            if not callable(method):
                continue

            scheduler_method = getattr(method, "_scheduler_job", None)

            if scheduler_method:
                self._initial_jobs_methods_list.append(
                    (method, scheduler_method["args"], scheduler_method["kwargs"])
                )

    def _start_initial_jobs(self) -> None:
        """
        Starts all scheduled jobs declared with @schedule_job.
        """
        if not self._initial_jobs_methods_list:
            return

        for func, args, kwargs in self._initial_jobs_methods_list:
            job: Job = self.scheduler.add_job(func, *args, **kwargs)
            self._active_jobs[job.id] = job

        self._initial_jobs_methods_list = []

    def run_background_task(self, func: Callable, *args, **kwargs) -> None:
        """
        Runs a method in the background.

        This is useful for fire-and-forget work whose result does not need to
        be awaited before returning a response to the client.
        """
        run_in_background(func, *args, **kwargs)

    def add_job(self, func: Callable, *args, **kwargs) -> Job:
        """
        Adds a job manually.
        """
        job: Job = self.scheduler.add_job(func, *args, **kwargs)
        self._active_jobs[job.id] = job
        return job

    def remove_job(self, job: str | Job, job_store: Optional[str] = None) -> None:
        """
        Removes a job.

        :param job: Job ID or Job instance returned by scheduler.add_job().
        """
        if isinstance(job, Job):
            job = job.id

        self._remove_job(cast(str, job), job_store)

    def pause_job(self, job: str | Job) -> None:
        """
        Pauses a job.
        """
        if isinstance(job, Job):
            job.pause()
            return

        active_job: Optional[Job] = self._active_jobs.get(job, None)

        if active_job is None:
            raise JobLookupError(job)

        active_job.pause()

    def resume_job(self, job: str | Job) -> None:
        """
        Resumes a paused job.
        """
        if isinstance(job, Job):
            job.resume()
            return

        paused_job: Optional[Job] = self._active_jobs.get(job, None)

        if paused_job is None:
            raise JobLookupError(job)

        paused_job.resume()

    def get_job(self, job_id: str) -> Job | None:
        """
        Returns a job by ID.
        """
        return self._active_jobs.get(job_id, None)

    def _remove_job(self, job_id: str, job_store: Optional[str] = None) -> None:
        """
        Removes a job from the scheduler and active job list.
        """
        self.scheduler.remove_job(job_id, job_store)

        if job_id in self._active_jobs:
            del self._active_jobs[job_id]

    @property
    def jobs(self) -> dict[str, Job]:
        """
        Returns a dictionary of active jobs.
        """
        return self._active_jobs

    @property
    def scheduler(self) -> BaseScheduler:
        """
        Returns the scheduler instance.
        """
        return self._scheduler

    @property
    def app(self) -> AppT:
        """
        Returns the Patera application instance.
        """
        return self._app

    @property
    def nice_name(self) -> str:
        """
        Returns the human readable name of the task manager.
        """
        return self.configs.NICE_NAME


def schedule_job(*args, **kwargs) -> Callable:
    """
    Decorator for declaring a scheduled job.

    The decorated method is added to the scheduler when the Patera
    application starts.

    Example:

    @schedule_job("interval", minutes=5, id="my_job_id")
    async def my_job(self):
        ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *f_args, **f_kwargs):
            return await run_sync_or_async(func, self, *f_args, **f_kwargs)

        setattr(wrapper, "_scheduler_job", {"args": args, "kwargs": kwargs})
        return wrapper

    return decorator
