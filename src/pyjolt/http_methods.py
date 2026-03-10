"""HTTP methods enum"""

from enum import StrEnum


class HttpMethod(StrEnum):
    """All allowed http methods"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    SOCKET = "SOCKET"
