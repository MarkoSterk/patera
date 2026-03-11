"""
OpenAPI controller
"""

import re
from typing import Any, Dict, Optional, Set, Type, Tuple, List, cast, Callable
from pydantic import BaseModel

from .http_statuses import HttpStatus
from .media_types import MediaType
from .response import Response
from .request import Request
from .controller import Controller, get, produces
from .controller.utilities import _extract_response_type

_WERKZEUG_PARAM_RE = re.compile(r"<(?:(int|string|path):)?([a-zA-Z_][a-zA-Z0-9_]*)>")


class OpenApiSpecs(BaseModel):
    openapi: str = "3.0.3"
    info: Any = None
    servers: Any = None
    paths: Any = None
    components: Any = None


class OpenAPIController(Controller):
    @get("/specs.json", open_api_spec=False)
    @produces(MediaType.APPLICATION_JSON)
    async def specs(self, req: Request) -> Response[OpenApiSpecs]:
        return req.response.json(self.app.json_spec).status(HttpStatus.OK)

    @get("/docs", open_api_spec=False)
    @produces(MediaType.TEXT_HTML)
    async def docs(self, req: Request) -> Response:
        return (
            await req.response.html_from_string("""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Swagger UI</title>
                <link rel="stylesheet"
                      href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4.18.3/swagger-ui.css" />
            </head>
            <body>
                <div id="swagger-ui"></div>
                <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@4.18.3/swagger-ui-bundle.js"></script>
                <script>
                    const ui = SwaggerUIBundle({
                        url: '{{ url_for("OpenAPIController.specs") }}',
                        dom_id: '#swagger-ui',
                    })
                </script>
            </body>
        </html>
        """)
        ).status(HttpStatus.OK)


def _as_media_type(mt: Any) -> str:
    # Accept enum-ish (with .value) or plain str
    if mt is None:
        return "application/json"
    return getattr(mt, "value", str(mt))


def _as_status_code(http_status: HttpStatus | int) -> int:
    if isinstance(http_status, HttpStatus):
        return http_status.value
    return http_status


def _model_name(model: Type) -> str:
    # Pick a stable schema key
    return getattr(model, "__name__", "AnonymousModel")


def _pydantic_schema_dict(model: Optional[Type]) -> Optional[Dict[str, Any]]:
    if model is None:
        return None
    # Pydantic v2
    if hasattr(model, "model_json_schema"):
        try:
            return model.model_json_schema(ref_template="#/components/schemas/{model}")
        except TypeError:
            # older/stricter signatures
            return model.model_json_schema()
    # Pydantic v1
    if hasattr(model, "schema"):
        try:
            return model.schema(ref_template="#/components/schemas/{model}")
        except TypeError:
            return model.schema()
    # Fallback – unknown object
    return {"type": "object"}


def _rebuild_model(model: Optional[Type]) -> None:
    if model is None:
        return
    # Pydantic v2
    if hasattr(model, "model_rebuild"):
        try:
            model.model_rebuild()
        except TypeError:
            pass
    # Pydantic v1
    if hasattr(model, "update_forward_refs"):
        try:
            # model.update_forward_refs()
            model.model_rebuild()
        except TypeError:
            pass


