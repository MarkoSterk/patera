"""
CORS middleware for Patera.
Handles Cross-Origin Resource Sharing (CORS) by adding appropriate headers to HTTP responses.
"""

from typing import Any, Callable, Optional, TYPE_CHECKING, cast
from ..middleware import MiddlewareBase

if TYPE_CHECKING:
    from ..request import Request
    from ..response import Response


class CORSMiddleware(MiddlewareBase):
    """
    Middleware to handle CORS by adding necessary headers to HTTP responses.
    """

    async def middleware(self, req: "Request") -> "Response":
        scope = req.scope
        cors_opts = self._resolve_cors_options(cast(Callable, req.route_handler))
        origin = self._get_header(scope, "origin")
        is_preflight = (req.method == "OPTIONS") and bool(
            self._get_header(scope, "access-control-request-method")
        )

        if cors_opts["enabled"] and origin:
            if not self._origin_allowed(origin, cors_opts["allow_origins"]):
                return req.res.json(
                    {"status": "error", "message": "CORS origin not allowed"}
                ).status(403)

            if is_preflight:
                return self._handle_preflight(scope, req, origin, cors_opts)

            # Wrap send to inject CORS headers on normal responses
            # pylint: disable-next=W0212
            req._send = self._wrap_cors_send(req._send, origin, cors_opts)

        return await self.next(req)

    def _get_header(self, scope, name: str) -> Optional[str]:
        target = name.lower().encode("latin1")
        for k, v in scope.get("headers", []):
            if k.lower() == target:
                try:
                    return v.decode("latin1")
                # pylint: disable-next=W0718
                except Exception:
                    return None
        return None

    def _normalize_list(self, v, *, upper: bool = False) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        out = [s.strip() for s in v if s and s.strip()]
        if upper:
            out = [s.upper() for s in out]
        return out

    def _global_cors_options(self) -> dict[str, Any]:
        return {
            "enabled": self.app.get_conf("CORS_ENABLED"),
            "allow_origins": self.app.get_conf("CORS_ALLOW_ORIGINS"),
            "allow_methods": self.app.get_conf("CORS_ALLOW_METHODS"),
            "allow_headers": self.app.get_conf("CORS_ALLOW_HEADERS"),
            "expose_headers": self.app.get_conf("CORS_EXPOSE_HEADERS"),
            "allow_credentials": self.app.get_conf("CORS_ALLOW_CREDENTIALS"),
            "max_age": self.app.get_conf("CORS_MAX_AGE"),
        }

    def _resolve_cors_options(self, handler: Optional[Callable]) -> dict[str, Any]:
        """
        Merge global and endpoint-level CORS options.
        If handler has @no_cors, CORS is completely disabled.
        """
        opts = self._global_cors_options()

        if handler is None:
            return opts

        # Check if handler explicitly disables CORS
        if getattr(handler, "_disable_cors", False):
            opts["enabled"] = False
            return opts

        # Merge @cors decorator overrides
        overrides = getattr(handler, "_cors_options", None) or {}
        for k, v in overrides.items():
            if v is not None:
                opts[k] = v

        opts["allow_origins"] = self._normalize_list(opts["allow_origins"])
        opts["allow_methods"] = self._normalize_list(opts["allow_methods"], upper=True)
        opts["allow_headers"] = self._normalize_list(opts["allow_headers"])
        opts["expose_headers"] = self._normalize_list(opts["expose_headers"])
        return opts

    def _origin_allowed(self, origin: Optional[str], allow_origins: list[str]) -> bool:
        if not origin:
            return True
        if "*" in allow_origins:
            return True
        return origin in allow_origins

    def _build_cors_headers_for_preflight(
        self,
        *,
        origin: str,
        request_method: Optional[str],
        request_headers: Optional[str],
        opts: dict[str, Any],
    ) -> dict[str, str]:
        allow_methods = opts["allow_methods"]
        allow_headers = opts["allow_headers"]

        # Echo requested headers if none configured
        if not allow_headers and request_headers:
            allow_headers = [h.strip() for h in request_headers.split(",") if h.strip()]

        # If "*" configured but credentials allowed: echo back the Origin
        allow_origin_value = "*"
        if opts["allow_credentials"] or ("*" not in opts["allow_origins"]):
            allow_origin_value = origin

        headers: dict[str, str] = {
            "access-control-allow-origin": allow_origin_value,
            "vary": "Origin",
            "access-control-allow-methods": ", ".join(allow_methods),
            "access-control-allow-headers": ", ".join(allow_headers),
        }

        if opts["allow_credentials"]:
            headers["access-control-allow-credentials"] = "true"

        if opts.get("max_age") is not None:
            headers["access-control-max-age"] = str(int(opts["max_age"]))

        return headers

    def _build_cors_headers_for_response(
        self, *, origin: Optional[str], opts: dict[str, Any]
    ) -> list[tuple[bytes, bytes]]:
        if not origin:
            return []

        # If "*" configured but credentials allowed: echo Origin instead.
        allow_origin_value = "*"
        if opts["allow_credentials"] or ("*" not in opts["allow_origins"]):
            allow_origin_value = origin

        headers: list[tuple[bytes, bytes]] = [
            (b"access-control-allow-origin", allow_origin_value.encode("latin1")),
            (b"vary", b"Origin"),
        ]
        if opts["allow_credentials"]:
            headers.append((b"access-control-allow-credentials", b"true"))
        expose = opts.get("expose_headers") or []
        if expose:
            headers.append(
                (b"access-control-expose-headers", ", ".join(expose).encode("latin1"))
            )
        return headers

    def _handle_preflight(
        self, scope, req: "Request", origin: str, cors_opts: dict
    ) -> "Response":
        acr_method = self._get_header(scope, "access-control-request-method")
        acr_headers = self._get_header(scope, "access-control-request-headers")

        if (
            acr_method
            and cors_opts["allow_methods"]
            and acr_method.upper() not in cors_opts["allow_methods"]
        ):
            return req.res.text("Preflight method not allowed").status(405)

        headers = self._build_cors_headers_for_preflight(
            origin=origin,
            request_method=acr_method,
            request_headers=acr_headers,
            opts=cors_opts,
        )
        return req.res.set_headers(headers)

    def _wrap_cors_send(self, send, origin: str, cors_opts: dict):
        cors_headers = self._build_cors_headers_for_response(
            origin=origin, opts=cors_opts
        )

        async def cors_send(event):
            if event.get("type") == "http.response.start":
                headers = event.get("headers", [])
                event = {**event, "headers": headers + cors_headers}
            await send(event)

        return cors_send
