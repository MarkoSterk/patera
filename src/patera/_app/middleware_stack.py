"""
Registers middleware classes in their order and builds the middleware
chain around the application.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

from typing import (
    Type,
    cast,
)


from ..middleware import AppCallableType, MiddlewareBase
from ..cors.cors_mw import CORSMiddleware

from ._base import AppPart


class MiddlewareStack(AppPart):
    """
    Registers middleware classes in their order and builds the middleware
    chain around the application.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    def enable_cors(self) -> None:
        app = self._app
        cors_enabled: bool = app._configs.CORS_ENABLED

        if not cors_enabled:
            return

        app.register_middleware(CORSMiddleware)

    def register_middleware(
        self,
        middleware_class: Type[MiddlewareBase],
        *,
        order: int | None = None,
    ) -> None:
        """
        Registers a middleware class with the application.

        Middleware instances are not created immediately. They are instantiated
        only when the HTTP application is built.

        This allows extensions to register middleware during app initialization
        without forcing the HTTP app to build in CLI mode.
        """
        app = self._app
        if app._is_built:
            raise RuntimeError(
                f"Cannot register middleware {middleware_class.__name__!r} "
                "after the application has already been built."
            )

        if middleware_class in app._middleware_classes.values():
            return

        if not getattr(middleware_class, "_middleware", False):
            return

        if getattr(middleware_class, "_ignore", False):
            return

        decorator_order = cast(int | None, getattr(middleware_class, "_order", None))
        default_order = cast(int | None, getattr(middleware_class, "_order_", None))
        here_set_order = order

        if default_order is not None and (
            decorator_order is not None or here_set_order is not None
        ):
            app.logger.warning(f"""Middleware {middleware_class.__name__} has default order {default_order}
                            but has set order {decorator_order or here_set_order}. This can lead to unexpected problems.
                            It is suggested that the order on middleware with default order number is not reset.""")

        original_order = next(
            (
                value
                for value in (here_set_order, decorator_order, default_order)
                if value is not None
            ),
            None,
        )
        if original_order is None:
            raise ValueError(
                f"Middleware {middleware_class.__name__} has no set order."
            )

        resolved_order = original_order

        while resolved_order in app._middleware_classes:
            resolved_order += 1

        if resolved_order != original_order:
            app.logger.warning(
                f"For middleware {middleware_class.__name__}: "
                f"Order {original_order} is already taken, "
                f"assigned order {resolved_order} instead."
            )

        app.logger.info(
            f"Registering middleware: {middleware_class.__name__} "
            f"(order={resolved_order})"
        )

        app._middleware_classes[resolved_order] = middleware_class

    def build_chain(self) -> None:
        """
        Wraps the application's base app in all middleware and stores the
        result as the app's request handler.

        Lower middleware order values are processed first and become outer
        middleware.
        """
        app = self._app
        built_app: AppCallableType = app._base_app

        for order_key in sorted(app._middleware_classes.keys(), reverse=True):
            middleware_class = app._middleware_classes[order_key]
            built_app = cast(
                AppCallableType,
                middleware_class(app, built_app),
            )
            if isinstance(built_app, CORSMiddleware):
                app._cors_middleware = built_app

        app._app = built_app
