from patera import Request, Response, HttpStatus, MediaType
from patera.controller import Controller, path, get, produces

from app import App


@path("/api/v1/hello", alias="hello_controller")
class HelloWorldApi(Controller[App]):
    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def hello(self, req: Request) -> Response:
        return req.res.json({"message": "Hello, World!"}).status(HttpStatus.OK)
