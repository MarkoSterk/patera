"""
RequestBody[list[Model]] for JSON bodies, and Files[...] parameters for the
files of a multipart body, next to the all-in-one RequestBody[Model].
"""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict, Field, field_validator

from patera import MediaType, Request, Response, UploadedFile
from patera.controller import (
    Controller,
    Files,
    QueryParams,
    RequestBody,
    consumes,
    path,
    post,
    produces,
)
from patera.controller.params import handler_params


class UserCreate(BaseModel):
    name: str = Field(min_length=1)


class UploadForm(BaseModel):
    """All-in-one multipart model: text fields and files together."""

    title: str
    attachment: UploadedFile
    extras: list[UploadedFile] = []


class ProfileForm(BaseModel):
    # Forbidding extras proves that file fields are not passed to the model.
    model_config = ConfigDict(extra="forbid")

    display_name: str
    tags: list[str] = []


class FileInfo(BaseModel):
    title: str
    attachment: UploadedFile


def describe(file: UploadedFile) -> dict:
    return {"name": file.filename, "data": file.read().decode()}


@path("/api")
class UploadsController(Controller):
    @post("/users")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def create_users(
        self, req: Request, data: RequestBody[list[UserCreate]]
    ) -> Response:
        return req.res.json([user.name for user in data])

    @post("/numbers")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def numbers(
        self, req: Request, data: RequestBody[dict[str, int]]
    ) -> Response:
        return req.res.json({"total": sum(data.values())})

    @post("/combined")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def combined(self, req: Request, data: RequestBody[UploadForm]) -> Response:
        return req.res.json(
            {
                "title": data.title,
                "attachment": describe(data.attachment),
                "extras": [describe(f) for f in data.extras],
            }
        )

    @post("/profile")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def profile(
        self,
        req: Request,
        data: RequestBody[ProfileForm],
        avatar: Files[UploadedFile],
        attachments: Files[list[UploadedFile]],
        cover: Files[Optional[UploadedFile]],
    ) -> Response:
        return req.res.json(
            {
                "form": data.model_dump(),
                "avatar": describe(avatar),
                "attachments": [describe(f) for f in attachments],
                "cover": describe(cover) if cover else None,
            }
        )

    @post("/files-only")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def files_only(
        self, req: Request, document: Files[UploadedFile] = None
    ) -> Response:
        return req.res.json({"document": describe(document) if document else None})

    @post("/everything")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def everything(
        self, req: Request, files: Files[dict[str, list[UploadedFile]]]
    ) -> Response:
        return req.res.json(
            {key: [f.filename for f in values] for key, values in files.items()}
        )

    @post("/info")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def info(
        self, req: Request, data: RequestBody[FileInfo]
    ) -> Response[FileInfo]:
        return req.res.json(data)


@pytest.fixture
def app(make_app):
    return make_app(controllers=[UploadsController])


# --- JSON bodies that are not a single object --------------------------------


def test_list_body_plan_uses_a_type_adapter():
    plan = handler_params(UploadsController.create_users)
    assert plan.body is not None
    assert plan.body.model == list[UserCreate]
    assert not plan.body.is_model and plan.body.adapter is not None


