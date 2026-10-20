from patera.auth import Authentication
from patera.admin import Permissions
from patera.middleware import middleware
from app import store
from app.session import same_origin, session_user, token_for


@middleware
class SessionAuthentication(Authentication):
    async def middleware(self, req):
        if req.path.startswith("/admin"):
            if req.method not in ("GET", "HEAD", "OPTIONS") and not same_origin(req):
                return req.res.json({"error": "Cross-origin request denied"}).status(
                    403
                )
            response = await super().middleware(req)
            response.set_header("Cache-Control", "no-store")
            return response
        return await super().middleware(req)

    async def user_loader(self, req):
        try:
            with store.database() as db:
                return session_user(db, token_for(req))
        except ValueError:
            return None

    async def roles_loader(self, user):
        return user["roles"] + (list(Permissions) if "ADMIN" in user["roles"] else [])
