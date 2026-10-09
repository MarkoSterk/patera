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
