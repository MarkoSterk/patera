from io import BytesIO

import qrcode
import qrcode.image.svg
from patera import HttpStatus, MediaType, Request, Response
from patera.auth import role_required
from patera.controller import (
    Controller,
    consumes,
    delete,
    get,
    path,
    post,
    produces,
    put,
)
from patera.database.sql import transactional
from patera.injectable import Inject

from app import App
from app.models import INSTRUCTOR
from app.schemas import (
    CategoryIn,
    CategoryOut,
    ExamIn,
    ExamOut,
    QuestionIn,
    QuestionOut,
)
from app.services.authoring import AuthoringService


@path("/api/categories", tags=["Categories"])
@role_required(INSTRUCTOR)
class CategoriesApi(Controller[App]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_categories(self, req: Request) -> Response[list[CategoryOut]]:
        return req.res.json(await self.authoring.list_categories(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_category(
        self, req: Request, data: CategoryIn
    ) -> Response[CategoryOut]:
        return req.res.json(await self.authoring.create_category(req.user.id, data))

    @put("/<category_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_category(
        self, req: Request, category_id: str, data: CategoryIn
    ) -> Response[CategoryOut]:
        return req.res.json(
            await self.authoring.update_category(req.user.id, category_id, data)
        )

    @delete("/<category_id>")
    @transactional
    async def delete_category(self, req: Request, category_id: str) -> Response:
        await self.authoring.delete_category(req.user.id, category_id)
        return req.res.no_content()


@path("/api/questions", tags=["Questions"])
@role_required(INSTRUCTOR)
class QuestionsApi(Controller[App]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_questions(self, req: Request) -> Response[list[QuestionOut]]:
        return req.res.json(await self.authoring.list_questions(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_question(
        self, req: Request, data: QuestionIn
    ) -> Response[QuestionOut]:
        return req.res.json(await self.authoring.create_question(req.user.id, data))

    @put("/<question_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_question(
        self, req: Request, question_id: str, data: QuestionIn
    ) -> Response[QuestionOut]:
        return req.res.json(
            await self.authoring.update_question(req.user.id, question_id, data)
        )

    @delete("/<question_id>")
    @transactional
    async def delete_question(self, req: Request, question_id: str) -> Response:
        await self.authoring.delete_question(req.user.id, question_id)
        return req.res.no_content()


@path("/api/exams", tags=["Exams"])
@role_required(INSTRUCTOR)
class ExamsApi(Controller[App]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_exams(self, req: Request) -> Response[list[ExamOut]]:
        return req.res.json(await self.authoring.list_exams(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_exam(self, req: Request, data: ExamIn) -> Response[ExamOut]:
        return req.res.json(await self.authoring.create_exam(req.user.id, data))

    @put("/<exam_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_exam(
        self, req: Request, exam_id: str, data: ExamIn
    ) -> Response[ExamOut]:
        return req.res.json(
            await self.authoring.update_exam(req.user.id, exam_id, data)
        )

    @delete("/<exam_id>")
    @transactional
    async def delete_exam(self, req: Request, exam_id: str) -> Response:
        await self.authoring.delete_exam(req.user.id, exam_id)
        return req.res.no_content()

    @get("/<exam_id>/qr")
    async def exam_qr_code(self, req: Request, exam_id: str) -> Response:
        exam = await self.authoring.get_exam(req.user.id, exam_id)
        link = f"{self.app.configs.PUBLIC_URL.rstrip('/')}/exam/{exam.id}"
        svg = BytesIO()
        qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage).save(svg)
        return req.res.bytes(svg.getvalue(), "image/svg+xml")
