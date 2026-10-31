# WebSockets

WebSocket endpoints are controller methods decorated with `@socket`:

```python
from typing import TYPE_CHECKING

from patera import Request
from patera.controller import Controller, path, socket

if TYPE_CHECKING:
    from app import App


@path("/ws")
class ChatSocket(Controller["App"]):
    @socket("/chat/<room>")
    async def chat(self, req: Request, room: str) -> None:
        if (await req.receive())["type"] != "websocket.connect":
            return
        await req.accept()
        while True:
            message = await req.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive" and "text" in message:
                await req.send({"type": "websocket.send", "text": f"[{room}] {message['text']}"})
```

Socket handlers receive and send the raw ASGI messages through `req.receive()` / `req.send()`
and accept the connection with `req.accept()`. Their routes include `URL_PREFIX`. The development
server needs the `websockets` package, included in the `dev` extra.

## Differences from HTTP endpoints

- Sockets send ASGI messages directly, not rendered `Response` objects.
- HTTP middleware and controller `@before_request` / `@after_request` hooks do not run.
- A socket handler (or its controller, including inherited metadata) marked with
  `@login_required`, `@role_required` or `@transactional` is **refused at startup**. Check the
  user inside the handler and keep sockets in a controller of their own.
- Unexpected exceptions close the connection with code `1011`.

## Security and resources

- Validate credentials and the allowed origin explicitly before accepting a private socket.
- Use short-lived sessions for database operations, never a transaction for the whole connection.
  Database sessions a socket handler opens through `Model.query()` or a repository are closed
  when it returns, and uncommitted work rolls back.
- Release resources in `finally`, handle disconnects and bound your queues.

## Testing

`PateraTestClient` sends HTTP requests only. Test sockets through an ASGI WebSocket harness or a
real socket client.
