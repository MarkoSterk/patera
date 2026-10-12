from __future__ import annotations

import time

import jwt
import pytest

from patera import Request, Response
from patera.auth import (
    AuthConfig,
    Authentication,
    AuthenticationException,
    AuthorizationException,
    AuthUtils,
    login_required,
    role_required,
)
from patera.controller import Controller, get, path
from patera.middleware import middleware

pytestmark = pytest.mark.integration

SECRET = "test-secret-that-is-long-enough-for-hs256-signatures"
USERS = {"ana": ["admin"], "bo": ["editor"], "cy": []}


@middleware
class TokenAuth(Authentication):
    async def user_loader(self, req: Request):
        token = req.headers.get("authorization", "").removeprefix("Bearer ")
        try:
            payload = AuthUtils.validate_jwt_token(token, SECRET)
        except jwt.InvalidTokenError:
            return None
        return payload["sub"] if payload["sub"] in USERS else None

    async def roles_loader(self, user):
        return USERS[user]


@path("/public")
class PublicController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.json({"user": req.user})


@path("/account")
@login_required()
class AccountController(Controller):
    @get("/")
    async def me(self, req: Request) -> Response:
        return req.res.json({"user": req.user, "roles": req.roles})

    @get("/admin")
    @role_required("admin")
    async def admin(self, req: Request) -> Response:
        return req.res.json({"ok": True})


@path("/editor")
@role_required("editor", "admin")
class EditorController(AccountController):
    """Inherits the parent's decorators; must not modify the parent."""


def token(user: str, expires_in: int = 60) -> dict[str, str]:
    return {
        "authorization": "Bearer "
        + AuthUtils.create_jwt_token({"sub": user}, SECRET, expires_in)
    }


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[PublicController, AccountController, EditorController],
        middleware=[TokenAuth],
    )


