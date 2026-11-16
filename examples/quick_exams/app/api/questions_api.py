from typing import TYPE_CHECKING

from app.models import INSTRUCTOR
from app.schemas import QuestionIn, QuestionOut
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


@path("/api/questions", tags=["Questions"])
@role_required(INSTRUCTOR)
class QuestionsApi(Controller["App"]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_questions(self, req: Request) -> Response[list[QuestionOut]]:
        return req.res.json(await self.authoring.list_questions(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_question(
        self, req: Request, data: RequestBody[QuestionIn]
    ) -> Response[QuestionOut]:
        return req.res.json(await self.authoring.create_question(req.user.id, data))

    @put("/<question_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_question(
        self, req: Request, question_id: str, data: RequestBody[QuestionIn]
    ) -> Response[QuestionOut]:
        return req.res.json(
            await self.authoring.update_question(req.user.id, question_id, data)
        )

    @delete("/<question_id>")
    @transactional
    async def delete_question(self, req: Request, question_id: str) -> Response:
        await self.authoring.delete_question(req.user.id, question_id)
        return req.res.no_content()
