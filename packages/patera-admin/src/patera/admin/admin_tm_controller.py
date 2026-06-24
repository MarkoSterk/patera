from typing import Any, cast
import inspect

from apscheduler.job import Job
from apscheduler.jobstores.base import JobLookupError

from patera.controller import (
    Controller,
    get,
    post,
    delete,
    put,
    patch,
    consumes,
    produces,
    before_request,
)
from patera import (
    Patera,
    BaseConfig,
    Request,
    Response,
    HttpStatus,
    MediaType,
)
from patera.auth import login_required

from .admin_interface import AdminInterface
from .exceptions import AdminLoginRequiredException, AdminUnsupportedLanguage


class _AdminTMController(Controller[Patera[BaseConfig]]):
    """
    Admin controller for viewing and managing TaskManager jobs.
    """

    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @before_request
    async def check_language(self, req: Request):
        lang = cast(str, req.route_parameters.get("lang"))

        if lang not in self.admin_interface.supported_languages:
            raise AdminUnsupportedLanguage(lang)

    @get("/")
    @produces(MediaType.TEXT_HTML)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def task_list(self, req: Request, manager: str) -> Response:
        task_manager = self.get_task_manager(manager)

        if task_manager is None:
            return self.task_manager_not_found_response(req, manager)

        return await req.res.html(
            "_admin/task_managers/tasks.html",
            {
                **self.admin_interface.context_variables,
                "manager": manager,
                "task_manager": task_manager,
                "tasks": [
                    self.job_to_dict(job, task_manager)
                    for job in task_manager.jobs.values()
                ],
            },
        )

    @post("/<string:job_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def run_job(self, req: Request, manager: str, job_id: str) -> Response:
        """
        Runs a scheduled job immediately as a one-off background execution.

        This does not change the scheduler trigger. It only starts one manual
        execution of the job.
        """
        task_manager = self.get_task_manager(manager)

        if task_manager is None:
            return self.task_manager_not_found_response(req, manager)

        job = task_manager.get_job(job_id)

        if job is None:
            return self.job_not_found_response(req, job_id)

        try:
            if task_manager.is_job_running(job_id):
                return self.error_response(
                    req,
                    "Task is already running.",
                    HttpStatus.BAD_REQUEST,
                )

            task_manager.run_job_now(job)

            return req.res.json(
                {
                    "message": "Task started successfully.",
                    "status": "success",
                    "data": self.job_to_dict(job, task_manager),
                }
            ).status(HttpStatus.ACCEPTED)

        except JobLookupError:
            return self.job_not_found_response(req, job_id)

        except Exception as e:
            self.app.logger.exception(e)

            return self.error_response(
                req,
                "Failed to start task.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @patch("/<string:job_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def pause_job(self, req: Request, manager: str, job_id: str) -> Response:
        """
        Pauses the scheduled job.

        This pauses future scheduled runs. It does not cancel a currently running
        manual execution.
        """
        task_manager = self.get_task_manager(manager)

        if task_manager is None:
            return self.task_manager_not_found_response(req, manager)

        job = task_manager.get_job(job_id)

        if job is None:
            return self.job_not_found_response(req, job_id)

        try:
            task_manager.pause_job(job_id)

            return req.res.json(
                {
                    "message": "Task paused successfully.",
                    "status": "success",
                    "data": self.job_to_dict(job, task_manager),
                }
            ).status(HttpStatus.ACCEPTED)

        except JobLookupError:
            return self.job_not_found_response(req, job_id)

        except Exception as e:
            self.app.logger.exception(e)

            return self.error_response(
                req,
                "Failed to pause task.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @put("/<string:job_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def resume_job(self, req: Request, manager: str, job_id: str) -> Response:
        """
        Resumes a paused scheduled job.
        """
        task_manager = self.get_task_manager(manager)

        if task_manager is None:
            return self.task_manager_not_found_response(req, manager)

        job = task_manager.get_job(job_id)

        if job is None:
            return self.job_not_found_response(req, job_id)

        try:
            task_manager.resume_job(job_id)

            return req.res.json(
                {
                    "message": "Task resumed successfully.",
                    "status": "success",
                    "data": self.job_to_dict(job, task_manager),
                }
            ).status(HttpStatus.ACCEPTED)

        except JobLookupError:
            return self.job_not_found_response(req, job_id)

        except Exception as e:
            self.app.logger.exception(e)

            return self.error_response(
                req,
                "Failed to resume task.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @delete("/<string:job_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def remove_job(self, req: Request, manager: str, job_id: str) -> Response:
        """
        Removes a job from the scheduler and the TaskManager active jobs map.

        This removes future scheduled runs. It does not forcibly cancel a
        currently running manual execution.
        """
        task_manager = self.get_task_manager(manager)

        if task_manager is None:
            return self.task_manager_not_found_response(req, manager)

        job = task_manager.get_job(job_id)

        if job is None:
            return self.job_not_found_response(req, job_id)

        try:
            job_data = self.job_to_dict(job, task_manager)
            task_manager.remove_job(job_id)

            return req.res.json(
                {
                    "message": "Task removed from task queue.",
                    "status": "success",
                    "data": job_data,
                }
            ).status(HttpStatus.ACCEPTED)

        except JobLookupError:
            return self.job_not_found_response(req, job_id)

        except Exception as e:
            self.app.logger.exception(e)

            return self.error_response(
                req,
                "Failed to remove task.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    def get_task_manager(self, manager: str) -> Any | None:
        return self.admin_interface.task_managers.get(manager)

    def task_manager_not_found_response(
        self,
        req: Request,
        manager: str,
    ) -> Response:
        return self.error_response(
            req,
            f'Task manager with name "{manager}" not found.',
            HttpStatus.NOT_FOUND,
        )

    def job_not_found_response(
        self,
        req: Request,
        job_id: str,
    ) -> Response:
        return self.error_response(
            req,
            f'Task with id "{job_id}" not found.',
            HttpStatus.NOT_FOUND,
        )

    def job_to_dict(self, job: Job, task_manager: Any) -> dict[str, Any]:
        return {
            "id": job.id,
            "name": job.name,
            "func_ref": job.func_ref,
            "description": inspect.getdoc(job.func) or "",
            "trigger": str(job.trigger),
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            "paused": job.next_run_time is None,
            "running": task_manager.is_job_running(job.id),
        }

    def error_response(
        self,
        req: Request,
        message: str,
        status: HttpStatus,
    ) -> Response:
        return req.res.json(
            {
                "message": message,
                "status": "error",
            }
        ).status(status)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
