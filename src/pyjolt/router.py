"""
Router class for application routing. Uses Wrkzeug under the hood.
"""

from typing import Callable, Any, Mapping
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import NotFound, MethodNotAllowed


class Router:
    """
    A Router class that leverages Werkzeug’s Map/Rule system.
    """

    def __init__(self, strict_slashes: bool = False):
        self.url_map = Map(strict_slashes=strict_slashes)
        # endpoint_name -> function
        self.endpoints: dict[str, Callable] = {}

    def add_route(
        self, path: str, endpoint: Callable, methods: list[str], endpoint_name: str
    ):
        """
        Registers a route by creating a Rule in the internal Map.
        """
        if endpoint_name in self.endpoints:
            raise ValueError(f"Duplicate endpoint name registered: {endpoint_name}")
        # Store the endpoint function:
        self.endpoints[endpoint_name] = endpoint
        # Add a single Rule that handles the specified methods
        self.url_map.add(Rule(path, endpoint=endpoint_name, methods=methods))

    def match(
        self, path: str, method: str
    ) -> tuple[Callable | None, Mapping[str, Any]]:
        """
        Matches the path and method against the routing map.
        Returns (endpoint_function, path_variables_dict) if found, otherwise (None, {}).
        """
        adapter = self.url_map.bind("", path_info=path)
        try:
            endpoint_name, kwargs = adapter.match(method=method)
            endpoint = self.endpoints.get(endpoint_name)
            return endpoint, kwargs
        except (NotFound, MethodNotAllowed) as exc:
            return None, {"method": method, "path": path, "exc": exc}
