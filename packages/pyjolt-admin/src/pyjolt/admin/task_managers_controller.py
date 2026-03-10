"""
Schedulers related admin dashboard controller
"""

from ..task_manager import TaskManager
from ..request import Request
from ..response import Response
from ..http_statuses import HttpStatus
from ..controller import get
from .common_controller import CommonAdminController
from ..utilities import run_in_background


class AdminTaskManagersController(CommonAdminController):
    @get("/task-managers")
    async def task_managers(self, req: Request) -> Response:
        """List of all schedulers"""
        return await req.res.html(
            "/__admin_templates/task_managers.html",
            {
                "task_managers": self.dashboard.get_task_managers(),
                **self.get_common_variables(),
            },
        )

    @get("/task-managers/<string:manager_name>")
    async def task_manager(self, req: Request, manager_name: str) -> Response:
        """Selected task manager"""
        managers: dict[str, TaskManager] | None = self.dashboard.get_task_managers()
        if managers is None:
            return await self.extension_not_available(req, "TaskManager")

        manager: list[TaskManager] = list(
            filter(lambda mng: mng.configs_name == manager_name, managers.values())
        )
        if len(manager) == 0:
            return await self.extension_not_available(
                req, "TaskManager - " + manager_name
            )
        return await req.res.html(
            "/__admin_templates/task_manager.html",
            {
                "manager": manager[0],
                "manager_name": manager[0].configs_name,
                "tasks": manager[0].jobs,
                **self.get_common_variables(),
            },
        )

    # API calls for task management
    @get("/task-managers/<string:manager_name>/run/<string:task_id>")
    async def run_task(self, req: Request, manager_name: str, task_id: str) -> Response:
        """Runs task with provided ID"""
        try:
            managers: dict[str, TaskManager] | None = self.dashboard.get_task_managers()
            if managers is None:
                return await self.extension_not_available(req, "TaskManager")
            manager: list[TaskManager] = list(
                filter(lambda mng: mng.configs_name == manager_name, managers.values())
            )
            if len(manager) == 0:
                return await self.extension_not_available(
                    req, "TaskManager - " + manager_name
                )

            task = manager[0].jobs.get(task_id)
            if task is None:
                return req.res.json(
                    {
                        "message": f"Task with id '{task_id}' does not exist",
                        "status": "danger",
                    }
                ).status(HttpStatus.BAD_REQUEST)
            self.app.logger.info(
                f"Running task with {task_id=} in task manager {manager_name}"
            )
            run_in_background(task.func)
            return req.res.json(
                {"message": "Task started", "status": "success"}
            ).status(HttpStatus.OK)
        except Exception:
            return req.res.json(
                {
                    "message": f"Something went wrong. Make sure task manager {manager_name} and task {task_id=} exist.",
                    "status": "danger",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    @get("/task-managers/<string:manager_name>/pause/<string:task_id>")
    async def pause_task(
        self, req: Request, manager_name: str, task_id: str
    ) -> Response:
        """Pauses task with provided ID"""
        try:
            managers: dict[str, TaskManager] | None = self.dashboard.get_task_managers()
            if managers is None:
                return await self.extension_not_available(req, "TaskManager")
            manager: list[TaskManager] = list(
                filter(lambda mng: mng.configs_name == manager_name, managers.values())
            )
            if len(manager) == 0:
                return await self.extension_not_available(
                    req, "TaskManager - " + manager_name
                )

            self.app.logger.info(
                f"Pausing task with {task_id=} in task manager {manager_name}"
            )
            manager[0].pause_job(task_id)

            return req.res.json({"message": "Task paused", "status": "success"}).status(
                HttpStatus.OK
            )
        except Exception:
            return req.res.json(
                {
                    "message": f"Something went wrong. Check if job with {task_id=} exists in task manager {manager_name}",
                    "status": "danger",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    @get("/task-managers/<string:manager_name>/resume/<string:task_id>")
    async def resume_task(
        self, req: Request, manager_name: str, task_id: str
    ) -> Response:
        """Resumes task with provided ID"""
        try:
            managers: dict[str, TaskManager] | None = self.dashboard.get_task_managers()
            if managers is None:
                return await self.extension_not_available(req, "TaskManager")
            manager: list[TaskManager] = list(
                filter(lambda mng: mng.configs_name == manager_name, managers.values())
            )
            if len(manager) == 0:
                return await self.extension_not_available(
                    req, "TaskManager - " + manager_name
                )

            self.app.logger.info(
                f"Resuming task with {task_id=} in task manager {manager_name}"
            )
            manager[0].resume_job(task_id)

            return req.res.json(
                {"message": "Task started", "status": "success"}
            ).status(HttpStatus.OK)
        except Exception:
            return req.res.json(
                {
                    "message": f"Something went wrong. Check if job with {task_id=} exists in task manager {manager_name}",
                    "status": "danger",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)
