"""
Default static endpoint that serves all static files for the application
In production, static files should be served directly by a reverse proxy server such
as Nginx. This reverse proxy server approach is more efficient.
"""

from __future__ import annotations
import os
from typing import Callable, Type

from werkzeug.security import safe_join

from .controller import Controller, get
from .exceptions.http_exceptions import StaticAssetNotFound
from .utilities import file_response

from .request import Request
from .response import Response


def static_resource(
    func_or_cls: "Callable|Type[Controller]",
) -> "Callable|Type[Controller]":
    """
    Mark a controller or handler as a static resource endpoint. Bypasses middleware and calls
    the endpoint handler directly.

    Useful for serving static assets that don't need any middleware. Used by the built-in
    Static controller
    """
    setattr(func_or_cls, "_static_resource", True)
    return func_or_cls


@static_resource
class Static(Controller):
    @get("/<path:filename>")
    async def get(self, req: Request, filename: str) -> Response:
        """
        Serves a file from the static folder, streamed from disk, with
        conditional requests (ETag, Last-Modified) and HTTP Range support.
        A missing file is answered with the standard JSON 404.
        """
        candidate = safe_join(req.app.static_files_path, filename)
        if not candidate or not os.path.isfile(candidate):
            raise StaticAssetNotFound()
        return file_response(req.res, candidate, req.headers)
