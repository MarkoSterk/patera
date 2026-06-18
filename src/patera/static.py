"""
Default static endpoint that serves all static files for the application
In production, static files should be served directly by a reverse proxy server such
as Nginx. This reverse proxy server approach is more efficient.
"""

from __future__ import annotations
import os
import mimetypes
from typing import Callable, Type

from werkzeug.security import safe_join

from .controller import Controller, get
from .utilities import get_file, get_range_file
from .http_statuses import HttpStatus

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
        Endpoint for static files with HTTP Range support,
        falling back to get_file for full-content requests.
        """
        # Checks if file exists
        file_path = None
        candidate = safe_join(req.app.static_files_path, filename)
        if candidate and os.path.exists(candidate):
            file_path = candidate
        if not file_path:
            return req.res.no_content().status(HttpStatus.NOT_FOUND)

        # checks/guesses mimetype
        guessed, _ = mimetypes.guess_type(file_path)
        content_type = guessed or "application/octet-stream"

        # Checks range header and returns range if header is present
        range_header = req.headers.get("range")
        if not range_header:
            status, headers, body = await get_file(file_path, content_type=content_type)
            headers["Accept-Ranges"] = "bytes"
            return req.res.send_file(body, headers).status(status)

        return await get_range_file(req.res, file_path, range_header, content_type)
