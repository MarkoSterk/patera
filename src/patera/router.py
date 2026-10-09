"""
Router class for application routing. Uses Wrkzeug under the hood.
"""

from typing import Callable, Any, Mapping
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import Map, Rule


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
        try:
            return self._match(path, method)
        except NotFound:
            if self.url_map.strict_slashes or path == "/":
                raise
            # Werkzeug matches "/x" against a "/x/" rule (and vice versa) when
            # strict slashes are off, but only for allowed methods; other
            # methods yield NotFound instead of MethodNotAllowed. Check the
            # alternative form so the correct 405 (and automatic OPTIONS) work.
            alternative = path[:-1] if path.endswith("/") else path + "/"
            try:
                self._match(alternative, method)
            except MethodNotAllowed:
                raise
            except Exception:
                pass
            raise

    def _match(
        self, path: str, method: str
    ) -> tuple[Callable | None, Mapping[str, Any]]:
        adapter = self.url_map.bind("", path_info=path)
        endpoint_name, kwargs = adapter.match(method=method)
        endpoint = self.endpoints.get(endpoint_name)
        return endpoint, kwargs
