"""
authentication.py
Authentication module of PyJolt
"""

from abc import ABC, abstractmethod
from typing import (
    Callable,
    Optional,
    Dict,
    Any,
    TYPE_CHECKING,
    Type,
    cast,
    TypedDict,
    NotRequired,
)
import base64
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import binascii
from cryptography.hazmat.primitives.hmac import HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pyjolt import PyJolt, Response, Request

from pyjolt.controller import Controller
from pyjolt.utilities import run_sync_or_async
from pyjolt.middleware import AppCallableType, MiddlewareBase

from .exceptions import AuthenticationException, AuthorizationException

REQUEST_ARGS_ERROR_MSG: str = (
    "Injected argument 'req' of route handler is not an instance "
    "of the Request class. If you used additional decorators "
    "make sure the order of arguments was not changed. "
    "The Request argument must always come first."
)

USER_LOADER_ERROR_MSG: str = (
    "Undefined user loader method. Please define a user loader "
    "method with the @user_loader decorator before using "
    "the login_required decorator"
)


class _AuthenticationConfigs(BaseModel):
    """
    Authentication configuration model
    """

    AUTHENTICATION_ERROR_MSG: Optional[str] = Field(
        default="Login required", description="Default authentication error message"
    )
    AUTHORIZATION_ERROR_MSG: Optional[str] = Field(
        default="Missing user role(s)",
        description="Default authorization error message",
    )


class AuthConfig(TypedDict):
    """Authentication configurations"""

    AUTHENTICATION_ERROR_MSG: NotRequired[str]
    AUTHORIZATION_ERROR_MSG: NotRequired[str]


class AuthUtils:
    """
    Utility class with useful static methods for authentication
    1. create_signed_cookie_value
    2. decode_signed_cookie
    3. create_password_hash
    4. check_password_hash
    5. create_jwt_token
    6. validate_jwt_token
    """

    @staticmethod
    def create_signed_cookie_value(value: str | int, secret_key: str) -> str:
        """
        Creates a signed cookie value using HMAC and a secret key.

        value: The string value to be signed
        secret_key: The application's secret key for signing

        Returns a base64-encoded signed value.
        """
        if isinstance(value, int):
            value = f"{value}"

        hmac_instance = HMAC(secret_key.encode("utf-8"), hashes.SHA256())
        hmac_instance.update(value.encode("utf-8"))
        signature = hmac_instance.finalize()
        signed_value = f"{value}|{base64.urlsafe_b64encode(signature).decode('utf-8')}"
        return signed_value

    @staticmethod
    def decode_signed_cookie(cookie_value: str, secret_key: str) -> str:
        """
        Decodes and verifies a signed cookie value.

        cookie_value: The signed cookie value to be verified and decoded
        secret_key: The application's secret key for verification

        Returns the original string value if the signature is valid.
        Raises a ValueError if the signature is invalid.
        """
        try:
            value, signature = cookie_value.rsplit("|", 1)
            signature_bytes = base64.urlsafe_b64decode(signature)
            hmac_instance = HMAC(secret_key.encode("utf-8"), hashes.SHA256())
            hmac_instance.update(value.encode("utf-8"))
            hmac_instance.verify(signature_bytes)  # Throws an exception if invalid
            return value
        except (ValueError, IndexError, binascii.Error, InvalidSignature):
            # pylint: disable-next=W0707
            raise ValueError("Invalid signed cookie format or signature.")

    @staticmethod
    def create_password_hash(password: str) -> str:
        """
        Creates a secure hash for a given password.

        password: The plain text password to be hashed
        Returns the hashed password as a string.
        """
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return hashed.decode("utf-8")

    @staticmethod
    def check_password_hash(password: str, hashed_password: str) -> bool:
        """
        Verifies a given password against a hashed password.

        password: The plain text password provided by the user
        hashed_password: The stored hashed password
        Returns True if the password matches, False otherwise.
        """
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))

    @staticmethod
    def create_jwt_token(payload: Dict, secret_key: str, expires_in: int = 3600) -> str:
        """
        Creates a JWT token.

        :param payload: A dictionary containing the payload data.
        :param expires_in: Token expiry time in seconds (default: 3600 seconds = 1 hour).
        :return: Encoded JWT token as a string.
        """
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a dictionary.")

        # Add expiry to the payload
        payload = payload.copy()
        payload["exp"] = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Create the token using the app's SECRET_KEY
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        return token

    @staticmethod
    def validate_jwt_token(token: str, secret_key: str) -> Dict | None:
        """
        Validates a JWT token.

        :param token: The JWT token to validate.
        :return: Decoded payload if the token is valid.
        :raises: InvalidJWTError if the token is expired.
                 InvalidJWTError for other validation issues.
        """
        try:
            # Decode the token using the app's SECRET_KEY
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            return payload
        except:
            raise