async def test_list_body_is_validated_item_by_item(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/api/users", json=[{"name": "Ada"}, {"name": "Bo"}])
        assert res.status_code == 200
        assert res.json() == ["Ada", "Bo"]

        assert (await client.post("/api/users", json=[])).json() == []

        bad = await client.post("/api/users", json=[{"name": "Ada"}, {"name": ""}])
        assert bad.status_code == 422
        assert bad.json()["data"][0]["loc"] == ["body", 1, "name"]

        not_a_list = await client.post("/api/users", json={"name": "Ada"})
        assert not_a_list.status_code == 422
        assert not_a_list.json()["data"][0]["loc"] == ["body"]

        empty = await client.post(
            "/api/users", content=b"", headers={"content-type": "application/json"}
        )
        assert empty.status_code == 422


async def test_other_json_types(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/api/numbers", json={"a": 1, "b": "2"})
        assert res.json() == {"total": 3}
        bad = await client.post("/api/numbers", json={"a": "x"})
        assert bad.status_code == 422
        assert bad.json()["data"][0]["loc"] == ["body", "a"]


# --- The all-in-one multipart model keeps working ------------------------------


async def test_all_in_one_model_takes_fields_and_files(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/combined",
            data={"title": "Report"},
            files=[
                ("attachment", ("a.txt", b"A", "text/plain")),
                ("extras", ("e1.txt", b"E1", "text/plain")),
            ],
        )
        assert res.status_code == 200, res.text
        assert res.json() == {
            "title": "Report",
            "attachment": {"name": "a.txt", "data": "A"},
            # A single file for a list field arrives as a one-item list.
            "extras": [{"name": "e1.txt", "data": "E1"}],
        }

        two = await client.post(
            "/api/combined",
            data={"title": "Report"},
            files=[
                ("attachment", ("a.txt", b"A", "text/plain")),
                ("extras", ("e1.txt", b"E1", "text/plain")),
                ("extras", ("e2.txt", b"E2", "text/plain")),
            ],
        )
        assert [e["name"] for e in two.json()["extras"]] == ["e1.txt", "e2.txt"]


async def test_text_sent_for_a_file_field_is_a_validation_error(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/combined",
            data={"title": "Report", "attachment": "not a file"},
            files=[("extras", ("e.txt", b"E", "text/plain"))],
        )
        assert res.status_code == 422
        assert res.json()["data"][0]["loc"] == ["body", "attachment"]


# --- Files[...] parameters ----------------------------------------------------


async def test_files_are_split_from_the_form_fields(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/profile",
            data={"display_name": "Ada", "tags": "x"},
            files=[
                ("avatar", ("me.png", b"PNG", "image/png")),
                ("attachments", ("cv.pdf", b"PDF", "application/pdf")),
            ],
        )
        assert res.status_code == 200, res.text
        assert res.json() == {
            "form": {"display_name": "Ada", "tags": ["x"]},
            "avatar": {"name": "me.png", "data": "PNG"},
            "attachments": [{"name": "cv.pdf", "data": "PDF"}],
            "cover": None,
        }

        several = await client.post(
            "/api/profile",
            data={"display_name": "Ada"},
            files=[
                ("avatar", ("me.png", b"PNG", "image/png")),
                ("cover", ("c.png", b"C", "image/png")),
                ("attachments", ("1.txt", b"1", "text/plain")),
                ("attachments", ("2.txt", b"2", "text/plain")),
            ],
        )
        body = several.json()
        assert [a["name"] for a in body["attachments"]] == ["1.txt", "2.txt"]
        assert body["cover"] == {"name": "c.png", "data": "C"}


async def test_list_files_default_to_an_empty_list(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/profile",
            data={"display_name": "Ada"},
            files=[("avatar", ("me.png", b"PNG", "image/png"))],
        )
        assert res.status_code == 200, res.text
        assert res.json()["attachments"] == []


async def test_missing_or_repeated_single_file_is_422(app, client_for):
    async with client_for(app) as client:
        missing = await client.post(
            "/api/profile",
            data={"display_name": "Ada"},
            files=[("attachments", ("1.txt", b"1", "text/plain"))],
        )
        assert missing.status_code == 422
        assert missing.json()["data"][0]["loc"] == ["files", "avatar"]

        twice = await client.post(
            "/api/profile",
            data={"display_name": "Ada"},
            files=[
                ("avatar", ("1.png", b"1", "image/png")),
                ("avatar", ("2.png", b"2", "image/png")),
            ],
        )
        assert twice.status_code == 422
        error = twice.json()["data"][0]
        assert error["loc"] == ["files", "avatar"]
        assert "several" in error["msg"]

        bad_form = await client.post(
            "/api/profile",
            data={"display_name": "Ada", "unknown": "x"},
            files=[("avatar", ("me.png", b"PNG", "image/png"))],
        )
        assert bad_form.status_code == 422
        assert bad_form.json()["data"][0]["loc"] == ["body", "unknown"]


async def test_files_without_a_body_model(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/files-only",
            files=[("document", ("d.txt", b"D", "text/plain"))],
        )
        assert res.json() == {"document": {"name": "d.txt", "data": "D"}}
        # A multipart body with a text field and no file.
        none = await client.post("/api/files-only", files=[("note", (None, "x"))])
        assert none.json() == {"document": None}


async def test_every_file_by_field_name(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/everything",
            files=[
                ("a", ("a1.txt", b"1", "text/plain")),
                ("b", ("b1.txt", b"1", "text/plain")),
                ("b", ("b2.txt", b"2", "text/plain")),
            ],
        )
        assert res.json() == {"a": ["a1.txt"], "b": ["b1.txt", "b2.txt"]}


# --- Registration errors -------------------------------------------------------


def _controller(method):
    return path("/broken")(type("BrokenController", (Controller,), {"m": method}))


@pytest.mark.parametrize(
    "media_type",
    [MediaType.APPLICATION_X_WWW_FORM_URLENCODED, MediaType.MULTIPART_FORM_DATA],
)
def test_list_body_is_json_only(make_app, media_type):
    @post("/")
    @consumes(media_type)
    async def m(
        self, req: Request, data: RequestBody[list[UserCreate]]
    ) -> Response: ...

    with pytest.raises(TypeError, match="form body is one set of fields"):
        make_app(controllers=[_controller(m)])


def test_files_need_a_multipart_endpoint(make_app):
    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def m(self, req: Request, avatar: Files[UploadedFile]) -> Response: ...

    with pytest.raises(TypeError, match="MULTIPART_FORM_DATA"):
        make_app(controllers=[_controller(m)])


@pytest.mark.parametrize(
    "annotation",
    [
        "Files[str]",
        "Files[list[str]]",
        "Files[dict[str, UploadedFile]]",
        "Files[Optional[dict[str, list[UploadedFile]]]]",
    ],
)
def test_unsupported_files_types(annotation):
    async def m(self, req: Request, upload) -> Response: ...

    m.__annotations__["upload"] = annotation
    with pytest.raises(TypeError, match="Use Files"):
        handler_params(m)


def test_body_model_with_file_fields_cannot_mix_with_files(make_app):
    @post("/")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    async def m(
        self,
        req: Request,
        data: RequestBody[UploadForm],
        cover: Files[UploadedFile],
    ) -> Response: ...

    with pytest.raises(TypeError, match="UploadForm.attachment is a file field"):
        make_app(controllers=[_controller(m)])


def test_body_field_and_files_parameter_cannot_share_a_name(make_app):
    @post("/")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    async def m(
        self,
        req: Request,
        data: RequestBody[ProfileForm],
        display_name: Files[UploadedFile],
    ) -> Response: ...

    with pytest.raises(TypeError, match="'display_name' is both"):
        make_app(controllers=[_controller(m)])


def test_only_one_catch_all_files_parameter():
    async def m(
        self,
        req: Request,
        a: Files[dict[str, list[UploadedFile]]],
        b: Files[dict[str, list[UploadedFile]]],
    ) -> Response: ...

    with pytest.raises(TypeError, match="both take every file"):
        handler_params(m)


def test_query_params_still_need_a_model():
    async def m(self, req: Request, q: QueryParams[list[UserCreate]]) -> Response: ...

    with pytest.raises(TypeError, match="not a Pydantic model"):
        handler_params(m)


# --- OpenAPI -------------------------------------------------------------------


def test_openapi_list_body(make_app):
    spec = make_app(controllers=[UploadsController]).json_spec
    body = spec["paths"]["/api/users"]["post"]["requestBody"]
    assert body["required"] is True
    assert body["content"]["application/json"]["schema"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/UserCreate"},
    }
    assert "UserCreate" in spec["components"]["schemas"]


def test_openapi_all_in_one_model_documents_binary_files(make_app):
    spec = make_app(controllers=[UploadsController]).json_spec
    content = spec["paths"]["/api/combined"]["post"]["requestBody"]["content"]
    assert content["multipart/form-data"]["schema"] == {
        "$ref": "#/components/schemas/UploadForm"
    }
    props = spec["components"]["schemas"]["UploadForm"]["properties"]
    assert props["attachment"]["format"] == "binary"
    assert props["extras"]["items"] == {"type": "string", "format": "binary"}


def test_openapi_files_parameters(make_app):
    spec = make_app(controllers=[UploadsController]).json_spec
    profile = spec["paths"]["/api/profile"]["post"]["requestBody"]
    schema = profile["content"]["multipart/form-data"]["schema"]
    assert profile["required"] is True
    assert schema["type"] == "object"
    props = schema["properties"]
    assert set(props) == {"display_name", "tags", "avatar", "attachments", "cover"}
    assert props["avatar"]["format"] == "binary"
    assert props["attachments"]["items"] == {"type": "string", "format": "binary"}
    assert set(schema["required"]) == {"display_name", "avatar"}
    assert "additionalProperties" not in schema

    everything = spec["paths"]["/api/everything"]["post"]["requestBody"]
    everything_schema = everything["content"]["multipart/form-data"]["schema"]
    assert everything_schema["additionalProperties"] == {
        "type": "array",
        "items": {"type": "string", "format": "binary"},
    }


def test_openapi_uploaded_file_in_a_response_is_metadata(make_app):
    spec = make_app(controllers=[UploadsController]).json_spec
    schemas = spec["components"]["schemas"]
    # The request reads the file; the response sends its metadata.
    assert schemas["FileInfo"]["properties"]["attachment"]["format"] == "binary"
    output = schemas["FileInfoOutput"]["properties"]["attachment"]
    assert output["type"] == "object"
    assert set(output["properties"]) == {"filename", "content_type", "size"}
    info = spec["paths"]["/api/info"]["post"]
    assert info["responses"][200]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FileInfoOutput"
    }
    assert "x-patera-schema-modes" not in spec["components"]


# --- Files[Model] ----------------------------------------------------------------


class ProfileFiles(BaseModel):
    picture: UploadedFile = Field(alias="profile-picture")
    documents: list[UploadedFile] = []

    @field_validator("picture")
    @classmethod
    def picture_is_png(cls, value: UploadedFile) -> UploadedFile:
        if not value.filename.lower().endswith(".png"):
            raise ValueError("The profile picture must be a PNG file")
        return value


@path("/models")
class FileModelsController(Controller):
    @post("/profile")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def profile(
        self,
        req: Request,
        data: RequestBody[ProfileForm],
        uploads: Files[ProfileFiles],
        extra: Files[list[UploadedFile]],
    ) -> Response:
        return req.res.json(
            {
                "name": data.display_name,
                "picture": describe(uploads.picture),
                "documents": [f.filename for f in uploads.documents],
                "extra": [f.filename for f in extra],
            }
        )

    @post("/only")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    async def only(self, req: Request, uploads: Files[ProfileFiles]) -> Response:
        return req.res.json({"picture": uploads.picture.filename})


async def test_files_model_is_validated_like_any_model(make_app, client_for):
    app = make_app(controllers=[FileModelsController])
    async with client_for(app) as client:
        res = await client.post(
            "/models/profile",
            data={"display_name": "Ada"},
            files=[
                ("profile-picture", ("me.png", b"PNG", "image/png")),
                ("documents", ("cv.pdf", b"PDF", "application/pdf")),
                ("extra", ("x.txt", b"X", "text/plain")),
            ],
        )
        assert res.status_code == 200, res.text
        assert res.json() == {
            "name": "Ada",
            "picture": {"name": "me.png", "data": "PNG"},
            "documents": ["cv.pdf"],
            "extra": ["x.txt"],
        }

        wrong = await client.post(
            "/models/only",
            files=[("profile-picture", ("me.gif", b"GIF", "image/gif"))],
        )
        assert wrong.status_code == 422
        error = wrong.json()["data"][0]
        assert error["loc"] == ["files", "profile-picture"]
        assert "PNG" in error["msg"]

        missing = await client.post("/models/only", files=[("note", (None, "x"))])
        assert missing.status_code == 422
        assert missing.json()["data"][0]["loc"] == ["files", "profile-picture"]


class MixedFiles(BaseModel):
    picture: UploadedFile
    caption: str


def test_files_model_fields_must_be_files():
    async def m(self, req: Request, uploads: Files[MixedFiles]) -> Response: ...

    with pytest.raises(TypeError, match="MixedFiles.caption is not a file field"):
        handler_params(m)


def test_files_model_cannot_be_optional():
    async def m(
        self, req: Request, uploads: Files[Optional[ProfileFiles]]
    ) -> Response: ...

    with pytest.raises(TypeError, match="Use Files"):
        handler_params(m)


def test_a_file_field_is_bound_once():
    async def m(
        self,
        req: Request,
        uploads: Files[ProfileFiles],
        documents: Files[list[UploadedFile]],
    ) -> Response: ...

    with pytest.raises(TypeError, match="'documents' is taken by both"):
        handler_params(m)


class DocumentsForm(BaseModel):
    documents: str


def test_body_field_cannot_share_a_name_with_a_files_model_field(make_app):
    @post("/")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    async def m(
        self,
        req: Request,
        data: RequestBody[DocumentsForm],
        uploads: Files[ProfileFiles],
    ) -> Response: ...

    with pytest.raises(TypeError, match="'documents' is both"):
        make_app(controllers=[_controller(m)])


def test_openapi_files_model(make_app):
    spec = make_app(controllers=[FileModelsController]).json_spec
    body = spec["paths"]["/models/profile"]["post"]["requestBody"]
    schema = body["content"]["multipart/form-data"]["schema"]
    props = schema["properties"]
    assert set(props) == {
        "display_name",
        "tags",
        "profile-picture",
        "documents",
        "extra",
    }
    assert props["profile-picture"]["format"] == "binary"
    assert set(schema["required"]) == {"display_name", "profile-picture"}
