from __future__ import annotations

from pydantic import BaseModel

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import (
    Controller,
    Descriptor,
    consumes,
    get,
    open_api_docs,
    path,
    post,
    produces,
)
from patera.open_api import _convert_path_and_extract_params, _unique_operation_id


class Pet(BaseModel):
    id: int
    name: str


class Owner(BaseModel):
    name: str
    pets: list[Pet]


class ErrorBody(BaseModel):
    message: str


@path("/pets", tags=["Pets"])
class PetController(Controller):
    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def list_pets(self, req: Request) -> Response[list[Pet]]:
        """List all pets"""
        return req.res.json([])

    @get("/<int:pet_id>")
    @open_api_docs(Descriptor(HttpStatus.NOT_FOUND, "Missing", body=ErrorBody))
    async def get_pet(self, req: Request, pet_id: int) -> Response[Pet]:
        return req.res.json({"id": pet_id, "name": "x"})

    @post("/owners")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def create_owner(self, req: Request, owner: Owner) -> Response[Owner]:
        return req.res.json(owner)

    @get("/hidden", open_api_spec=False)
    async def hidden(self, req: Request) -> Response:
        return req.res.text("x")


@path("/other", open_api_spec=False)
class HiddenController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("x")


def test_convert_path_parameters():
    converted, params = _convert_path_and_extract_params(
        "/a/<int:id>/<float:ratio>/<uuid:key>/<path:rest>/<int(signed=True):n>/<name>"
    )
    assert converted == "/a/{id}/{ratio}/{key}/{rest}/{n}/{name}"
    by_name = {p["name"]: p for p in params}
    assert by_name["id"]["schema"]["type"] == "integer"
    assert by_name["ratio"]["schema"]["type"] == "number"
    assert by_name["key"]["schema"]["format"] == "uuid"
    assert by_name["rest"]["x-greedy-path"] is True
    assert by_name["n"]["schema"]["type"] == "integer"
    assert by_name["name"]["schema"]["type"] == "string"


def test_spec_contents(make_app):
    app = make_app(
        controllers=[PetController, HiddenController],
        OPEN_API_DESCRIPTION="Pet store",
        PORT=9000,
    )
    spec = app.json_spec
    assert spec["info"] == {
        "title": "Test app",
        "version": "1.0",
        "description": "Pet store",
    }
    # A relative server: Swagger calls the origin that served the document.
    assert spec["servers"] == [{"url": "/"}]

    paths = spec["paths"]
    assert "/other/" not in paths
    assert "/pets/hidden" not in paths

    list_op = paths["/pets/"]["get"]
    assert list_op["description"] == "List all pets"
    assert list_op["tags"] == ["Pets"]
    list_schema = list_op["responses"][200]["content"]["application/json"]["schema"]
    assert list_schema == {
        "items": {"$ref": "#/components/schemas/Pet"},
        "type": "array",
    }

    get_op = paths["/pets/{pet_id}"]["get"]
    assert get_op["parameters"][0]["name"] == "pet_id"
    assert get_op["responses"][404]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorBody"
    }

    create = paths["/pets/owners"]["post"]
    assert create["requestBody"]["required"] is True
    assert create["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Owner"
    }
    assert 201 in create["responses"]

    schemas = spec["components"]["schemas"]
    assert {"Pet", "Owner", "ErrorBody"} <= set(schemas)


def test_spec_includes_controllers_registered_later(make_app):
    app = make_app()
    assert "/pets/" not in app.json_spec["paths"]
    app.register_controller(PetController)
    assert "/pets/" in app.json_spec["paths"]


def test_tags_do_not_accumulate_across_apps(make_app):
    for _ in range(3):
        app = make_app(controllers=[PetController])
        assert app.json_spec["paths"]["/pets/"]["get"]["tags"] == ["Pets"]


def test_url_prefix_is_part_of_server_url(make_app):
    app = make_app(controllers=[PetController], URL_PREFIX="/v2")
    assert app.json_spec["servers"] == [{"url": "/v2"}]


@path("/first")
class FirstController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        """Lists the first things.

        A longer explanation that belongs in the description.
        """
        return req.res.json([])


@path("/second")
class SecondController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.json([])


def test_operation_ids_are_unique_across_controllers(make_app):
    app = make_app(controllers=[FirstController, SecondController])
    paths = app.json_spec["paths"]
    first = paths["/first/"]["get"]["operationId"]
    second = paths["/second/"]["get"]["operationId"]
    assert first == "FirstController_index"
    assert second == "SecondController_index"


def test_unique_operation_id_adds_a_suffix():
    used: set[str] = set()
    assert _unique_operation_id("Items_index", used) == "Items_index"
    assert _unique_operation_id("Items_index", used) == "Items_index_2"
    assert _unique_operation_id("Items_index", used) == "Items_index_3"


def test_summary_comes_from_the_docstring(make_app):
    app = make_app(controllers=[FirstController, SecondController, PetController])
    paths = app.json_spec["paths"]
    first = paths["/first/"]["get"]
    assert first["summary"] == "Lists the first things."
    assert "longer explanation" in first["description"]
    assert paths["/pets/"]["get"]["summary"] == "List all pets"
    # No docstring: empty summary and description.
    assert paths["/second/"]["get"]["summary"] == ""
    assert paths["/second/"]["get"]["description"] == ""
