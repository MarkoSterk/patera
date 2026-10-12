import os
from typing import TYPE_CHECKING, Any, Optional, cast
from patera import Request, Response, MediaType, HttpStatus
from werkzeug.security import safe_join

from patera.utilities import file_response
from patera.utilities import run_sync_or_async
from patera.controller import Controller, post, consumes, produces, get
from patera.static import static_resource
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .frontend import Frontend


class UnknownFrontendMethod(Exception):
    def __init__(self, method: str):
        super().__init__(
            f"Unknown frontend method call. Method '{method}' does not exist or is not exposed."
        )
        self.method: str = method


class InterfaceResponse(BaseModel):
    data: Optional[Any] = Field(
        default=None, description="The return data of the interface method"
    )


class InterfaceRequest(BaseModel):
    method: str = Field(description="The method to be executed")
    args: list[Any] = Field(
        default=[], description="Incomming data as a list of arguments"
    )
    kwargs: dict[str, Any] = Field(
        default={}, description="Incomming data as key-value pairs"
    )


class _FrontendInterfaceController(Controller):
    def __init__(self, *args, **kwargs):
        self._frontend: "Frontend" = cast("Frontend", None)
        super().__init__(*args, **kwargs)

    @post("/interface")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def interface(
        self, req: Request, data: InterfaceRequest
    ) -> Response[InterfaceResponse]:
        method = self.frontend.exposed_tools_map.get(data.method, None)
        if method is None:
            raise UnknownFrontendMethod(data.method)

        result = await run_sync_or_async(method, *data.args, **data.kwargs)

        return req.res.json({"data": result}).status(HttpStatus.OK)

    @get("/_static/<path:filename>")
    @static_resource
    async def static(self, req: Request, filename: str) -> Response:
        """
        Endpoint for static files with HTTP Range and conditional request
        support.
        """
        # Checks if file exists
        file_path = None
        candidate = safe_join(self.frontend.root_path, "static", filename)
        if candidate and os.path.exists(candidate):
            file_path = candidate
        if not file_path:
            return req.res.no_content().status(HttpStatus.NOT_FOUND)

        # Full files, ranges and conditional requests (ETag, If-Modified-Since)
        return file_response(req.res, file_path, req.headers)

    @property
    def frontend(self) -> "Frontend":
        return self._frontend

    @frontend.setter
    def frontend(self, interface: "Frontend") -> None:
        self._frontend = interface
