"""Application router"""

from typing import (
    TYPE_CHECKING,
    Awaitable,
    Dict,
    List,
    Tuple,
    Any,
    Callable,
    Pattern,
    TypedDict,
    cast,
    Optional,
)
import re
import asyncio
from dataclasses import dataclass
from js import window, document
from pyscript.ffi import create_proxy, is_none  # type: ignore

from .utilities import RouteParams
from .exceptions.exceptions import NoRouteMatch
from .mini_template import MiniTemplate
from .auth import AuthenticationException, AuthorizationException

if TYPE_CHECKING:
    from .app import Application
    from .controller import Controller

Converter = Tuple[Pattern[str], Callable[[str], Any]]

CONVERTERS: Dict[str, Converter] = {
    "int": (re.compile(r"\d+"), int),
    "string": (re.compile(r"[^/]+"), str),
    # "path" can include slashes, so it matches "anything" (non-empty)
    "path": (re.compile(r".+"), str),
}


class Route(TypedDict):
    path: str
    page: Callable


@dataclass(frozen=True)
class RouteEntry:
    raw_rule: str
    page: Callable[[], Awaitable[str]]
    regex: Pattern[str]
    param_casts: Dict[str, Callable[[str], Any]]
    param_converters: Dict[str, str]
    template_parts: Tuple[Tuple[str, str], ...]
    specificity: Tuple[int, int, int]
    transition_effect: Optional[Callable]


class RouteCompileError(ValueError):
    pass


class BuildError(KeyError):
    pass


def transition_effect(
    transition_func: Callable[["Controller"], str | None],
) -> Callable:
    """
    Adds a transition effect to the decorated page. Transition function should return a valid html string or None.
    If the returned value is a html string it is temporarly inserted into the target container of the router. If
    return value is None you can perform any action using the Controller instance.
    """

    def decorator(
        func: Callable[["Controller"], Awaitable[str | None]],
    ) -> Callable[["Controller"], Awaitable[str | None]]:
        setattr(func, "__transition_effect__", transition_func)
        return func

    return decorator


