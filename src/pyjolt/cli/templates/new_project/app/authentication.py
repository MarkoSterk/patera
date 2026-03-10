"""
Authentication
"""

from typing import Any
from pyjolt.auth import Authentication
from pyjolt import Request


class Auth(Authentication):
    """This class must implement the user_loader and role_check (optional) methods"""

    async def user_loader(self, req: Request) -> Any:
        """
        Implement this method for loading users from the request object.
        Method should return the user object (loaded from db or the jwt).

        return None -> user was not found/loaded. User is not authenticated
        return Any -> user is authenticated
        """
        return None

    async def role_check(self, user: Any, roles: list[Any]) -> bool:
        """
        Implement check if user has required roles.

        True -> user has role
        False -> user doesn't have role
        """
        return False


auth: Auth = Auth()
