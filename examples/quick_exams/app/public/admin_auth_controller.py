from patera import Request, Response
from patera.controller import Controller, get, post, path
from app import App, store
from app.session import COOKIE, clear_session_cookie, same_origin, set_session_cookie


@path("/admin")
class AdminAuth(Controller[App]):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.redirect("/admin/en/dashboard")

    @post("/login")
    async def login(self, req: Request) -> Response:
        req.res.set_header("Cache-Control", "no-store")
        if not same_origin(req):
            return req.res.json({"message": "Cross-origin request denied"}).status(403)
        if req.headers.get("content-type", "").split(";")[0] != "application/json":
            return req.res.json({"message": "JSON required"}).status(415)
        try:
            data = await req.json()
            store.require(isinstance(data, dict), "Expected a JSON object")
            with store.database() as db:
                token = store.login(db, data)
                from app.session import session_user

                user = session_user(db, token)
                store.require("ADMIN" in user["roles"], "ADMIN role required")
            set_session_cookie(req.res, token)
            return req.res.json({"ok": True})
        except (ValueError, TypeError):
            return req.res.json(
                {"message": "Invalid credentials or missing ADMIN role"}
            ).status(401)

    @get("/logout")
    async def logout(self, req: Request) -> Response:
        if not same_origin(req):
            return req.res.json({"error": "Cross-origin request denied"}).status(403)
        with store.database() as db:
            store.remove(db, "session", req.cookies.get(COOKIE, ""))
        clear_session_cookie(req.res)
        return req.res.redirect("/")
