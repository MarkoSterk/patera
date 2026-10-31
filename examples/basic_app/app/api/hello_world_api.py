from typing import TYPE_CHECKING

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import Controller, get, path, produces

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/v1/hello", alias="hello_controller")
class HelloWorldApi(Controller["App"]):
    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def hello(self, req: Request) -> Response:
        return req.res.json({"message": "Hello, World!"}).status(HttpStatus.OK)
