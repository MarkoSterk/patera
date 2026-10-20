from datetime import datetime, timezone
import os
from urllib.parse import urlsplit

from app import store

COOKIE = "quick_exams_session"


def session_user(db, token):
    session = store.get(db, "session", token)
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(session["created"])
    ).total_seconds()
    store.require(0 <= age < 28800, "Session expired")
    return store.get(db, "user", session["user"])


def token_for(req):
    return req.headers.get("authorization", "").removeprefix(
        "Bearer "
    ) or req.cookies.get(COOKIE, "")


def same_origin(req):
    origin = req.headers.get("origin")
    return req.headers.get("sec-fetch-site") != "cross-site" and (
        not origin or urlsplit(origin).netloc == req.headers.get("host")
    )


def set_session_cookie(res, token):
    res.set_cookie(
        COOKIE,
        token,
        max_age=28800,
        http_only=True,
        same_site="Strict",
        secure=os.environ.get("QUICK_EXAMS_PUBLIC_URL", "").startswith("https://"),
    )


def clear_session_cookie(res):
    res.delete_cookie(
        COOKIE,
        same_site="Strict",
        secure=os.environ.get("QUICK_EXAMS_PUBLIC_URL", "").startswith("https://"),
    )
