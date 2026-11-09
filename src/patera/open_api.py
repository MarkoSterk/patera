"""
OpenAPI controller
"""

import inspect
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Type, cast
from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import JsonSchemaMode

from .http_statuses import HttpStatus
from .media_types import MediaType
from .response import Response
from .request import Request
from .controller import Controller, get, produces
from .controller.params import HandlerParams, handler_params
from .utilities import _extract_response_type

# Matches werkzeug route parameters such as <id>, <int:id>, <int(signed=True):id>
# or <any(a, b):kind>.
_WERKZEUG_PARAM_RE = re.compile(
    r"<(?:([a-zA-Z_][a-zA-Z0-9_]*)(?:\([^)]*\))?:)?([a-zA-Z_][a-zA-Z0-9_]*)>"
)


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


_REF_TEMPLATE = "#/components/schemas/{model}"
# Remembers in which mode each component was registered; removed from the
# finished document.
_MODES_KEY = "x-patera-schema-modes"


def _is_model_class(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _pydantic_schema_and_defs(
    model: Optional[Type],
    mode: JsonSchemaMode = "validation",
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Returns (schema_for_type, defs) where defs are nested component schemas
    that must be merged into components/schemas.

    Pydantic models and any other type Pydantic understands (list[Model],
    dict[str, int], unions, ...) are supported. Request data is described
    in "validation" mode (what the server accepts, an UploadedFile is a
    binary file), responses in "serialization" mode (what it sends, an
    UploadedFile is its metadata).
    """
    if model is None:
        return None, {}

    try:
        if _is_model_class(model):
            model.model_rebuild()
            schema = model.model_json_schema(ref_template=_REF_TEMPLATE, mode=mode)
        else:
            schema = TypeAdapter(model).json_schema(
                ref_template=_REF_TEMPLATE, mode=mode
            )
    except Exception:
        # Types Pydantic cannot describe are documented as generic objects.
        return {"type": "object"}, {}

    defs = schema.pop("$defs", {}) or {}
    return schema, defs


def _ensure_schema(
    components: Dict[str, Any],
    model: Optional[Type],
    mode: JsonSchemaMode = "validation",
) -> Optional[Dict[str, Any]]:
    """
    Registers the schema of ``model`` in components and returns a schema
    object for it: a $ref for Pydantic models, an inline schema otherwise.
    A model whose request and response schemas differ (it has file fields,
    computed fields, ...) gets a second component suffixed Input or Output.
    """
    if model is None:
        return None

    if "schemas" not in components:
        components["schemas"] = {}
    modes: Dict[str, str] = components.setdefault(_MODES_KEY, {})

    # Get schema and nested defs
    schema, defs = _pydantic_schema_and_defs(model, mode)

    # Merge nested defs first (don't overwrite if already present)
    for def_name, def_schema in defs.items():
        components["schemas"].setdefault(def_name, def_schema)

    if not _is_model_class(model):
        return schema or {"type": "object"}

    name = _model_name(model)
    schema = schema or {"type": "object"}
    registered = components["schemas"].get(name)
    if (
        registered is not None
        and registered != schema
        and modes.get(name, mode) != mode
    ):
        name += "Input" if mode == "validation" else "Output"
    # Register the model schema itself (if not already present)
    if name not in components["schemas"]:
        components["schemas"][name] = schema
        modes[name] = mode

    # Return a $ref to the component
    return {"$ref": f"#/components/schemas/{name}"}


_BINARY = {"type": "string", "format": "binary"}


def _multipart_schema(
    components: Dict[str, Any], plan: "HandlerParams"
) -> Dict[str, Any]:
    """
    One multipart/form-data object for an endpoint with Files parameters:
    the RequestBody model's form fields plus one binary property (or array
    of them) per Files parameter. A Files[dict[...]] parameter accepts files
    under any name.
    """
    components.setdefault("schemas", {})
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for model in (
        plan.body.model if plan.body is not None else None,
        plan.files_model,
        *(p.model for p in plan.file_models),
    ):
        schema, defs = _pydantic_schema_and_defs(model)
        for def_name, def_schema in defs.items():
            components["schemas"].setdefault(def_name, def_schema)
        if not schema:
            continue
        properties.update(schema.get("properties") or {})
        required.extend(schema.get("required") or [])

    result: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    if plan.all_files is not None:
        result["additionalProperties"] = {"type": "array", "items": dict(_BINARY)}
    return result


# OpenAPI 3.0 ignores header parameters with these names; they are described
# by the request body's media type and the security schemes instead.
_IGNORED_HEADER_PARAMETERS = {"accept", "content-type", "authorization"}


def _query_parameters(
    components: Dict[str, Any],
    model: Type[BaseModel],
    location: str = "query",
    names: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    OpenAPI parameters (``in: query``, ``header`` or ``cookie``) for the
    fields of a QueryParams, Headers or Cookies model. Field aliases are
    used, or ``names`` maps them to the header and cookie names a client
    sends; nested models are registered in components.
    """
    schema, defs = _pydantic_schema_and_defs(model)
    components.setdefault("schemas", {})
    for def_name, def_schema in defs.items():
        components["schemas"].setdefault(def_name, def_schema)

    schema = schema or {}
    required = set(schema.get("required", []))
    parameters: List[Dict[str, Any]] = []
    for key, field_schema in (schema.get("properties") or {}).items():
        name = (names or {}).get(key, key)
        if location == "header" and name.lower() in _IGNORED_HEADER_PARAMETERS:
            continue
        field_schema = dict(field_schema)
        param: Dict[str, Any] = {
            "name": name,
            "in": location,
            "required": key in required,
        }
        description = field_schema.pop("description", None)
        if description:
            param["description"] = description
        field_schema.pop("title", None)
        param["schema"] = field_schema or {}
        parameters.append(param)
    return parameters


_TYPE_MAP = {
    "int": {"type": "integer", "format": "int64"},
    "float": {"type": "number", "format": "double"},
    "uuid": {"type": "string", "format": "uuid"},
    "string": {"type": "string"},
    "default": {"type": "string"},
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


def _split_docstring(func: Callable) -> Tuple[str, str]:
    """
    Returns an OpenAPI summary and description from a handler's docstring:
    the summary is its first line, the description the whole text.
    """
    doc = inspect.getdoc(func) or ""
    return doc.partition("\n")[0].strip(), doc


def _unique_operation_id(operation_id: str, used: Set[str]) -> str:
    """Returns operation_id, suffixed with a number if it is already used."""
    candidate = operation_id
    counter = 2
    while candidate in used:
        candidate = f"{operation_id}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def build_openapi(
    controllers: Dict[str, "Controller"],
    *,
    title: str,
    version: str,
    openapi_version: str,
    servers: Optional[list[str]] = None,
    description: str = "",
    middleware_plans: Iterable["HandlerParams"] = (),
) -> Dict[str, Any]:
    """
    Builds the OpenAPI document for the registered controllers.

    ``controllers`` maps controller names to controller instances. Each
    instance's ``endpoints_map`` has this structure: {
        "<base_path>": {
            "<HTTP_METHOD>": {
                "<endpoint_path>": {
                    "method": <callable>,
                    "produces": <MediaType>,
                    "consumes": <MediaType>,
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

    QueryParams, Headers and Cookies parameters of the controller's
    @before_request hooks are added to each of its operations, and those of
    ``middleware_plans`` (one per middleware) to every operation; the
    endpoint's own parameters come first.

    The request body schema comes from the handler's RequestBody[...]
    parameter, and each QueryParams[...] model's fields become ``in: query``
    parameters.
    """
    spec: Dict[str, Any] = {
        "openapi": openapi_version,
        "info": {"title": title, "version": version, "description": description},
        "paths": {},
        "components": {"schemas": {}},
    }
    if servers:
        spec["servers"] = [{"url": url} for url in servers]

    components = spec["components"]
    paths = spec["paths"]

    used_operation_ids: Set[str] = set()
    middleware_list = list(middleware_plans)

    for controller in controllers.values():
        if not controller.open_api_spec:
            continue

        base_path = controller.path

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

                # Summary / description: explicit settings win, otherwise
                # the docstring's first line is the summary and the whole
                # docstring the description.
                handler = cast(Callable, cast(dict, ep_cfg).get("method"))
                doc_summary, doc_description = _split_docstring(handler)
                op_obj["summary"] = cast(dict, ep_cfg).get("summary") or doc_summary
                op_obj["description"] = (
                    cast(dict, ep_cfg).get("description") or doc_description
                )

                # Tags
                tags = cast(dict, ep_cfg).get("tags")
                if tags:
                    op_obj["tags"] = tags

                # operationId: unique across the document. Handler names
                # repeat between controllers (index, get, ...), so the
                # controller's class name is part of the default.
                operation_id = cast(dict, ep_cfg).get("operation_id") or (
                    f"{controller.__class__.__name__}_{handler.__name__}"
                )
                op_obj["operationId"] = _unique_operation_id(
                    operation_id, used_operation_ids
                )

                # Handler parameters: QueryParams[...] and RequestBody[...]
                plan = handler_params(handler)

                # Path, query, header and cookie parameters
                parameters: List[Dict[str, Any]] = [*path_params]
                shared = [
                    *getattr(controller, "_before_request_plans", []),
                    *middleware_list,
                ]
                for sourced in (
                    *plan.query,
                    *plan.headers,
                    *plan.cookies,
                    *(
                        param
                        for shared_plan in shared
                        for param in (
                            *shared_plan.query,
                            *shared_plan.headers,
                            *shared_plan.cookies,
                        )
                    ),
                ):
                    location = sourced.source.location
                    taken = {(p["in"], p["name"]) for p in parameters}
                    parameters.extend(
                        p
                        for p in _query_parameters(
                            components,
                            sourced.model,
                            location,
                            {key: name for key, name, _ in sourced.names},
                        )
                        if (location, p["name"]) not in taken
                    )
                if parameters:
                    op_obj["parameters"] = parameters

                # Request body
                consumes = cast(dict, ep_cfg).get("consumes")
                if consumes:
                    request_model = plan.body.model if plan.body is not None else None
                    schema_ref: Optional[Dict[str, Any]]
                    if plan.reads_files:
                        schema_ref = _multipart_schema(components, plan)
                    else:
                        schema_ref = _ensure_schema(components, request_model)
                    op_obj["requestBody"] = {
                        "required": request_model is not None or plan.reads_files,
                        "content": {
                            _as_media_type(consumes): {
                                "schema": schema_ref or {"type": "object"}
                            }
                        },
                    }

                # Responses
                produces = cast(str, cast(dict, ep_cfg).get("produces"))
                mt_out = _as_media_type(produces) if produces else "application/json"
                default_status = _as_status_code(
                    cast(
                        int,
                        cast(dict, ep_cfg).get("default_status_code", HttpStatus.OK),
                    )
                )
                responses: Dict[int, Any] = {}
                op_obj["responses"] = responses

                response_type = _extract_response_type(
                    cast(str, cast(dict, ep_cfg).get("method"))
                )
                resp_schema_ref = (
                    _ensure_schema(components, response_type, "serialization")
                    if response_type
                    else None
                )

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

                    schema_ref = _ensure_schema(components, body_model, "serialization")

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

    components.pop(_MODES_KEY, None)
    return spec
