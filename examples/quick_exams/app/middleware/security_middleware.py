from urllib.parse import urlsplit

from patera import HttpStatus, Request, Response
from patera.exceptions import abort
from patera.middleware import MiddlewareBase, middleware

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PRIVATE_PREFIXES = ("/api/", "/admin")


def is_cross_site(req: Request) -> bool:
    if req.headers.get("sec-fetch-site") == "cross-site":
        return True
    origin = req.headers.get("origin")
    return bool(origin) and urlsplit(origin).netloc != req.headers.get("host")


@middleware(order=1)
class BrowserSecurity(MiddlewareBase):
    """
    Defense in depth for the cookie-authenticated browser UI: state-changing
    requests must come from this site (the auth cookie is SameSite=Strict as
    well), and API and Admin responses are never cached.
    """

    async def middleware(self, req: Request) -> Response:
        if req.method in UNSAFE_METHODS and is_cross_site(req):
            abort("Cross-origin request denied", HttpStatus.FORBIDDEN)
        res = await self.next(req)
        if req.path.startswith(PRIVATE_PREFIXES) and "/_static/" not in req.path:
            res.set_header("Cache-Control", "no-store")
        return res
