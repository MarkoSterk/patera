from typing import TYPE_CHECKING

from app.models import INSTRUCTOR
from app.schemas import SubjectIn, SubjectOut
from app.services.authoring import AuthoringService
from patera.auth import role_required
from patera.database.sql import transactional

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import (
    Controller,
    consumes,
    delete,
    get,
    path,
    post,
    produces,
    put,
    RequestBody,
)
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/subjects", tags=["Subjects"])
@role_required(INSTRUCTOR)
class SubjectsApi(Controller["App"]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_subjects(self, req: Request) -> Response[list[SubjectOut]]:
        return req.res.json(await self.authoring.list_subjects(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_subject(
        self, req: Request, data: RequestBody[SubjectIn]
    ) -> Response[SubjectOut]:
        return req.res.json(await self.authoring.create_subject(req.user.id, data))

    @put("/<subject_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_subject(
        self, req: Request, subject_id: str, data: RequestBody[SubjectIn]
    ) -> Response[SubjectOut]:
        return req.res.json(
            await self.authoring.update_subject(req.user.id, subject_id, data)
        )

    @delete("/<subject_id>")
    @transactional
    async def delete_subject(self, req: Request, subject_id: str) -> Response:
        await self.authoring.delete_subject(req.user.id, subject_id)
        return req.res.no_content()
