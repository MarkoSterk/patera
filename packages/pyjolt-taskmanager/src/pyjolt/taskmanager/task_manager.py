"""
Task manager class
"""

from typing import (
    Callable,
    Tuple,
    Optional,
    Type,
    cast,
    TYPE_CHECKING,
    Any,
    TypedDict,
    NotRequired,
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

from pyjolt.utilities import run_sync_or_async, run_in_background
from pyjolt.base_extension import BaseExtension

if TYPE_CHECKING:
    from pyjolt import PyJolt


class _TaskManagerConfigs(BaseModel):
    """Configuration model for TaskManager extension."""

    NICE_NAME: Optional[str] = Field(
        "Task manager",
        description="Human readable name for the task manager for the admin dashboard",
    )
    SCHEDULER: Optional[Type[BaseScheduler]] = Field(
        default=AsyncIOScheduler,
        description="Scheduler class to use, must be subclass of apscheduler.schedulers.BaseScheduler. Default AsyncIOScheduler",
    )
    JOB_STORES: Optional[dict[str, BaseJobStore]] = Field(
        default={"default": MemoryJobStore()},
        description="Job stores configuration dictionary. Default MemoryJobStore",
    )
    EXECUTORS: Optional[dict[str, BaseExecutor]] = Field(
        default={"default": AsyncIOExecutor()},
        description="Executors configuration dictionary. Default AsyncIOExecutor",
    )
    JOB_DEFAULTS: Optional[dict[str, bool | int]] = Field(
        default={"coalesce": False, "max_instances": 3},
        description="Default job settings dictionary",
    )
    DAEMON: Optional[bool] = Field(
        default=True,
        description="Whether the scheduler should run as a daemon. Default True",
    )


class TaskManagerConfig(TypedDict):
    """TypedDict for TaskManager configuration."""

    NICE_NAME: NotRequired[str]
    SCHEDULER: NotRequired[Type[BaseScheduler]]
    JOB_STORES: NotRequired[dict[str, BaseJobStore]]
    EXECUTORS: NotRequired[dict[str, BaseExecutor]]
    JOB_DEFAULTS: NotRequired[dict[str, bool | int]]
    DAEMON: NotRequired[bool]


class TaskManager(BaseExtension):
    """
    Task manager class for scheduling and managing backgroudn tasks.
    """

    def __init__(self, configs_name: str = "TASK_MANAGER") -> None:
        self._configs_name: str = cast(str, configs_name)
        self._configs: dict[str, Any] = {}
        self._app: "PyJolt"
        self._job_stores: dict
        self._executors: dict
        self._job_defaults: dict
        self._daemon: bool
        self._scheduler: AsyncIOScheduler
        self._initial_jobs_methods_list: list[Tuple] = []
        self._active_jobs: dict[str, Job] = {}

    def init_app(self, app: "PyJolt"):
        """
        Initlizer for TaskManager with PyJolt app
        """
        self._app = app  # type: ignore
        self._configs = app.get_conf(self._configs_name, {})

        self._configs = self.validate_configs(self._configs, _TaskManagerConfigs)
        self._job_stores = self._configs["JOB_STORES"]
        self._executors = self._configs["EXECUTORS"]
        self._job_defaults = self._configs["JOB_DEFAULTS"]
        self._daemon = self._configs["DAEMON"]
        self._scheduler = self._configs["SCHEDULER"]

        self._scheduler = self._scheduler(
            jobstores=self._job_stores,
            executors=self._executors,
            job_defaults=self._job_defaults,
            daemon=self._daemon,
        )  # type: ignore
        self._app.add_extension(self)
        self._get_defined_jobs()
        self._app.add_on_startup_method(self._start_scheduler)
        self._app.add_on_shutdown_method(self._stop_scheduler)

    def pause_scheduler(self):
        """
        Pauses scheduler execution
        """
        self.scheduler.pause()

    def resume_scheduler(self):
        """
        Resumes paused scheduler execution
        """
        self.scheduler.resume()

    async def _start_scheduler(self):
        """
        On startup hook for starting the scheduler
        """
        self.scheduler.start()
        self._start_initial_jobs()

    async def _stop_scheduler(self):
        """
        On shutdown hook for shuting the scheduler down
        """
        self.scheduler.shutdown()

    def _get_defined_jobs(self):
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
        Starts all initial jobs (decorated functions)
        """
        if (
            self._initial_jobs_methods_list is None
            or len(self._initial_jobs_methods_list) == 0
        ):
            return
        for func, args, kwargs in self._initial_jobs_methods_list:
            job: Job = self.scheduler.add_job(func, *args, **kwargs)
            self._active_jobs[job.id] = job
        self._initial_jobs_methods_list = []

    def run_background_task(self, func: Callable, *args, **kwargs):
        """
        Runs a method in the background (fire and forget).
        Used for running functions whose execution doesn't have to be awaited/returned to the user.
        Example: a route handler can return a response immediately, and the
        task is executed in a seperate thread (sending an email for example).

        Uses the pyjolt.utilities.run_in_background method
        """
        run_in_background(func, *args, **kwargs)

    def add_job(self, func: Callable, *args, **kwargs) -> Job:
        """
        Adds job
        """
        job: Job = self.scheduler.add_job(func, *args, **kwargs)
        self._active_jobs[job.id] = job
        return job

    def remove_job(self, job: str | Job, job_store: Optional[str] = None):
        """
        Removes a job.
        :param job: job id (str) or the Job instance returned by the scheduler.add_job method
        """
        if isinstance(job, Job):
            job = job.id
        return self._remove_job(cast(str, job), job_store)

    def pause_job(self, job: str | Job):
        """
        Pauses the job
        """
        if isinstance(job, Job):
            return job.pause()
        active_job: Optional[Job] = self._active_jobs.get(job, None)
        if job is None:
            raise JobLookupError(job)
        return cast(Job, active_job).pause()

    def resume_job(self, job: str | Job):
        """
        Resumes job
        :param paused_job: id or Job instance
        """
        if isinstance(job, Job):
            return job.resume()
        paused_job: Optional[Job] = self._active_jobs.get(job, None)
        if paused_job is None:
            raise JobLookupError(paused_job)
        return paused_job.resume()

    def get_job(self, job_id: str) -> Job | None:
        return self._active_jobs.get(job_id, None)

    def _remove_job(self, job_id: str, job_store=None):
        """
        Removes job from job list
        """
        self.scheduler.remove_job(job_id, job_store)
        del self._active_jobs[job_id]

    @property
    def jobs(self) -> dict[str, Job]:
        """
        Returns dictionary of running jobs
        """
        return self._active_jobs

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """
        Returns the background scheduler instance
        """
        return self._scheduler

    @property
    def nice_name(self) -> str:
        """Nice name of the instance"""
        return self._configs["NICE_NAME"]

    @property
    def app(self) -> "PyJolt":
        """
        Application instance
        """
        return cast("PyJolt", self._app)


def schedule_job(*args, **kwargs):
    """
    ```
    A decorator to add a function as a scheduled job in the given APScheduler instance.
    The decorated function is added to a list of tuples (func, args, kwargs) and the job
    is started when the scheduler instance is started (on_startup event of PyJolt)
    IMPORTANT: The decorator should be the top-most decorator of the function to make sure
    any other decorator is applied before the job is added to the job list
    :param args: Positional arguments to pass to scheduler.add_job().
                Typically, the first of these args is the trigger (e.g. 'interval', 'cron', etc.).
    :param kwargs: Keyword arguments to pass to scheduler.add_job().
    Example:
    Runs a job with id 'my_job_id' every 5 minutes

    @schedule_job('interval', minutes=5, id='my_job_id')
    async def my_job(self):
        #some task
    ```
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, *f_args, **f_kwargs):
            return await run_sync_or_async(func, self, *f_args, **f_kwargs)

        setattr(wrapper, "_scheduler_job", {"args": args, "kwargs": kwargs})
        return wrapper

    return decorator
