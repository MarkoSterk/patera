# WebSockets

```python
from patera import Request
from patera.controller import Controller, path, socket

@path("/live")
class LiveController(Controller):
    @socket("/echo")
    async def echo(self, req: Request):
        if (await req.receive())["type"] != "websocket.connect":
            return
        await req.accept()
        while True:
            message = await req.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive" and "text" in message:
                await req.send({"type": "websocket.send", "text": message["text"]})
```

Sockets send ASGI messages directly, not rendered HTTP Responses. Their routes
include `URL_PREFIX`. HTTP middleware and controller before/after request hooks
do not run. Keep socket controllers separate from HTTP controllers with auth or
transaction metadata: `login_required`, `role_required`, and `transactional` on
sockets (including inherited controller metadata) are rejected.

Validate credentials and allowed origin explicitly before accepting a private
socket. Use short-lived sessions for database operations, never a transaction for
the entire connection. Context-opened sessions close when the handler returns and
uncommitted work rolls back. Release resources in `finally`; handle disconnects
and bound queues. Unexpected exceptions close with 1011. Test through an ASGI
WebSocket harness or real socket client, not the HTTP-only test client's requests.

Sources: tutorial chapter 6; architecture chapter 9.
