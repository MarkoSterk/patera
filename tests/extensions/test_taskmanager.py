from __future__ import annotations

import asyncio

import pytest
from apscheduler.jobstores.base import JobLookupError

from patera.taskmanager import TaskManager, TaskManagerConfig, schedule_job

pytestmark = pytest.mark.integration


class Jobs(TaskManager):
    runs: list[str]

    @schedule_job("interval", hours=1, id="hourly")
    async def hourly(self):
        self.runs.append("hourly")


@pytest.fixture
def app(make_app):
    return make_app(extensions=[Jobs])


async def test_scheduled_jobs_start_with_the_app(app, client_for):
    jobs = app.get_extension(Jobs)
    jobs.runs = []
    async with client_for(app):
        assert "hourly" in jobs.jobs
        assert jobs.scheduler.running
        assert jobs.nice_name == "Task manager"
        jobs.run_job_now("hourly")
        await asyncio.sleep(0.05)
        assert jobs.runs == ["hourly"]
    assert not jobs.scheduler.running


async def test_instances_do_not_share_job_stores(make_app, client_for):
    app1 = make_app(extensions=[Jobs])
    app2 = make_app(extensions=[Jobs])
    jobs1, jobs2 = app1.get_extension(Jobs), app2.get_extension(Jobs)
    jobs1.runs = jobs2.runs = []
    assert (
        jobs1.scheduler._jobstores["default"]
        is not jobs2.scheduler._jobstores["default"]
    )
    # Starting both used to fail with a conflicting job id.
    async with client_for(app1), client_for(app2):
        assert jobs1.get_job("hourly") is not None
        assert jobs2.get_job("hourly") is not None


async def test_manual_job_management(app, client_for):
    jobs = app.get_extension(Jobs)
    jobs.runs = []
    async with client_for(app):
        hits: list[int] = []
        job = jobs.add_job(lambda: hits.append(1), "interval", minutes=5, id="manual")
        assert jobs.get_job("manual") is job
        jobs.pause_job("manual")
        assert jobs.scheduler.get_job("manual").next_run_time is None
        jobs.resume_job("manual")
        assert jobs.scheduler.get_job("manual").next_run_time is not None
        jobs.remove_job(job)
        assert jobs.get_job("manual") is None
        with pytest.raises(JobLookupError):
            jobs.pause_job("manual")
        with pytest.raises(JobLookupError):
            jobs.run_job_now("manual")


async def test_config_and_background_tasks(make_app, client_for):
    app = make_app(extensions=[Jobs], JOBS=TaskManagerConfig(NICE_NAME="Nightly"))
    jobs = app.get_extension(Jobs)
    jobs.runs = []
    assert jobs.nice_name == "Nightly"
    done = asyncio.Event()
    async with client_for(app):
        jobs.run_background_task(done.set)
        await asyncio.wait_for(done.wait(), 1)


async def test_jobs_added_directly_to_the_scheduler_are_managed(app, client_for):
    jobs = app.get_extension(Jobs)
    jobs.runs = []
    hits: list[str] = []
    async with client_for(app):
        # Bypasses TaskManager.add_job entirely.
        jobs.scheduler.add_job(
            lambda: hits.append("direct"), "interval", hours=2, id="direct"
        )
        assert set(jobs.jobs) == {"hourly", "direct"}
        assert jobs.get_job("direct") is not None

        jobs.pause_job("direct")
        assert jobs.get_job("direct").next_run_time is None
        jobs.resume_job(jobs.get_job("direct"))
        assert jobs.get_job("direct").next_run_time is not None

        jobs.run_job_now("direct")
        await asyncio.sleep(0.05)
        assert hits == ["direct"]

        jobs.remove_job("direct")
        assert "direct" not in jobs.jobs


async def test_finished_one_off_jobs_disappear(app, client_for):
    jobs = app.get_extension(Jobs)
    jobs.runs = []
    done = asyncio.Event()
    async with client_for(app):
        jobs.add_job(done.set, "date", id="once")
        await asyncio.wait_for(done.wait(), 2)
        await asyncio.sleep(0.05)
        assert "once" not in jobs.jobs
        assert jobs.get_job("once") is None


async def test_jobs_in_a_second_job_store_are_listed(make_app, client_for):
    from apscheduler.jobstores.memory import MemoryJobStore

    class TwoStores(TaskManager):
        pass

    app = make_app(extensions=[TwoStores])
    jobs = app.get_extension(TwoStores)
    jobs.scheduler.add_jobstore(MemoryJobStore(), "archive")
    async with client_for(app):
        job = jobs.add_job(
            lambda: None, "interval", hours=1, id="old", jobstore="archive"
        )
        assert "old" in jobs.jobs
        jobs.pause_job(job)
        assert jobs.get_job("old").next_run_time is None
        jobs.resume_job("old")
        assert jobs.get_job("old").next_run_time is not None


async def test_jobs_return_when_the_lifespan_runs_again(app, client_for):
    jobs = app.get_extension(Jobs)
    for _ in range(2):
        async with client_for(app):
            assert list(jobs.jobs) == ["hourly"]


STORED_RUNS: list[str] = []


def _persistent_jobs(path) -> type:
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

    class StoredJobs(TaskManager):
        job_stores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{path}")}

        @schedule_job("interval", hours=1)
        async def nightly(self, label: str = "nightly") -> None:
            """Cleans up once an hour."""
            STORED_RUNS.append(label)

    return StoredJobs


async def test_jobs_work_with_a_persistent_job_store(make_app, client_for, tmp_path):
    from patera.taskmanager.task_manager import run_scheduled_job

    path = tmp_path / "jobs.db"
    for _ in range(2):  # a restart finds the stored job and replaces it
        stored_jobs = _persistent_jobs(path)
        app = make_app(extensions=[stored_jobs])
        jobs = app.get_extension(stored_jobs)
        STORED_RUNS.clear()
        async with client_for(app):
            assert list(jobs.jobs) == ["StoredJobs.nightly"]
            job = jobs.get_job("StoredJobs.nightly")
            # Stored by name: the bound method would drag the app into the store.
            assert job.func is run_scheduled_job
            assert jobs.job_callable(job).__doc__ == "Cleans up once an hour."
            jobs.run_job_now(job)
            await asyncio.sleep(0.05)
            assert STORED_RUNS == ["nightly"]

            # Methods added by hand are stored by name too, with their arguments.
            jobs.add_job(jobs.nightly, "interval", ["manual"], minutes=5, id="manual")
            jobs.run_job_now("manual")
            await asyncio.sleep(0.05)
            assert STORED_RUNS == ["nightly", "manual"]
            jobs.remove_job("manual")


async def test_declared_jobs_get_a_default_id(make_app, client_for):
    class Named(TaskManager):
        @schedule_job("interval", hours=1)
        async def cleanup(self) -> None: ...

    app = make_app(extensions=[Named])
    async with client_for(app):
        assert list(app.get_extension(Named).jobs) == ["Named.cleanup"]
