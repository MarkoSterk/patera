from io import BytesIO

from patera import Request, Response
from patera.controller import Controller, get, path, post
from app import App
from app import store as s
from app.session import (
    session_user,
    token_for,
    same_origin,
    set_session_cookie,
    clear_session_cookie,
)


@path("/api")
class ExamsApi(Controller[App]):
    @post("/<action>")
    async def action(self, req: Request, action: str) -> Response:
        req.res.set_header("Cache-Control", "no-store")
        if not same_origin(req):
            return req.res.json({"error": "Cross-origin request denied"}).status(403)
        if req.headers.get("content-type", "").split(";")[0] != "application/json":
            return req.res.json({"error": "JSON required"}).status(415)
        try:
            data = await req.json()
            s.require(isinstance(data, dict), "Expected a JSON object")
            with s.database() as db:
                if action == "login":
                    result = {"token": s.login(db, data)}
                    set_session_cookie(req.res, result["token"])
                elif action == "start":
                    result = s.public_attempt(
                        s.start_attempt(db, data.get("exam", ""), data.get("email", ""))
                    )
                elif action == "submit":
                    result = s.submit(db, data.get("attempt", ""), data.get("answers"))
                else:
                    token = token_for(req)
                    try:
                        user = session_user(db, token)
                    except ValueError:
                        return req.res.json({"error": "Please sign in"}).status(401)
                    result = self.staff(db, action, data, user, token)
                    if action == "logout":
                        clear_session_cookie(req.res)
            return req.res.json(result)
        except PermissionError as exc:
            return req.res.json({"error": str(exc)}).status(403)
        except (ValueError, TypeError, KeyError) as exc:
            return req.res.json({"error": str(exc) or "Invalid input"}).status(400)

    def staff(self, db, action, data, user, token):
        owner = user["id"]
        if action == "logout":
            s.remove(db, "session", token)
            return {}
        if action == "state":
            if not set(user["roles"]) & {"ADMIN", "INSTRUCTOR"}:
                raise PermissionError("No staff roles assigned")
            return {
                "user": {k: user[k] for k in ("id", "email", "roles")},
                **{
                    kind + "s": [
                        r for r in s.all_records(db, kind) if r["owner"] == owner
                    ]
                    for kind in ("category", "question", "exam")
                },
                "reports": s.reports(db, owner),
            }
        if action.startswith("admin"):
            if "ADMIN" not in user["roles"]:
                raise PermissionError("ADMIN role required")
            if action == "admin-user":
                s.user_save(db, data)
            elif action != "admin":
                raise ValueError("Unknown action")
            return {
                "users": [
                    {k: u[k] for k in ("id", "email", "roles")}
                    for u in s.all_records(db, "user")
                ],
                "reports": s.reports(db),
                "counts": {
                    kind: len(s.all_records(db, kind))
                    for kind in ("question", "exam", "attempt")
                },
            }
        if "INSTRUCTOR" not in user["roles"]:
            raise PermissionError("INSTRUCTOR role required")
        kind = data.get("kind")
        if action in ("save", "delete"):
            s.require(kind in ("category", "question", "exam"), "Invalid record type")
            if data.get("id"):
                if s.get(db, kind, data["id"])["owner"] != owner:
                    raise PermissionError("This record belongs to another instructor")
            if action == "delete":
                if kind == "category":
                    s.require(
                        not any(
                            q["category"] == data["id"]
                            for q in s.all_records(db, "question")
                        ),
                        "Move or delete the category's questions first",
                    )
                if kind == "question":
                    s.require(
                        not any(
                            data["id"] in e["questions"]
                            for e in s.all_records(db, "exam")
                        ),
                        "Remove this question from live exams first",
                    )
                s.remove(db, kind, data["id"])
                return {}
            if kind == "category":
                name = str(data.get("name", "")).strip()
                s.require(
                    name and len(name) <= 100,
                    "Category name is required (maximum 100 characters)",
                )
                return s.save(
                    db,
                    kind,
                    {
                        **({"id": data["id"]} if data.get("id") else {}),
                        "name": name,
                        "owner": owner,
                    },
                )
            if kind == "question":
                return s.question_save(db, data, owner)
            return s.exam_save(db, data, owner)
        raise ValueError("Unknown action")

    @get("/qr/<exam_id>")
    async def qr(self, req: Request, exam_id: str) -> Response:
        import os
        import qrcode
        import qrcode.image.svg

        with s.database() as db:
            try:
                s.get(db, "exam", exam_id)
            except ValueError:
                return req.res.json({"error": "Exam not found"}).status(404)
        base = os.environ.get("QUICK_EXAMS_PUBLIC_URL", "http://localhost:3000").rstrip(
            "/"
        )
        stream = BytesIO()
        qrcode.make(
            f"{base}/exam/{exam_id}", image_factory=qrcode.image.svg.SvgPathImage
        ).save(stream)
        return req.res.bytes(stream.getvalue(), "image/svg+xml")
