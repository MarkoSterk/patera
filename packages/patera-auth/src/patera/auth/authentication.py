"""
authentication.py
Authentication module of Patera
"""

from abc import ABC, abstractmethod
from typing import (
    ClassVar,
    Callable,
    Generic,
    Optional,
    Dict,
    Any,
    TYPE_CHECKING,
    Type,
    TypeVar,
)
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import binascii
import time
from cryptography.hazmat.primitives.hmac import HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from patera import Patera, Response, Request

from patera.controller import Controller
from patera.middleware import AppCallableType, MiddlewareBase

from .exceptions import AuthenticationException, AuthorizationException


class AuthenticationConfig(BaseModel):
    """
    Authentication configuration model
    """

    AUTHENTICATION_ERROR_MSG: str = Field(
        default="Login required", description="Default authentication error message"
    )
    AUTHORIZATION_ERROR_MSG: str = Field(
        default="Missing user role(s)",
        description="Default authorization error message",
    )
    ALWAYS_LOAD_ROLES: bool = Field(
        default=False,
        description=(
            "Load user roles for every authenticated request, even when "
            "the matched controller or endpoint does not require roles."
        ),
    )


class AuthUtils:
    """
    Utility class with useful static methods for authentication
    1. create_signed_cookie_value
    2. decode_signed_cookie
    3. create_password_hash
    4. check_password_hash / password_hash_needs_update
    5. create_jwt_token
    6. validate_jwt_token
    """

    @staticmethod
    def _sign(message: str, secret_key: str) -> bytes:
        hmac_instance = HMAC(secret_key.encode("utf-8"), hashes.SHA256())
        hmac_instance.update(message.encode("utf-8"))
        return hmac_instance.finalize()

    @staticmethod
    def _verify(message: str, signature: str, secret_key: str) -> bool:
        try:
            signature_bytes = base64.urlsafe_b64decode(signature)
            hmac_instance = HMAC(secret_key.encode("utf-8"), hashes.SHA256())
            hmac_instance.update(message.encode("utf-8"))
            hmac_instance.verify(signature_bytes)
            return True
        except (ValueError, binascii.Error, InvalidSignature):
            return False

    @staticmethod
    def create_signed_cookie_value(value: str | int, secret_key: str) -> str:
        """
        Creates a signed cookie value using HMAC and a secret key.

        value: The string value to be signed
        secret_key: The application's secret key for signing

        Returns ``value|timestamp|signature``. The signature covers the value
        and the time of signing, so decode_signed_cookie() can reject values
        older than a maximum age.
        """
        value = f"{value}"
        timestamp = str(int(time.time()))
        signature = AuthUtils._sign(f"{value}|{timestamp}", secret_key)
        encoded = base64.urlsafe_b64encode(signature).decode("utf-8")
        return f"{value}|{timestamp}|{encoded}"

    @staticmethod
    def decode_signed_cookie(
        cookie_value: str, secret_key: str, max_age: Optional[int] = None
    ) -> str:
        """
        Decodes and verifies a signed cookie value.

        cookie_value: The signed cookie value to be verified and decoded
        secret_key: The application's secret key for verification
        max_age: Maximum age in seconds. Older values are rejected; values
            signed in the future (beyond 60 seconds of clock skew) too.
            None accepts any age.

        Returns the original string value if the signature is valid.
        Raises a ValueError if the format, the signature or the age is
        invalid.
        """
        parts = cookie_value.rsplit("|", 2)
        if len(parts) == 3 and parts[1].isdigit():
            value, timestamp, signature = parts
            if AuthUtils._verify(f"{value}|{timestamp}", signature, secret_key):
                if max_age is not None:
                    age = time.time() - int(timestamp)
                    if age > max_age or age < -60:
                        raise ValueError("Signed cookie has expired.")
                return value

        raise ValueError("Invalid signed cookie format or signature.")

    # Hashes from create_password_hash() start with this marker; plain bcrypt
    # hashes ("$2b$...") are from versions before 0.11 and still verify.
    PASSWORD_HASH_PREFIX: ClassVar[str] = "bcrypt-sha256$"

    @staticmethod
    def _password_digest(password: str) -> bytes:
        """
        SHA-256 of the password, base64-encoded (44 bytes). bcrypt reads at
        most 72 bytes and rejects longer input, so passwords of any length are
        reduced to this digest first; every character still counts.
        """
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        return base64.b64encode(digest)

    @staticmethod
    def create_password_hash(password: str) -> str:
        """
        Creates a hash for a password of any length:
        "bcrypt-sha256$" followed by a bcrypt hash of the password's SHA-256
        digest.

        password: The plain text password to be hashed
        Returns the hashed password as a string.
        """
        hashed = bcrypt.hashpw(AuthUtils._password_digest(password), bcrypt.gensalt())
        return AuthUtils.PASSWORD_HASH_PREFIX + hashed.decode("utf-8")

    @staticmethod
    def check_password_hash(password: str, hashed_password: str) -> bool:
        """
        Verifies a password against a stored hash.

        Accepts hashes made by create_password_hash() and plain bcrypt hashes
        made by earlier versions (use password_hash_needs_update() to replace
        those after a successful login).

        password: The plain text password provided by the user
        hashed_password: The stored hashed password
        Returns True if the password matches, False otherwise, including
        for a stored value that is not a valid hash.
        """
        try:
            if hashed_password.startswith(AuthUtils.PASSWORD_HASH_PREFIX):
                stored = hashed_password[len(AuthUtils.PASSWORD_HASH_PREFIX) :]
                return bcrypt.checkpw(
                    AuthUtils._password_digest(password), stored.encode("utf-8")
                )
            if hashed_password.startswith("$2"):
                # Plain bcrypt (earlier versions). bcrypt never accepted more
                # than 72 bytes, so a longer password cannot match such a hash.
                raw = password.encode("utf-8")
                if len(raw) > 72:
                    return False
                return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
        except (ValueError, UnicodeEncodeError):
            return False
        return False

    @staticmethod
    def password_hash_needs_update(hashed_password: str) -> bool:
        """
        True for a hash in an older format. After check_password_hash()
        succeeds, store create_password_hash(password) in its place:

            if AuthUtils.check_password_hash(password, user.password_hash):
                if AuthUtils.password_hash_needs_update(user.password_hash):
                    user.password_hash = AuthUtils.create_password_hash(password)
        """
        return not hashed_password.startswith(AuthUtils.PASSWORD_HASH_PREFIX)

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
    def validate_jwt_token(token: str, secret_key: str) -> Dict:
        """
        Validates a JWT token.

        :param token: The JWT token to validate.
        :return: Decoded payload if the token is valid.
        :raises: jwt.ExpiredSignatureError if the token is expired.
                 jwt.InvalidTokenError (base class) for any other validation issue.
        """
        return jwt.decode(token, secret_key, algorithms=["HS256"])


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class Authentication(MiddlewareBase[AppT, AuthenticationConfig], ABC, Generic[AppT]):
    """
    Authentication middleware for Patera application
    User must implement user_loader method and optionally role_check method
    to define how users are loaded and how roles are checked.
    1. user_loader: should return a user object (or None) loaded from the cookie/jwt/header token
    2. roles_loader: should return a list of user roles or an empty list
                    Returned list is compared to required roles on controller and endpoint handler.
    3. Decorators:
        - login_required: to mark route handlers/controllers that require authentication
        - role_required: to mark route handlers/controllers that require specific roles

    OPTIONAL:
    Implement an async def refresh_credentials(self, res: "Response") -> None: method to refresh credentials
    if near expiration date.

    Default middleware order for Authentication is -99 and should idealy not be changed.
    """

    _order_: int = -99

    def __init__(self, app: AppT, next_app: AppCallableType) -> None:
        """
        Initilizer for authentication module
        """
        super().__init__(app, next_app)  # type: ignore
        # Uses the AuthenticationConfig defaults if the app has no configuration
        # for this middleware (see MiddlewareBase.configs).
        self.authentication_error = self.configs.AUTHENTICATION_ERROR_MSG
        self.authorization_error = self.configs.AUTHORIZATION_ERROR_MSG

    async def middleware(self, req: "Request") -> "Response":
        """
        Middleware for authentication
        """
        handler_method: Callable = req.route_handler
        handler_authentication_attributes: Optional[dict[str, Any]] = getattr(
            handler_method, "_authentication", None
        )
        controller_authentication_attributes: Optional[dict[str, Any]] = getattr(
            handler_method.__self__,  # type: ignore
            "_authentication",
            None,  # type: ignore
        )  # type: ignore
        if (
            handler_authentication_attributes is None
            and controller_authentication_attributes is None
        ):
            return await self.next(req)

        combined_attr = {}
        if controller_authentication_attributes is not None:
            combined_attr.update(controller_authentication_attributes)
        if handler_authentication_attributes is not None:
            combined_attr.update(handler_authentication_attributes)

        authentication_exc = combined_attr.get(
            "authentication_exception", AuthenticationException
        )
        authorization_exc = combined_attr.get(
            "authorization_exception", AuthorizationException
        )

        user: Optional[Any] = await self.user_loader(req)

        if user is None:
            req.remove_user()
            raise authentication_exc(self.authentication_error)

        req.set_user(user)

        controller_roles: set[Any] = set(
            controller_authentication_attributes.get("roles", [])
            if controller_authentication_attributes
            else []
        )

        handler_roles: set[Any] = set(
            handler_authentication_attributes.get("roles", [])
            if handler_authentication_attributes
            else []
        )

        required_roles: set[Any] = controller_roles | handler_roles

        if required_roles or self.configs.ALWAYS_LOAD_ROLES:
            user_roles: list[Any] = await self.roles_loader(req.user)
            req.set_roles(user_roles)
            if required_roles:
                user_role_set: set[Any] = set(user_roles)

                controller_authorized = _has_roles(
                    user_role_set,
                    controller_roles,
                    bool(
                        controller_authentication_attributes
                        and controller_authentication_attributes.get("require_all")
                    ),
                )
                handler_authorized = _has_roles(
                    user_role_set,
                    handler_roles,
                    bool(
                        handler_authentication_attributes
                        and handler_authentication_attributes.get("require_all")
                    ),
                )

                if not controller_authorized or not handler_authorized:
                    raise authorization_exc(
                        self.authorization_error,
                        list(required_roles),
                    )

        res: "Response" = await self.next(req)
        await self.refresh_credentials(res)
        return res

    @abstractmethod
    async def user_loader(self, req: "Request") -> Any:
        """
        Should return a user object (or None) loaded from the cookie
        or some other way provided by the request object
        """

    @abstractmethod
    async def roles_loader(self, user: Any) -> list[Any]:
        """
        Should load and return a list of current users roles. If user has no assigned roles
        return an empty list.
        """

    async def refresh_credentials(self, res: "Response") -> None:
        """
        Refresh credentials (cookies/jwt etc) if near expiration.
        Should modify the response object in-place and return None
        """
        pass


