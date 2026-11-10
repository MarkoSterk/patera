import re
from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from app.models import INSTRUCTOR
from app.schemas import (
    CategoryIn,
    CategoryOut,
    ExamIn,
    ExamOut,
    QuestionIn,
    QuestionOut,
    SubjectIn,
    SubjectOut,
)
from app.services.authoring import AuthoringService
from app.services.exam_export import exam_docx
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


@path("/api/categories", tags=["Categories"])
@role_required(INSTRUCTOR)
class CategoriesApi(Controller["App"]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_categories(self, req: Request) -> Response[list[CategoryOut]]:
        return req.res.json(await self.authoring.list_categories(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_category(
        self, req: Request, data: RequestBody[CategoryIn]
    ) -> Response[CategoryOut]:
        return req.res.json(await self.authoring.create_category(req.user.id, data))

    @put("/<category_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_category(
        self, req: Request, category_id: str, data: RequestBody[CategoryIn]
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


@path("/api/exams", tags=["Exams"])
@role_required(INSTRUCTOR)
class ExamsApi(Controller["App"]):
    authoring: Inject[AuthoringService]

    @get("/")
    async def list_exams(self, req: Request) -> Response[list[ExamOut]]:
        return req.res.json(await self.authoring.list_exams(req.user.id))

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_exam(
        self, req: Request, data: RequestBody[ExamIn]
    ) -> Response[ExamOut]:
        return req.res.json(await self.authoring.create_exam(req.user.id, data))

    @put("/<exam_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_exam(
        self, req: Request, exam_id: str, data: RequestBody[ExamIn]
    ) -> Response[ExamOut]:
        return req.res.json(
            await self.authoring.update_exam(req.user.id, exam_id, data)
        )

    @delete("/<exam_id>")
    @transactional
    async def delete_exam(self, req: Request, exam_id: str) -> Response:
        await self.authoring.delete_exam(req.user.id, exam_id)
        return req.res.no_content()

    @get("/<exam_id>/docx")
    async def export_exam_docx(self, req: Request, exam_id: str) -> Response:
        """
        The exam as a Word document: numbered questions, answers a) to d),
        the correct answer in bold. A random-per-attempt exam is exported as
        a newly drawn version.
        """
        exam, questions = await self.authoring.exam_for_export(req.user.id, exam_id)
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", exam.title).strip("_") or "exam"
        return req.res.bytes(
            exam_docx(exam.title, questions),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ).set_header(
            "Content-Disposition",
            f'attachment; filename="{filename}.docx"; '
            f"filename*=UTF-8''{quote(exam.title)}.docx",
        )

    @get("/<exam_id>/qr")
    async def exam_qr_code(self, req: Request, exam_id: str) -> Response:
        exam = await self.authoring.get_exam(req.user.id, exam_id)
        link = f"{self.app.configs.exam_base_url}/exam/{exam.id}"
        svg = BytesIO()
        qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage).save(svg)
        return req.res.bytes(svg.getvalue(), "image/svg+xml")
