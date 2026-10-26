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
import inspect
from functools import wraps
import asyncio
from weakref import WeakValueDictionary

from apscheduler.events import EVENT_JOB_SUBMITTED, EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
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
        default="Task manager",
        description="Human readable name for the task manager for the admin dashboard",
    )
    DAEMON: bool = Field(
        default=True,
        description="Whether the scheduler should run as a daemon. Default True",
    )
    JOB_NAMESPACE: str = Field(
        default="",
        description="Stable namespace for persisted jobs; unique per application/store.",
    )


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")

# The running task managers by class ("module:QualName"), so a job stored in
# a persistent job store can find its task manager again when it runs.
_TASK_MANAGERS: WeakValueDictionary[str, "TaskManager[Any]"] = WeakValueDictionary()


def _manager_key(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


async def run_scheduled_job(
    manager: str, method: str, *args: Any, **kwargs: Any
) -> Any:
    """
    Runs ``method`` of the running task manager ``manager``.

    Jobs in a job store that serializes them (SQLAlchemy, Redis, MongoDB) are
    stored as a call of this function with those two names, instead of the
    method itself: a bound method would carry the task manager, and through
    it the whole application, into the store, which cannot be serialized.
    """
    task_manager = _TASK_MANAGERS.get(manager)
    if task_manager is None:
        raise RuntimeError(
            f"Task manager {manager!r} is not running in this process; "
            "its stored job cannot run."
        )
    return await run_sync_or_async(getattr(task_manager, method), *args, **kwargs)


class TaskManager(BaseExtension[AppT, TaskManagerConfig], Generic[AppT]):
    """
    Task manager class for scheduling and managing background tasks.

    Scheduler configuration is declared on the class implementation:

    - scheduler
    - job_stores
    - executors
    - job_defaults

    Runtime configuration is loaded from application configs.

    The scheduler is the single source of truth for jobs: jobs declared with
    @schedule_job, added through add_job(), or added directly to
    ``self.scheduler`` are all listed, looked up, paused, resumed, removed
    and run in the same way.
    """

    scheduler_cls: Type[BaseScheduler] = AsyncIOScheduler
    # None -> a fresh MemoryJobStore / AsyncIOExecutor per TaskManager instance.
    # (Shared instances at class level would leak jobs between instances/apps.)
    job_stores: Optional[dict[str, BaseJobStore]] = None
    executors: Optional[dict[str, BaseExecutor]] = None
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
        self._running_jobs: dict[str, int] = {}

        self._daemon = self.configs.DAEMON

        if not issubclass(self.scheduler_cls, BaseScheduler):
            raise TypeError(
                "scheduler_cls must be a class and subclass of BaseScheduler"
            )

        job_stores = (
            self.job_stores
            if self.job_stores is not None
            else {"default": MemoryJobStore()}
        )
        executors = (
            self.executors
            if self.executors is not None
            else {"default": AsyncIOExecutor()}
        )

        self._job_stores: dict[str, BaseJobStore] = job_stores
        self._persistent_key = _manager_key(type(self))
        if self.configs.JOB_NAMESPACE:
            self._persistent_key += ":" + self.configs.JOB_NAMESPACE

        self._scheduler = self.scheduler_cls(
            jobstores=job_stores,
            executors=executors,
            job_defaults=dict(self.job_defaults),
            daemon=self._daemon,
        )

        self.scheduler.add_listener(
            self._handle_scheduler_event,
            EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        self._get_defined_jobs()
        self._app.add_on_startup_method(self._start_scheduler)
        self._app.add_on_shutdown_method(self._stop_scheduler)

    def _handle_scheduler_event(self, event) -> None:
        job_id = getattr(event, "job_id", None)

        if not job_id:
            return

        if event.code == EVENT_JOB_SUBMITTED:
            self._mark_job_running(job_id)
            return

        if event.code in (EVENT_JOB_EXECUTED, EVENT_JOB_ERROR):
            self._mark_job_finished(job_id)

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
        persistent = any(
            not isinstance(store, MemoryJobStore) for store in self._job_stores.values()
        )
        if persistent:
            existing = _TASK_MANAGERS.get(self._persistent_key)
            if existing is not None and existing is not self:
                raise RuntimeError(
                    "A persistent task manager already uses this JOB_NAMESPACE; "
                    "configure distinct stable namespaces for separate applications."
                )
            _TASK_MANAGERS[self._persistent_key] = self
        try:
            self.scheduler.start()
            self._start_initial_jobs()
        except BaseException:
            await self._stop_scheduler()
            raise

    async def _stop_scheduler(self) -> None:
        """
        Shutdown hook for stopping the scheduler.
        """
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                # AsyncIOScheduler schedules shutdown on its loop.
                await asyncio.sleep(0)
        finally:
            if _TASK_MANAGERS.get(self._persistent_key) is self:
                del _TASK_MANAGERS[self._persistent_key]

    def _get_defined_jobs(self) -> None:
        """
        Finds methods decorated with @schedule_job.
        """
        for name in dir(self):
            if isinstance(inspect.getattr_static(self, name, None), property):
                continue

            method = getattr(self, name)

            if not callable(method):
                continue

            scheduler_method = getattr(method, "_scheduler_job", None)

            if scheduler_method:
                self._initial_jobs_methods_list.append(
                    (name, scheduler_method["args"], scheduler_method["kwargs"])
                )

    def _start_initial_jobs(self) -> None:
        """
        Adds the jobs declared with @schedule_job. Runs at every startup, so
        an application whose lifespan runs again (a second test client, for
        example) gets its jobs again. Every job has an id, by default
        "<TaskManager class>.<method>", and replaces the stored job of that
        id, so a persistent job store never holds it twice.
        """
        for name, args, kwargs in self._initial_jobs_methods_list:
            default_id = f"{type(self).__name__}.{name}"
            kwargs = {
                "id": default_id,
                "name": default_id,
                "replace_existing": True,
                **kwargs,
            }
            self.add_job(getattr(self, name), *args, **kwargs)

    def run_background_task(self, func: Callable, *args, **kwargs) -> None:
        """
        Runs a method in the background.

        This is useful for fire-and-forget work whose result does not need to
        be awaited before returning a response to the client.
        """
        run_in_background(func, *args, **kwargs)

    def add_job(self, func: Callable, *args, **kwargs) -> Job:
        """
        Adds a job manually. Arguments are passed to the scheduler's add_job().

        A method of this task manager works with every job store: for a store
        that serializes its jobs, it is stored by name (see
        run_scheduled_job) instead of as a bound method.
        """
        if (
            inspect.ismethod(func)
            and func.__self__ is self
            and self._serializes_jobs(kwargs.get("jobstore"))
        ):
            args, kwargs = self._by_name(func.__name__, args, kwargs)
            kwargs.setdefault("name", f"{type(self).__name__}.{func.__name__}")
            func = run_scheduled_job
        return self.scheduler.add_job(func, *args, **kwargs)

    def _serializes_jobs(self, alias: Optional[str]) -> bool:
        """True unless the job store keeps jobs in memory as they are."""
        store = self._job_stores.get(alias or "default")
        return store is not None and not isinstance(store, MemoryJobStore)

    def _by_name(
        self, method: str, args: tuple, kwargs: dict[str, Any]
    ) -> tuple[tuple, dict[str, Any]]:
        """
        Arguments of scheduler.add_job() for run_scheduled_job: the task
        manager's key and the method name come first in the job's ``args``.
        """
        positional = list(args)
        kwargs = dict(kwargs)
        # add_job(func, trigger, args, kwargs, ...): the job's own arguments
        # may be given positionally after the trigger.
        job_args = positional.pop(1) if len(positional) > 1 else kwargs.pop("args", ())
        kwargs["args"] = [self._persistent_key, method, *(job_args or ())]
        return tuple(positional), kwargs

    def job_callable(self, job: Job) -> Callable:
        """The method or function a job runs (also for a job stored by name)."""
        if job.func is run_scheduled_job and len(job.args) >= 2:
            return cast(Callable, getattr(self, job.args[1]))
        return cast(Callable, job.func)

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
        Pauses future runs of a job. Raises JobLookupError if it does not exist.
        """
        job_id: str = job.id if isinstance(job, Job) else job
        self.scheduler.pause_job(job_id, self._job_store_of(job))

    def resume_job(self, job: str | Job) -> None:
        """
        Resumes a paused job. Raises JobLookupError if it does not exist.
        """
        job_id: str = job.id if isinstance(job, Job) else job
        self.scheduler.resume_job(job_id, self._job_store_of(job))

    def get_job(self, job_id: str) -> Job | None:
        """
        Returns a job by ID, from any job store, or None.
        """
        return self.scheduler.get_job(job_id)

    def _job_store_of(self, job: str | Job) -> Optional[str]:
        return getattr(job, "_jobstore_alias", None) if isinstance(job, Job) else None

    def _remove_job(self, job_id: str, job_store: Optional[str] = None) -> None:
        """
        Removes a job from the scheduler.
        """
        self.scheduler.remove_job(job_id, job_store)

    def is_job_running(self, job: str | Job) -> bool:
        job_id: str = job.id if isinstance(job, Job) else job

        return self._running_jobs.get(job_id, 0) > 0

    def _mark_job_running(self, job_id: str) -> None:
        self._running_jobs[job_id] = self._running_jobs.get(job_id, 0) + 1

    def _mark_job_finished(self, job_id: str) -> None:
        running_count = self._running_jobs.get(job_id, 0)

        if running_count <= 1:
            self._running_jobs.pop(job_id, None)
            return

        self._running_jobs[job_id] = running_count - 1

    def run_job_now(self, job: str | Job) -> None:
        if isinstance(job, str):
            active_job = self.get_job(job)

            if active_job is None:
                raise JobLookupError(job)

            job = active_job

        job_id = job.id

        if self.is_job_running(job_id):
            raise RuntimeError(f'Job "{job_id}" is already running.')

        self._mark_job_running(job_id)

        async def runner():
            try:
                await run_sync_or_async(job.func, *job.args, **job.kwargs)
            finally:
                self._mark_job_finished(job_id)

        run_in_background(runner)

    @property
    def jobs(self) -> dict[str, Job]:
        """
        Returns the scheduler's jobs by ID, from every job store, including
        jobs added directly to the scheduler. Jobs that have finished for
        good (a one-off date trigger, for example) are no longer listed.
        """
        return {job.id: job for job in self.scheduler.get_jobs()}

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
