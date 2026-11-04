"""
RequestBody[...] and QueryParams[...] handler parameters: injection,
validation, registration errors and OpenAPI documentation.
"""

from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, Field

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import (
    Controller,
    QueryParams,
    RequestBody,
    after_request,
    consumes,
    get,
    path,
    post,
    produces,
    socket,
)
from patera.controller.params import BodySource, QuerySource, handler_params
from patera.exceptions import UnexpectedDecorator


class UserQuery(BaseModel):
    page: int = 1
    tags: list[str] = []
    order_by: Optional[str] = Field(
        default=None, alias="orderBy", description="Sort field"
    )


class Paging(BaseModel):
    limit: int = Field(ge=1, le=100)


class CreateUser(BaseModel):
    name: str
    age: int


class Filters(BaseModel):
    active: bool = False


@path("/users")
class UsersController(Controller):
    @after_request
    def mark(self, res: Response) -> None:
        res.set_header("x-after", "yes")

    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def find(self, req: Request, query: QueryParams[UserQuery]) -> Response:
        """Find users"""
        return req.res.json(query.model_dump(mode="json"))

    @get("/paged")
    @produces(MediaType.APPLICATION_JSON)
    async def paged(
        self,
        req: Request,
        paging: QueryParams[Paging],
        filters: QueryParams[Filters],
    ) -> Response:
        return req.res.json({"limit": paging.limit, "active": filters.active})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def create(
        self,
        req: Request,
        data: RequestBody[CreateUser],
        query: QueryParams[UserQuery],
    ) -> Response:
        return req.res.json({"user": data.model_dump(), "page": query.page})

    @consumes(MediaType.APPLICATION_X_WWW_FORM_URLENCODED)
    @post("/<int:group_id>/form")
    @produces(MediaType.APPLICATION_JSON)
    async def form(
        self, req: Request, group_id: int, data: RequestBody[CreateUser]
    ) -> Response:
        return req.res.json({"group": group_id, "name": data.name})

    @post("/raw")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def raw(self, req: Request) -> Response:
        return req.res.json(await req.json())

    @post("/annotated")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def annotated(
        self, req: Request, data: Annotated[RequestBody[CreateUser], "extra"]
    ) -> Response:
        return req.res.json({"name": data.name})


@pytest.fixture
def app(make_app):
    return make_app(controllers=[UsersController])


def test_aliases_are_annotated_markers():
    plan = handler_params(UsersController.create)
    assert plan.body is not None
    assert plan.body.name == "data" and plan.body.model is CreateUser
    assert isinstance(plan.body.source, BodySource)
    assert [(p.name, p.model) for p in plan.query] == [("query", UserQuery)]
    assert isinstance(plan.query[0].source, QuerySource)
    assert handler_params(UsersController.raw).body is None
    # The plan is cached per function.
    assert handler_params(UsersController.create) is plan


