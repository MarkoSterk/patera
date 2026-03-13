"""
Test client class
"""

from typing import TYPE_CHECKING, cast
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport

if TYPE_CHECKING:
    from ..patera import Patera


class PyJoltTestClient:
    """
    Test client class for testing of Patera applications
    """

    def __init__(self, app: "Patera", base_url: str = "http://testserver"):
        self.app = app
        self._lifespan: LifespanManager = cast(LifespanManager, None)
        self._transport: ASGITransport = cast(ASGITransport, None)
        self.client: AsyncClient = cast(AsyncClient, None)
        self.base_url: str = base_url

    async def __aenter__(self):
        # Starts up app with lifespan events (triggers startup methods)
        self._lifespan = LifespanManager(self.app)
        await self._lifespan.__aenter__()

        self._transport = ASGITransport(app=self.app)
        self.client = AsyncClient(transport=self._transport, base_url=self.base_url)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Closes the underlying HTTPX client
        if self.client is not None:
            await self.client.aclose()

        # Executes app shutdown with lifespan events (triggers shutdown methods)
        if self._lifespan is not None:
            await self._lifespan.__aexit__(exc_type, exc_val, exc_tb)

        self.client = cast(AsyncClient, None)
        self._transport = cast(ASGITransport, None)
        self._lifespan = cast(LifespanManager, None)

    async def request(self, method: str, path: str, **kwargs):
        if self.client is None:
            raise RuntimeError(
                "PyJoltTestClient must be used as an async context manager."
            )
        return await self.client.request(method, path, **kwargs)

    async def get(self, path: str, **kwargs):
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs):
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs):
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs):
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs):
        return await self.request("DELETE", path, **kwargs)

    async def close(self):
        await self.client.aclose()
