from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, StringConstraints, field_validator

from .common import Email, Input, Password, Role


class LoginIn(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True)]
    password: str


class UserIn(Input):
    email: Email
    password: Optional[Password] = None
    roles: list[Role] = []

    @field_validator("password", mode="before")
    @classmethod
    def _blank_password(cls, value):
        return value or None

    @field_validator("roles", mode="after")
    @classmethod
    def _unique_roles(cls, value: list[str]) -> list[str]:
        return sorted(set(value), key=["INSTRUCTOR", "ADMIN"].index)


class UserOut(BaseModel):
    id: str
    email: str
    roles: list[str]


class TokenOut(BaseModel):
    token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    user: UserOut