async def test_query_params_are_validated_and_injected(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/users/", params={"page": "3", "orderBy": "name"})
        assert res.status_code == 200
        assert res.json() == {"page": 3, "tags": [], "order_by": "name"}

        # A single value fills a list field; repeated keys give every value.
        one = await client.get("/users/?tags=a")
        assert one.json()["tags"] == ["a"]
        two = await client.get("/users/?tags=a&tags=b")
        assert two.json()["tags"] == ["a", "b"]

        defaults = await client.get("/users/")
        assert defaults.json() == {"page": 1, "tags": [], "order_by": None}

        invalid = await client.get("/users/", params={"page": "x"})
        assert invalid.status_code == 422
        assert invalid.json()["data"][0]["loc"] == ["query", "page"]


async def test_several_query_models(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/users/paged", params={"limit": 5, "active": "true"})
        assert res.json() == {"limit": 5, "active": True}
        missing = await client.get("/users/paged")
        assert missing.status_code == 422
        assert missing.json()["data"][0]["loc"] == ["query", "limit"]


async def test_body_and_query_together(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/users/?page=2", json={"name": "Ada", "age": 36})
        assert res.status_code == 201
        assert res.json() == {"user": {"name": "Ada", "age": 36}, "page": 2}

        bad_body = await client.post("/users/", json={"name": "Ada"})
        assert bad_body.status_code == 422
        assert bad_body.json()["data"][0]["loc"] == ["body", "age"]

        bad_query = await client.post("/users/?page=x", json={"name": "Ada", "age": 36})
        assert bad_query.status_code == 422
        assert bad_query.json()["data"][0]["loc"] == ["query", "page"]


async def test_unsupported_media_type_runs_after_request_hooks(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/users/", content="name=Ada", headers={"content-type": "text/plain"}
        )
        assert res.status_code == 415
        assert res.json()["message"] == "Unsupported media type"
        assert res.headers["x-after"] == "yes"


async def test_form_body_with_route_value_and_any_decorator_order(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/users/7/form", data={"name": "Ada", "age": "36"})
        assert res.json() == {"group": 7, "name": "Ada"}


async def test_consumes_without_body_parameter_and_nested_annotated(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/users/raw", json={"anything": 1})
        assert res.json() == {"anything": 1}
        res = await client.post("/users/annotated", json={"name": "Ada", "age": 1})
        assert res.json() == {"name": "Ada"}


def _controller(method):
    return path("/broken")(type("BrokenController", (Controller,), {"m": method}))


def test_unmarked_model_parameter_fails_at_registration(make_app):
    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def m(self, req: Request, data: CreateUser) -> Response: ...

    with pytest.raises(TypeError, match=r"RequestBody\[CreateUser\] or QueryParams"):
        make_app(controllers=[_controller(m)])


def test_request_body_requires_consumes(make_app):
    @post("/")
    async def m(self, req: Request, data: RequestBody[CreateUser]) -> Response: ...

    with pytest.raises(TypeError, match="no @consumes"):
        make_app(controllers=[_controller(m)])


def test_only_one_request_body(make_app):
    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def m(
        self,
        req: Request,
        a: RequestBody[CreateUser],
        b: RequestBody[Filters],
    ) -> Response: ...

    with pytest.raises(TypeError, match="both RequestBody"):
        make_app(controllers=[_controller(m)])


def test_marker_requires_a_pydantic_model(make_app):
    @get("/")
    async def m(self, req: Request, page: QueryParams[int]) -> Response: ...

    with pytest.raises(TypeError, match="not a Pydantic model"):
        make_app(controllers=[_controller(m)])


@pytest.mark.parametrize("consumes_outermost", [True, False])
def test_get_cannot_consume_in_any_decorator_order(make_app, consumes_outermost):
    async def m(self, req: Request) -> Response: ...

    if consumes_outermost:
        m = consumes(MediaType.APPLICATION_JSON)(get("/")(m))
        with pytest.raises(UnexpectedDecorator):
            make_app(controllers=[_controller(m)])
    else:
        with pytest.raises(UnexpectedDecorator):
            get("/")(consumes(MediaType.APPLICATION_JSON)(m))


def test_socket_handlers_reject_markers(make_app):
    @socket("/ws")
    async def m(self, req: Request, query: QueryParams[UserQuery]) -> None: ...

    with pytest.raises(TypeError, match="WebSocket"):
        make_app(controllers=[_controller(m)])


def test_unresolvable_marked_annotation_is_reported():
    async def m(self, req: Request, data: RequestBody[Missing]) -> Response: ...  # noqa: F821

    with pytest.raises(TypeError, match="cannot resolve"):
        handler_params(m)


def test_openapi_documents_query_parameters_and_body(make_app):
    spec = make_app(controllers=[UsersController]).json_spec
    find = spec["paths"]["/users/"]["get"]
    assert "requestBody" not in find
    params = {p["name"]: p for p in find["parameters"]}
    assert set(params) == {"page", "tags", "orderBy"}
    assert params["page"] == {
        "name": "page",
        "in": "query",
        "required": False,
        "schema": {"default": 1, "type": "integer"},
    }
    assert params["tags"]["schema"]["type"] == "array"
    assert params["orderBy"]["description"] == "Sort field"

    paged = spec["paths"]["/users/paged"]["get"]
    paged_params = {p["name"]: p for p in paged["parameters"]}
    assert paged_params["limit"]["required"] is True
    assert paged_params["limit"]["schema"]["maximum"] == 100
    assert set(paged_params) == {"limit", "active"}

    create = spec["paths"]["/users/"]["post"]
    assert create["requestBody"] == {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/CreateUser"}}
        },
    }
    assert {p["name"] for p in create["parameters"]} == {"page", "tags", "orderBy"}
    assert "CreateUser" in spec["components"]["schemas"]
    # Query models are expanded into parameters, not registered as schemas.
    assert "UserQuery" not in spec["components"]["schemas"]

    form = spec["paths"]["/users/{group_id}/form"]["post"]
    assert [p["in"] for p in form["parameters"]] == ["path"]
    assert "application/x-www-form-urlencoded" in form["requestBody"]["content"]

    raw = spec["paths"]["/users/raw"]["post"]
    assert raw["requestBody"]["required"] is False