class Router:
    _var_re = re.compile(r"<(?:(?P<conv>[a-zA-Z_]\w*):)?(?P<name>[a-zA-Z_]\w*)>")

    def __init__(
        self,
        strict_slashes: bool = False,
        base_url: str = "",
        default_target: Optional[str] = None,
    ) -> None:
        self._strict_slashes = strict_slashes
        self._base_url = base_url
        self._default_target = default_target
        self._app: "Application" = cast("Application", None)
        self._routes: List[RouteEntry] = []
        self._by_endpoint: Dict[str, RouteEntry] = {}
        self._by_rule: Dict[str, RouteEntry] = {}
        self._current_route_task: asyncio.Task = cast(asyncio.Task, None)

    def initilize(self, app: "Application"):
        self._app = app
        self._set_event_listeners()

    def add_route(self, rule: str, page: Callable[[], Awaitable[str]]) -> None:
        entry = self._compile_rule(rule, page)
        self._routes.append(entry)
        self._routes.sort(key=lambda r: r.specificity, reverse=True)

        self._by_rule[entry.raw_rule] = entry

    def build_map(self) -> Dict[str, Callable[[], Awaitable[str]]]:
        """Simple rule->page mapping (inspection/debug)."""
        return {r.raw_rule: r.page for r in self._routes}

    def match(
        self, path: str
    ) -> Tuple[Callable[[], Awaitable[str]], Dict[str, Any], Optional[Callable]]:
        """Returns: (page, params). Raises NoRouteMatch."""
        norm = self._normalize_path(path)
        for r in self._routes:
            m = r.regex.fullmatch(norm)
            if not m:
                continue

            params: Dict[str, Any] = {}
            for k, v in m.groupdict().items():
                if v is None:
                    continue
                cast = r.param_casts.get(k, str)
                try:
                    params[k] = cast(v)
                except Exception:
                    break
            else:
                return r.page, params, r.transition_effect
        raise NoRouteMatch(f"No route matched path: {path!r}")

    async def route(self, path: str) -> None:
        if self._current_route_task:
            self._current_route_task.cancel()
        try:
            page = None
            ctrl = None
            ctx = {}
            exception = None
            transition_effect: Optional[Callable] = None
            task: Callable[[], Awaitable[str]] = cast(
                Callable[[], Awaitable[str]], None
            )
            try:
                page, params, transition_effect = self.match(path)
                if self.app._authentication is not None:
                    self.app._authentication._check(page)
                route_parameters = RouteParams(params)
                self.app.route_params = route_parameters
                ctrl = page.__self__  # type: ignore
                ctx.update({"ctx": ctrl})
                task = page
            except (
                NoRouteMatch,
                AuthenticationException,
                AuthorizationException,
            ) as exc:
                handler = self.app._exception_mappings.get(exc.__class__.__name__, None)
                if handler is None:
                    raise exc
                exception = exc
                task = handler
                ctrl = handler.__self__
                ctx.update({"ctx": ctrl, "exc": exc})

            target_query = cast(str, self._default_target)
            target = document.querySelector(target_query)
            if is_none(target) or target is None:
                raise BuildError(
                    f"Failed to find container target {self._default_target}"
                )
            window.history.pushState(None, None, f"{self._base_url}{path}")  # type: ignore

            if transition_effect:
                transition_markup = transition_effect(ctrl)
                if transition_markup:
                    target.innerHTML = transition_markup
            if exception:
                self._current_route_task = asyncio.create_task(task(exception))  # type: ignore
            else:
                self._current_route_task = asyncio.create_task(task())  # type: ignore
            markup = await self._current_route_task

            target.setAttribute("jolt-controller", ctrl.__class__.__name__)
            target._controller = ctrl  # type: ignore
            tmpl = MiniTemplate(markup)
            html = tmpl.render(ctx)
            target.innerHTML = html
        except asyncio.CancelledError:
            pass

    def _stringify_param(self, conv_name: str, value: Any) -> str:
        if conv_name == "int":
            if isinstance(value, bool):
                raise BuildError("Boolean is not a valid int parameter")
            if not isinstance(value, int):
                try:
                    value = int(value)
                except Exception as e:
                    raise BuildError(f"Invalid int param value: {value!r}") from e
            return str(value)

        if value is None:
            raise BuildError("None is not a valid parameter value")
        return str(value)

    def _normalize_path(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        if self._strict_slashes:
            return path
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return path

    def _normalize_rule(self, rule: str) -> str:
        if self._strict_slashes:
            return rule
        if rule != "/" and rule.endswith("/"):
            return rule[:-1]
        return rule

    def _compile_rule(
        self, rule: str, page: Callable[[], Awaitable[str]]
    ) -> RouteEntry:
        if not rule.startswith("/"):
            raise RouteCompileError(f"Rule must start with '/': {rule!r}")

        raw_rule = rule
        norm_rule = self._normalize_rule(rule)

        param_casts: Dict[str, Callable[[str], Any]] = {}
        param_converters: Dict[str, str] = {}

        regex_parts: List[str] = ["^"]
        template_parts: List[Tuple[str, str]] = []

        static_segments = 0
        total_vars = 0
        non_path_vars = 0

        lit_buf: List[str] = []

        def flush_lit() -> None:
            if lit_buf:
                lit = "".join(lit_buf)
                template_parts.append(("lit", lit))
                lit_buf.clear()

        i = 0
        while i < len(norm_rule):
            ch = norm_rule[i]
            if ch == "<":
                m = self._var_re.match(norm_rule, i)
                if not m:
                    raise RouteCompileError(
                        f"Invalid variable syntax in rule: {raw_rule!r}"
                    )

                flush_lit()

                conv = m.group("conv") or "string"
                name = m.group("name")

                if conv not in CONVERTERS:
                    raise RouteCompileError(
                        f"Unknown converter {conv!r} in rule {raw_rule!r}. "
                        f"Supported: {', '.join(CONVERTERS)}"
                    )

                if name in param_casts:
                    raise RouteCompileError(
                        f"Duplicate variable name {name!r} in rule: {raw_rule!r}"
                    )

                conv_pat, conv_cast = CONVERTERS[conv]
                param_casts[name] = conv_cast
                param_converters[name] = conv

                regex_parts.append(f"(?P<{name}>{conv_pat.pattern})")
                template_parts.append(("var", name))

                total_vars += 1
                if conv != "path":
                    non_path_vars += 1

                i = m.end()
            else:
                lit_buf.append(ch)
                if ch in r".^$*+?{}[]\|()":
                    regex_parts.append("\\")
                regex_parts.append(ch)
                i += 1

        flush_lit()
        regex_parts.append("$")

        segments = [s for s in norm_rule.split("/") if s != ""]
        for seg in segments:
            if "<" not in seg and ">" not in seg:
                static_segments += 1

        specificity = (static_segments, non_path_vars, -total_vars)

        compiled = re.compile("".join(regex_parts))
        if raw_rule in self._by_endpoint:
            raise RouteCompileError(f"Duplicate endpoint name: {raw_rule!r}")

        transition_effect = getattr(page, "__transition_effect__", None)
        return RouteEntry(
            raw_rule=raw_rule,
            page=page,
            regex=compiled,
            param_casts=param_casts,
            param_converters=param_converters,
            template_parts=tuple(template_parts),
            specificity=specificity,
            transition_effect=transition_effect,
        )

    def _get_clean_link_path(self, path: str) -> str:
        path = path.replace(window.location.host, "")
        path = path.replace(f"{window.location.protocol}//", "")
        path = path.replace(self._base_url, "")
        path = path.split("#", 1)[0]
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _set_event_listeners(self) -> None:
        window.addEventListener("click", create_proxy(self._on_click_event))
        window.addEventListener("popstate", create_proxy(self._on_popstate_event))

    def _on_click_event(self, event) -> None:
        link = event.target.closest("a")
        if link is None or is_none(link):
            return

        target_blank: bool = link.getAttribute("target") == "_blank"
        ignore_router: bool = link.hasAttribute("ignore-router")
        if target_blank or ignore_router:
            return
        event.preventDefault()
        path: str = self._get_clean_link_path(link.href)
        asyncio.create_task(self.route(path))

    def _on_popstate_event(self, event):
        event.preventDefault()

    @property
    def app(self) -> "Application":
        return self._app