class Authentication(MiddlewareBase, ABC):
    """
    Authentication middleware for PyJolt application
    User must implement user_loader method and optionally role_check method
    to define how users are loaded and how roles are checked.
    1. user_loader: should return a user object (or None) loaded from the cookie/jwt/header token
    2. role_check: should check if user has required role(s) and return a boolean
    True -> user has role(s)
    False -> user doesn't have role(s)
    3. Decorators:
        - login_required: to mark route handlers/controllers that require authentication
        - role_required: to mark route handlers/controllers that require specific roles
    """

    configs_name: str = cast(str, None)

    def __init__(self, app: "PyJolt", next_app: AppCallableType) -> None:
        """
        Initilizer for authentication module
        """
        super().__init__(app, next_app)  # type: ignore
        self._configs: dict[str, Any] = {}
        self.authentication_error: str
        self.authorization_error: str

        self._configs = app.get_conf(self.configs_name, {})
        self._configs = self.validate_configs(self._configs, _AuthenticationConfigs)

        self.authentication_error = self._configs["AUTHENTICATION_ERROR_MSG"]
        self.authorization_error = self._configs["AUTHORIZATION_ERROR_MSG"]
        # self._app.add_extension(self) #is this neccessary? - Probably not

    async def middleware(self, req: "Request") -> "Response":
        """
        Middleware for authentication
        """
        handler_method: Callable = req.route_handler
        handler_authentication_attributes: Optional[dict[str, Any]] = getattr(
            handler_method, "_authentication", None
        )
        controller_authentication_attributes: Optional[dict[str, Any]] = getattr(
            handler_method.__self__,
            "_authentication",
            None,  # type: ignore
        )  # type: ignore
        if (
            handler_authentication_attributes is None
            and controller_authentication_attributes is None
        ):
            return await self.next(req)
        if (
            controller_authentication_attributes is not None
            or handler_authentication_attributes is not None
        ):  # type: ignore
            user: Optional[Any] = await run_sync_or_async(self.user_loader, req)
            if user is None:
                # not Authenticated
                raise AuthenticationException(self.authentication_error)
            req.set_user(user)
        controller_roles: list[Any] = (
            controller_authentication_attributes.get("roles", [])
            if controller_authentication_attributes
            else []
        )
        handler_roles: list[Any] = (
            handler_authentication_attributes.get("roles", [])
            if handler_authentication_attributes
            else []
        )
        roles: list[Any] = list(set(controller_roles + handler_roles))
        if len(roles) == 0:  # roles not are specified
            # user is authenticated
            return await self.next(req)
        authorized: bool = await run_sync_or_async(
            self.role_check, req.user, list(roles)
        )
        if not authorized:
            # not authorized
            raise AuthorizationException(self.authorization_error, list(roles))
        # user is authenticated and authorized - calls next middleware in chain
        return await self.next(req)

    @abstractmethod
    async def user_loader(self, req: "Request") -> Any:
        """
        Should return a user object (or None) loaded from the cookie
        or some other way provided by the request object
        """

    @abstractmethod
    async def role_check(self, user: Any, roles: list[Any]) -> bool:
        """
        Should check if user has required role(s) and return a boolean
        True -> user has role(s)
        False -> user doesn't have role(s)
        """


def login_required(handler: "Callable|Type[Controller]") -> "Callable|Type[Controller]":
    """
    Decorator for login required
    """
    setattr(handler, "_authentication", {"required": True})
    return handler


def role_required(
    *roles,
) -> Callable[[Callable | Type[Controller]], Callable | Type[Controller]]:
    """
    Decorator for role required
    """

    def decorator(handler: "Callable|Type[Controller]") -> "Callable|Type[Controller]":
        attributes: dict[str, Any] = getattr(handler, "_authentication", {})
        attributes["roles"] = list(roles)
        attributes["required"] = True
        setattr(handler, "_authentication", attributes)
        return handler

    return decorator