def _pydantic_schema_and_defs(
    model: Optional[Type],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Returns (schema_for_model, defs) where defs are nested component schemas
    that must be merged into components/schemas.
    """
    if model is None:
        return None, {}

    _rebuild_model(model)

    # Pydantic v2
    if hasattr(model, "model_json_schema"):
        try:
            schema = model.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
        except TypeError:
            schema = model.model_json_schema()
        defs = schema.pop("$defs", {}) or {}
        return schema, defs

    # Pydantic v1
    if hasattr(model, "schema"):
        try:
            schema = model.schema(ref_template="#/components/schemas/{model}")
        except TypeError:
            schema = model.schema()
        defs = schema.pop("definitions", {}) or {}
        return schema, defs

    # Fallback
    return {"type": "object"}, {}


def _ensure_schema(
    components: Dict[str, Any], model: Optional[Type]
) -> Optional[Dict[str, Any]]:
    if model is None:
        return None

    name = _model_name(model)
    if "schemas" not in components:
        components["schemas"] = {}

    # Get schema and nested defs
    schema, defs = _pydantic_schema_and_defs(model)

    # Merge nested defs first (don't overwrite if already present)
    for def_name, def_schema in defs.items():
        components["schemas"].setdefault(def_name, def_schema)

    # Register the model schema itself (if not already present)
    if name not in components["schemas"]:
        components["schemas"][name] = schema or {"type": "object"}

    # Return a $ref to the component
    return {"$ref": f"#/components/schemas/{name}"}


_TYPE_MAP = {
    "int": {"type": "integer", "format": "int64"},
    "string": {"type": "string"},
    "path": {
        "type": "string"
    },  # openapi does not have a special type for path. Will be treated as string with x-greedy-path: true
}


def _convert_path_and_extract_params(path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Convert Flask-style route params in `path` to OpenAPI templating and
    return (converted_path, parameters_list).
    """
    params: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def _repl(m: re.Match) -> str:
        typ = m.group(1) or "string"
        name = m.group(2)
        if name not in seen:
            seen.add(name)
            schema = _TYPE_MAP.get(typ, {"type": "string"})
            param: Dict[str, Any] = {
                "in": "path",
                "name": name,
                "required": True,
                "schema": dict(schema),  # copy
            }
            if typ == "path":
                param["x-greedy-path"] = True
                param["description"] = (param.get("description") or "") + (
                    " Greedy path segment captured by the server."
                )
            params.append(param)
        return "{" + name + "}"

    converted = _WERKZEUG_PARAM_RE.sub(_repl, path)
    return converted, params


def build_openapi(
    controllers: Dict[str, "Controller"],
    *,
    title: str,
    version: str,
    openapi_version: str,
    servers: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    controllers structure: {
        "<base_path>": {
            "<HTTP_METHOD>": {
                "<endpoint_path>": {
                    "method": <callable>,
                    "produces": <MediaType>,
                    "consumes": <MediaType>,
                    "consumes_type": <PydanticModel>,
                    "response_type": <PydanticModel>, # optional
                    "default_status_code": <HttpStatus>,
                    "http_method": <HTTP_METHOD>,
                    "path": <endpoint_path>,
                    "base_path": <base_path>,
                    "summary": <string>, # optional
                    "description": <string>, # optional
                    "tags": [<string>, ...], # optional
                    "operation_id": <string>, # optional
                    "error_responses": [<Descriptor>, ...]
                }
            }
        }
    }
    Descriptor has: media_type, body, description, status (default BAD_REQUEST).
    """
    spec: Dict[str, Any] = {
        "openapi": openapi_version,
        "info": {"title": title, "version": version, "description": ""},
        "paths": {},
        "components": {"schemas": {}},
    }
    if servers:
        spec["servers"] = [{"url": url} for url in servers]

    components = spec["components"]
    paths = spec["paths"]

    referenced_models: Set[Type] = set()

    for base_path, controller in controllers.items():
        if not controller.open_api_spec:
            continue

        for http_method, endpoints_map in controller.endpoints_map.items():
            for endpoint_path, ep_cfg in endpoints_map.items():
                if not cast(dict, ep_cfg).get("open_api_spec"):
                    continue

                # Build raw path first
                raw_full_path = (
                    f"/{base_path.strip('/')}/{endpoint_path.strip('/')}".replace(
                        "//", "/"
                    )
                )
                if base_path == "/":
                    raw_full_path = f"/{endpoint_path.strip('/')}" or "/"

                # Converts dynamic paths to OpenApi complient format and generates path schema
                full_path, path_params = _convert_path_and_extract_params(raw_full_path)

                if full_path not in paths:
                    paths[full_path] = {}

                op_obj: Dict[str, Any] = {}
                paths[full_path][http_method.lower()] = op_obj

                # Summary / description
                op_obj["summary"] = cast(dict, ep_cfg).get("summary", "")
                op_obj["description"] = cast(dict, ep_cfg).get(
                    "method"
                ).__doc__ or cast(dict, ep_cfg).get("description", "")

                # Tags
                tags = cast(dict, ep_cfg).get("tags")
                if tags:
                    op_obj["tags"] = tags

                # operationId
                op_obj["operationId"] = cast(
                    Callable, cast(dict[str, Callable], ep_cfg).get("method")
                ).__name__ or (
                    f"{http_method.lower()}_{base_path.strip('/').replace('/', '_')}_{endpoint_path.strip('/').replace('/', '_')}"
                    or f"{http_method.lower()}_root"
                )

                # Path parameters
                if path_params:
                    op_obj["parameters"] = [*path_params]

                # Request body
                consumes = cast(str, cast(dict, ep_cfg).get("consumes"))
                consumes_type = cast(Type, cast(dict, ep_cfg).get("consumes_type"))
                if consumes or consumes_type:
                    mt = _as_media_type(consumes) if consumes else "application/json"
                    schema_ref = _ensure_schema(components, consumes_type)
                    if consumes_type:
                        try:
                            referenced_models.add(consumes_type)
                        except TypeError:
                            pass
                    op_obj["requestBody"] = {
                        "required": True if consumes_type else False,
                        "content": {mt: {"schema": schema_ref or {"type": "object"}}},
                    }

                # Responses
                produces = cast(str, cast(dict, ep_cfg).get("produces"))
                mt_out = _as_media_type(produces) if produces else "application/json"
                default_status = _as_status_code(
                    cast(int, cast(dict, ep_cfg).get("default_status_code", 200))
                )
                responses: Dict[int, Any] = {}
                op_obj["responses"] = responses

                response_type = _extract_response_type(
                    cast(str, cast(dict, ep_cfg).get("method"))
                )
                resp_schema_ref = (
                    _ensure_schema(components, response_type) if response_type else None
                )
                if response_type:
                    try:
                        referenced_models.add(response_type)
                    except TypeError:
                        pass

                responses[default_status] = {
                    "description": cast(str, cast(dict, ep_cfg).get("description", ""))
                    or "",
                    "content": {
                        mt_out: {"schema": resp_schema_ref or {"type": "object"}}
                    },
                }

                # Error responses
                for desc in (
                    cast(list, cast(dict, ep_cfg).get("error_responses", [])) or []
                ):
                    status_code = _as_status_code(
                        cast(int, getattr(desc, "status", None))
                    )
                    err_response_type = _as_media_type(
                        getattr(desc, "media_type", None)
                    )
                    body_model = getattr(desc, "body", None)
                    err_desc = getattr(desc, "description", None) or ""

                    schema_ref = _ensure_schema(components, body_model)
                    if body_model:
                        try:
                            referenced_models.add(body_model)
                        except TypeError:
                            pass

                    if status_code not in responses:
                        responses[status_code] = {
                            "description": err_desc or "",
                            "content": {},
                        }
                    if not responses[status_code].get("description"):
                        responses[status_code]["description"] = err_desc or ""

                    responses[status_code]["content"][err_response_type] = {
                        "schema": schema_ref or {"type": "object"}
                    }

    return spec
