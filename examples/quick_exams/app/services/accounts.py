from __future__ import annotations

import asyncio
from typing import Any, Optional

import jwt
from patera import Service
from patera.admin import Permissions
from patera.auth import AuthUtils
from patera.injectable import Inject
from werkzeug.security import check_password_hash as check_legacy_hash

from ..errors import (
    Conflict,
    ExamError,
    Forbidden,
    InvalidCredentials,
    NotFound,
    require,
)
from ..models import ADMIN, User
from ..repository import Users
from ..schemas import Role, UserIn


class AccountService(Service):
    users: Inject[Users]

    def init(self) -> None:
        self._dummy_hash: Optional[str] = None

    async def hash_password(self, password: str) -> str:
        return await asyncio.to_thread(AuthUtils.create_password_hash, password)

    async def _password_matches(self, password: str, hashed: str) -> bool:
        if hashed.startswith((AuthUtils.PASSWORD_HASH_PREFIX, "$2")):
            return await asyncio.to_thread(
                AuthUtils.check_password_hash, password, hashed
            )
        return await asyncio.to_thread(check_legacy_hash, hashed, password)

    async def _absent_user_hash(self) -> str:
        # Unknown emails are checked against a real hash so timing reveals nothing.
        if self._dummy_hash is None:
            self._dummy_hash = await self.hash_password("not-a-real-password")
        return self._dummy_hash

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_one_by(email=email)
        hashed = user.password_hash if user else await self._absent_user_hash()
        valid = await self._password_matches(password, hashed)
        if user is None or not valid:
            raise InvalidCredentials("Invalid email or password")
        require(user.roles, "This account has no staff access", Forbidden)
        if AuthUtils.password_hash_needs_update(user.password_hash):
            user.password_hash = await self.hash_password(password)
        return user

    def issue_token(self, user: User) -> str:
        return AuthUtils.create_jwt_token(
            {"sub": user.id, "ver": user.token_version},
            self.app.configs.SECRET_KEY,
            expires_in=self.app.configs.JWT_LIFETIME_SECONDS,
        )

    async def user_from_token(self, token: str) -> Optional[User]:
        """
        The staff user a valid token belongs to. The user's current database
        row decides: a deleted user, a changed token version (new password)
        or removed roles all end the token's validity immediately.
        """
        if not token:
            return None
        try:
            claims = AuthUtils.validate_jwt_token(token, self.app.configs.SECRET_KEY)
        except jwt.InvalidTokenError:
            return None
        user = await self.users.get(claims.get("sub", ""))
        if user is None or claims.get("ver") != user.token_version or not user.roles:
            return None
        return user

    @staticmethod
    def roles_of(user: User) -> list[str]:
        roles: list[str] = list(user.roles)
        if user.is_admin:
            roles.extend(permission.value for permission in Permissions)
        return roles

    async def list_users(self) -> list[User]:
        return await self.users.query.order_by(User.email).all()

    async def create_user(self, data: UserIn) -> User:
        if not data.password:
            raise ExamError("Use a password of at least 12 characters")
        await self._ensure_unique_email(data.email)
        return await self.users.create_and_flush(
            email=data.email,
            password_hash=await self.hash_password(data.password),
            is_instructor="INSTRUCTOR" in data.roles,
            is_admin="ADMIN" in data.roles,
        )

    async def update_user(self, user_id: str, data: UserIn) -> User:
        user = await self.users.get(user_id)
        require(user, "User not found", NotFound)
        await self._ensure_unique_email(data.email, user.id)
        if ADMIN not in data.roles:
            await self.ensure_admin_remains(user)
        user.email = data.email
        user.is_instructor = "INSTRUCTOR" in data.roles
        user.is_admin = ADMIN in data.roles
        if data.password:
            user.password_hash = await self.hash_password(data.password)
            user.token_version += 1
        await self.users.flush()
        return user

    async def ensure_admin_remains(self, user: User) -> None:
        if user.is_admin:
            require(
                await self.users.count_admins() > 1, "Keep at least one admin", Conflict
            )

    async def _ensure_unique_email(
        self, email: str, user_id: Optional[str] = None
    ) -> None:
        existing = await self.users.first_by(email=email)
        require(
            existing is None or existing.id == user_id, "Email already exists", Conflict
        )

    async def admin_clean_user(
        self, record: User, values: dict[str, Any], creating: bool
    ) -> dict[str, Any]:
        roles: list[Role] = []
        if values.get("is_instructor"):
            roles.append("INSTRUCTOR")
        if values.get("is_admin"):
            roles.append("ADMIN")
        data = UserIn(
            email=values.get("email") or "",
            password=values.pop("password", None),
            roles=roles,
        )
        if creating and not data.password:
            raise ExamError("Use a password of at least 12 characters")
        await self._ensure_unique_email(data.email, None if creating else record.id)
        if not creating and ADMIN not in data.roles:
            await self.ensure_admin_remains(record)
        values.update(
            email=data.email,
            is_instructor="INSTRUCTOR" in data.roles,
            is_admin=ADMIN in data.roles,
        )
        if data.password:
            values["password_hash"] = await self.hash_password(data.password)
            if not creating:
                values["token_version"] = (record.token_version or 0) + 1
        return values
