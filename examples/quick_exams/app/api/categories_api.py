from typing import TYPE_CHECKING

from app.models import INSTRUCTOR
from app.schemas import CategoryIn, CategoryOut
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