async def test_public_routes_skip_authentication(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/public/")
        assert res.status_code == 200
        assert res.json() == {"user": None}


async def test_login_required(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/account/")
        assert res.status_code == 401
        assert res.json()["message"] == "Login required"

        res = await client.get("/account/", headers=token("cy"))
        assert res.status_code == 200
        assert res.json() == {"user": "cy", "roles": None}


async def test_expired_token_is_rejected(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/account/", headers=token("ana", expires_in=-10))
        assert res.status_code == 401


async def test_role_required(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/account/admin", headers=token("bo"))
        assert res.status_code == 403
        assert res.json()["data"] == ["admin"]

        res = await client.get("/account/admin", headers=token("ana"))
        assert res.status_code == 200


async def test_controller_level_roles_and_isolation(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/editor/", headers=token("bo"))).status_code == 200
        assert (await client.get("/editor/", headers=token("cy"))).status_code == 403
        # The parent controller did not inherit the subclass' role requirement
        assert (await client.get("/account/", headers=token("cy"))).status_code == 200
    assert "roles" not in AccountController._authentication


async def test_custom_messages_and_always_load_roles(make_app, client_for):
    app = make_app(
        controllers=[AccountController],
        middleware=[TokenAuth],
        TOKEN_AUTH=AuthConfig(
            AUTHENTICATION_ERROR_MSG="Please log in", ALWAYS_LOAD_ROLES=True
        ),
    )
    async with client_for(app) as client:
        assert (await client.get("/account/")).json()["message"] == "Please log in"
        res = await client.get("/account/", headers=token("ana"))
        assert res.json() == {"user": "ana", "roles": ["admin"]}


def test_exception_status_codes():
    assert AuthenticationException("x").status_code == 401
    assert AuthorizationException("x", []).status_code == 403


def test_password_hashing():
    hashed = AuthUtils.create_password_hash("s3cret")
    assert hashed != "s3cret"
    assert AuthUtils.check_password_hash("s3cret", hashed)
    assert not AuthUtils.check_password_hash("wrong", hashed)


def test_long_passwords_are_hashed_in_full():
    long_password = "correct horse battery staple " * 5  # 145 bytes
    hashed = AuthUtils.create_password_hash(long_password)
    assert AuthUtils.check_password_hash(long_password, hashed)
    # A password differing only after byte 72 must not match
    assert not AuthUtils.check_password_hash(long_password[:-1] + "!", hashed)
    assert AuthUtils.check_password_hash(
        "čšž-ünïcode", AuthUtils.create_password_hash("čšž-ünïcode")
    )


def test_password_hashes_from_earlier_versions_still_verify():
    import bcrypt

    legacy = bcrypt.hashpw(b"old-secret", bcrypt.gensalt(4)).decode()
    assert AuthUtils.check_password_hash("old-secret", legacy)
    assert not AuthUtils.check_password_hash("wrong", legacy)
    assert not AuthUtils.check_password_hash("x" * 100, legacy)  # > 72 bytes
    assert AuthUtils.password_hash_needs_update(legacy)

    current = AuthUtils.create_password_hash("old-secret")
    assert current.startswith("bcrypt-sha256$$2b$")
    assert not AuthUtils.password_hash_needs_update(current)


@pytest.mark.parametrize(
    "stored", ["", "plain-text", "$2b$12$tooshort", "bcrypt-sha256$garbage", "ž"]
)
def test_malformed_password_hashes_do_not_match(stored):
    assert AuthUtils.check_password_hash("s3cret", stored) is False


def test_signed_cookies():
    signed = AuthUtils.create_signed_cookie_value(42, SECRET)
    assert AuthUtils.decode_signed_cookie(signed, SECRET) == "42"
    with pytest.raises(ValueError):
        AuthUtils.decode_signed_cookie(signed, "other-secret")
    with pytest.raises(ValueError):
        AuthUtils.decode_signed_cookie("garbage", SECRET)


def test_jwt_tokens():
    tok = AuthUtils.create_jwt_token({"sub": "ana"}, SECRET, expires_in=60)
    payload = AuthUtils.validate_jwt_token(tok, SECRET)
    assert payload["sub"] == "ana"
    assert payload["exp"] > time.time()
    with pytest.raises(jwt.InvalidTokenError):
        AuthUtils.validate_jwt_token(
            tok, "another-secret-that-is-long-enough-for-hs256"
        )
    with pytest.raises(ValueError):
        AuthUtils.create_jwt_token("not a dict", SECRET)  # type: ignore[arg-type]


def test_signed_cookie_values_carry_a_timestamp():
    signed = AuthUtils.create_signed_cookie_value("user|7", SECRET)
    value, timestamp, _ = signed.rsplit("|", 2)
    assert value == "user|7"  # a "|" in the value survives
    assert abs(int(timestamp) - time.time()) < 5
    assert AuthUtils.decode_signed_cookie(signed, SECRET, max_age=60) == "user|7"


def test_signed_cookie_max_age(monkeypatch):
    signed = AuthUtils.create_signed_cookie_value("42", SECRET)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 120)
    with pytest.raises(ValueError, match="expired"):
        AuthUtils.decode_signed_cookie(signed, SECRET, max_age=60)
    assert AuthUtils.decode_signed_cookie(signed, SECRET, max_age=600) == "42"
    assert AuthUtils.decode_signed_cookie(signed, SECRET) == "42"

    # Signed far in the future (beyond clock skew) is rejected too
    monkeypatch.setattr(time, "time", lambda: now - 3600)
    with pytest.raises(ValueError):
        AuthUtils.decode_signed_cookie(signed, SECRET, max_age=60)


def test_signed_cookie_tampering_is_rejected():
    signed = AuthUtils.create_signed_cookie_value("42", SECRET)
    value, timestamp, signature = signed.rsplit("|", 2)
    for forged in (
        f"43|{timestamp}|{signature}",
        f"42|{int(timestamp) + 1000}|{signature}",
        f"42|{timestamp}|{signature[:-4]}AAAA",
        "42",
        "",
    ):
        with pytest.raises(ValueError):
            AuthUtils.decode_signed_cookie(forged, SECRET)


def test_signed_cookies_without_a_timestamp_are_rejected():
    import base64

    signature = base64.urlsafe_b64encode(AuthUtils._sign("42", SECRET)).decode()
    with pytest.raises(ValueError):
        AuthUtils.decode_signed_cookie(f"42|{signature}", SECRET)