def _has_roles(user_roles: set[Any], required: set[Any], require_all: bool) -> bool:
    """
    True if nothing is required, or the user has every required role
    (``require_all``) or at least one of them.
    """
    if not required:
        return True
    if require_all:
        return required <= user_roles
    return bool(user_roles & required)


def _set_exception(
    attributes: dict[str, Any],
    key: str,
    given: Optional[Type[Exception]],
    default: Type[Exception],
) -> None:
    """
    An exception class passed to a decorator wins. Otherwise one that another
    decorator on the same handler already chose is kept, so the order in
    which @login_required and @role_required are stacked does not matter.
    """
    if given is not None:
        attributes[key] = given
    else:
        attributes.setdefault(key, default)


def login_required(
    *,
    raise_authentication_exception: Optional[Type[Exception]] = None,
) -> Callable[[Callable | Type[Controller]], Callable | Type[Controller]]:
    """
    Requires a signed-in user. ``raise_authentication_exception`` replaces
    AuthenticationException (401) when nobody is signed in.
    """

    def decorator(handler: "Callable|Type[Controller]") -> "Callable|Type[Controller]":
        # Copy: the dict may be inherited from a parent controller class.
        attributes: dict[str, Any] = dict(getattr(handler, "_authentication", {}))
        attributes["required"] = True
        _set_exception(
            attributes,
            "authentication_exception",
            raise_authentication_exception,
            AuthenticationException,
        )
        setattr(handler, "_authentication", attributes)
        return handler

    return decorator


def role_required(
    *roles,
    require_all: bool = False,
    raise_authentication_exception: Optional[Type[Exception]] = None,
    raise_authorization_exception: Optional[Type[Exception]] = None,
) -> Callable[[Callable | Type[Controller]], Callable | Type[Controller]]:
    """
    Requires a signed-in user with at least one of ``roles``, or with all of
    them when ``require_all`` is True. The exception classes replace
    AuthenticationException (401) and AuthorizationException (403).

    A controller's and an endpoint's requirements are checked separately and
    must both be met.
    """

    def decorator(handler: "Callable|Type[Controller]") -> "Callable|Type[Controller]":
        # Copy: the dict may be inherited from a parent controller class.
        attributes: dict[str, Any] = dict(getattr(handler, "_authentication", {}))
        attributes["roles"] = list(roles)
        attributes["require_all"] = require_all
        attributes["required"] = True
        _set_exception(
            attributes,
            "authentication_exception",
            raise_authentication_exception,
            AuthenticationException,
        )
        _set_exception(
            attributes,
            "authorization_exception",
            raise_authorization_exception,
            AuthorizationException,
        )
        setattr(handler, "_authentication", attributes)
        return handler

    return decorator
