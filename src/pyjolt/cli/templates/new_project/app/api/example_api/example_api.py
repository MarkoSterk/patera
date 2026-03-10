"""
Test api endpoint
"""

from typing import Any
from pyjolt import Request, Response, HttpStatus, MediaType, abort
from pyjolt.controller import Controller, path, get, post, consumes, produces
from pydantic import BaseModel, field_serializer
from pyjolt.database.sql import AsyncSession

from app.extensions import db
from app.api.models import Example


class CreateExample(BaseModel):
    name: str


class ExampleOut(CreateExample):
    id: int

    @classmethod
    def from_model(cls, model: Example):
        return cls(id=model.id, name=model.name)


class ResponseModel(BaseModel):
    message: str
    data: Any | None = None

    @field_serializer("data")
    def serialize_data(self, data: Any, _info):
        if isinstance(data, BaseModel):
            return data.model_dump()
        return data


@path("/api/v1/examples")
class ExampleApi(Controller):
    @get("/<int:example_id>")
    @produces(MediaType.APPLICATION_JSON)
    @db.managed_session
    async def get_example(
        self, req: Request, example_id: int, session: AsyncSession
    ) -> Response[ResponseModel]:
        # The request object is always injected into the endpoint as the first argument
        # All other data (route parameters, indicated data objects etc) are injected
        # in the order of top->bottom, left->right

        example: Example = await Example.query(session).filter_by(id=example_id).first()
        if example is None:
            abort(
                f"Test with id {example_id} does not exist.",
                HttpStatus.NOT_FOUND,
                "error",
            )

        return req.response.json(
            {
                "message": "Test fetched successfully",
                "data": ExampleOut.from_model(example),
            }
        ).status(HttpStatus.OK)

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @db.managed_session
    async def create_example(
        self, req: Request, data: CreateExample, session: AsyncSession
    ) -> Response[CreateExample]:
        # CreateTest data is validated and injected into the endpoint controlelr
        # Some logic for creating/storing the test object data
        # Response data is serialized as the indicated CreateTest pydantic model in the response type
        # -> Response[CreateTest] indicates what type the response body is
        example: Example = Example(name=data.name)
        session.add(example)
        return req.response.json({"name": data.name}).status(HttpStatus.CREATED)
