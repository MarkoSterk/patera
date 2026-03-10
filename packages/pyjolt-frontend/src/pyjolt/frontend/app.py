"""Frontend application"""

from typing import (
    TYPE_CHECKING,
    TypedDict,
    NotRequired,
    List,
    Callable,
    Optional,
    cast,
    Any,
    Dict,
    Type,
)
from urllib.parse import parse_qs
from js import window, Location
from pyscript import document
from pyscript.ffi import create_proxy
from .utilities import RouteParams, AppData, run_sync_or_async
from .mini_template import extract_data_bind_templates
from .mini_template import MiniTemplate

if TYPE_CHECKING:
    from .custom_element import CustomElement
    from .router import Router
    from dom_stubs import Element
    from .auth import Authentication
    from .controller import Controller
    from .exceptions import ExceptionController


class AppConfigs(TypedDict):
    ROUTER_STRICT_SLASHES: NotRequired[bool]
    ROUTER_BASE_URL: NotRequired[str]
    ROUTER_DEFAULT_TARGET: NotRequired[str]


async def register_component(component: "CustomElement", app: "Application"):
    from js import __pyjolt__registerComponent

    tag_name: str = component.tag_name
    markup_method = cast(Callable, component.markup)
    methods = create_proxy(
        {
            key: create_proxy(app.catch_exception(method))
            for key, method in component.methods.items()
        }
    )
    before_init = create_proxy(
        {
            key: create_proxy(app.catch_exception(method))
            for key, method in component.before_init.items()
        }
    )
    after_init = create_proxy(
        {
            key: create_proxy(app.catch_exception(method))
            for key, method in component.after_init.items()
        }
    )
    on_disconnect = create_proxy(
        {
            key: create_proxy(app.catch_exception(method))
            for key, method in component.on_disconnect.items()
        }
    )
    style = create_proxy(component.style)
    markup = None
    snippets = None
    if markup_method is not None:
        full_html = markup_method()
        markup = create_proxy(MiniTemplate(full_html))
        snippets = extract_data_bind_templates(full_html)
        snippets = create_proxy(
            {key: create_proxy(MiniTemplate(html)) for key, html in snippets.items()}
        )
    values_getters_setters = ""
    init_values = ""
    for key, _value in component.values.items():
        reactive = False
        if isinstance(_value, tuple):
            value, reactive = _value
        else:
            value = _value
        values_getters_setters += f"""
        get {key}() {{
            return this._values._{key};
        }}
        """
        if reactive:
            values_getters_setters += f"""
        set {key}(value){{
            this._values._{key} = value;
            this._rerenderPart('{key}');
        }}
            """
        else:
            values_getters_setters += f"""
        set {key}(value){{
            this._values._{key} = value;
        }}
        """
        init_values += f"""
            this._values._{key} = __pyjolt__convertValue('{value}')
        """
    methods_getters = ""
    for key in component.methods.keys():
        methods_getters += f"""
        get {key}(){{
            return __customElements['{tag_name}']['methods']['{key}']
        }}
        """

    __pyjolt__registerComponent(
        tag_name,
        f"""
    customElements.define('{tag_name}', class extends CustomElement {{

        tagName = '{tag_name}'

        constructor(){{
            super();
            this.resolveInitialization = null;
            this.initComplete = new Promise((resolve) => {{
                this.resolveInitialization = resolve;
            }});
        }}
        async connectedCallback() {{
            this._values = {{}}
            {init_values}
            await this._runLifeCycleMethods('beforeInit');
            this._installStyle();
            this._render();
            this._wire(this);
            await this._waitForSubelements()
            this.resolveInitialization();
            await this._runLifeCycleMethods('afterInit');
        }}

        _waitForSubelements = async () => {{
            const subelementPromises = [];
            const allCustomElements = Array.from(this.querySelectorAll('*')).filter(
                (el) => {{
                    return el instanceof CustomElement
                }}
            );
            allCustomElements.forEach(elem => {{
                subelementPromises.push(elem.initComplete);
            }})
            return await Promise.all(subelementPromises);
        }}

        _installStyle(){{
            if(!__customElements['{tag_name}']['style']){{
                return;
            }}
            const style = document.head.querySelector(`style[jolt-element='{tag_name}']`);
            if(style){{
                return;
            }}
            const str_style = __customElements['{tag_name}']['style'](this)
            const style_el = document.createElement('style')
            style_el.setAttribute('jolt-element', this.tagName)
            style_el.textContent = str_style.trim();
            document.head.appendChild(style_el);
        }}

        async disconnectedCallback(){{
            await this._runLifeCycleMethods('onDisconnect')
        }}

        _rerenderPart(field){{
            const selector = '[data-bind="' + field + '"]'
            const elem = this.querySelector(selector);
            if(!elem){{
                return;
            }}
            elem.innerHTML = __customElements['{tag_name}']['template_snippets'][field]?.render(this);
            this._rewirePart(elem);
        }}

        _rewirePart(elem){{
            this._wire(elem);
        }}

        _render(){{
            if(__customElements['{tag_name}']?.['markup']){{
                this.innerHTML = this._markup();
            }}
        }}

        _markup(){{
            return __customElements['{tag_name}']['markup'].render(this)
        }}

        _wire(elem){{
            elem.querySelectorAll('*').forEach(el => {{
                for(const attr of el.attributes){{
                    if(attr.name.startsWith('jolt-')){{
                        const method = el.getAttribute(attr.name)
                        el.addEventListener('click', async (e) => {{
                            await __customElements['{tag_name}']['methods'][method](this, e, el.dataset);
                        }})
                    }}
                }}
            }});
        }}

        async _runLifeCycleMethods(cycle){{
            for(const [name, method] of Object.entries(__customElements['{tag_name}'][cycle])){{
                await method(this);
            }}
        }}

        get app(){{
            return this.closest('[jolt-app]')?._app;
        }}

        get controller(){{
            return this.closest('[jolt-controller]')?._controller
        }}
        {values_getters_setters}
        {methods_getters}
    }});
    """,
        markup,
        methods,
        before_init,
        after_init,
        on_disconnect,
        style,
        snippets,
    )


class App(TypedDict):
    target: str
    components: NotRequired[List["CustomElement"]]
    before_init: NotRequired[Dict[str, Callable]]
    after_init: NotRequired[Dict[str, Callable]]
    markup: NotRequired[Callable]
    data: NotRequired[Dict[str, Any]]
    configurations: NotRequired[AppConfigs]
    controllers: List["Type[Controller]"]
    exception_controllers: NotRequired[List["Type[ExceptionController]"]]
    authentication: NotRequired["Type[Authentication]"]


class Application:
    """
    Main application controller.
    Responsible for bootstrapping UI and wiring events.
    """

    def __init__(
        self,
        target: str,
        components: Optional[List["CustomElement"]] = None,
        before_init: Optional[Dict[str, Callable]] = None,
        after_init: Optional[Dict[str, Callable]] = None,
        markup: Optional[Callable] = None,
        data: Optional[Dict[str, Any]] = None,
        configurations: Optional[AppConfigs] = None,
        controllers: Optional[List["Type[Controller]"]] = None,
        authentication: Optional["Type[Authentication]"] = None,
        exception_controllers: Optional[List["Type[ExceptionController]"]] = None,
    ) -> None:

        self._configurations = configurations if configurations is not None else {}
        if controllers is None:
            raise ValueError("Please provide a valid list of controllers")
        self._authentication = (
            authentication(self) if authentication is not None else None
        )
        self._controllers: "Dict[str, Controller]" = {
            ctrl.__name__: ctrl(self) for ctrl in controllers
        }

        self._exception_controllers = []
        if exception_controllers is not None:
            self._exception_controllers = [ctrl(self) for ctrl in exception_controllers]
        self._exception_mappings: Dict[str, Any] = {}
        for ctrl in self._exception_controllers:
            self._exception_mappings = {
                **self._exception_mappings,
                **ctrl.get_exception_mapping(),
            }
        self._container: str = target
        self._components = components
        self._before_init = before_init
        self._after_init = after_init
        self._markup = markup
        self._data = AppData(data)
        self.root: "Element" = cast("Element", None)
        self._router: "Router" = cast("Router", None)
        self._init_router()

    def _init_router(self) -> None:
        from .router import Router

        strict_slashes = self.get_conf("ROUTER_STRICT_SLASHES", False)
        base_url = self.get_conf("ROUTER_BASE_URL", "")
        default_target = self.get_conf("ROUTER_DEFAULT_TARGET", None)
        self._router = Router(strict_slashes, base_url, default_target)
        for ctrl in self._controllers.values():
            pages = ctrl.get_pages()
            for route in pages:
                self._router.add_route(
                    cast(str, route.get("path")), cast(Callable, route.get("page"))
                )
        self._router.build_map()

    async def initialize(self):
        """
        Perform async initialization logic.
        """
        await self._run_lifecycle_methods(self._before_init)
        self._router.initilize(self)
        self.root = cast("Element", document.querySelector(cast(str, self._container)))  # type: ignore
        if not self.root:
            raise RuntimeError("Missing root element for app in HTML template.")
        await self._register_components()
        self.root.setAttribute("jolt-app", "")
        self.root._app = create_proxy(self)  # type: ignore
        self.render()
        if self._router:
            await self._router.route(self._router._get_clean_link_path(self.pathname))
        await self._run_lifecycle_methods(self._after_init)

    async def _run_lifecycle_methods(self, methods: Dict[str, Callable] | None) -> None:
        if methods is None:
            return
        for method in methods.values():
            try:
                await run_sync_or_async(method, self)
            except Exception as exc:
                await self.handle_exception(exc)

    async def handle_exception(self, exc: Exception):
        handler = self._exception_mappings.get(exc.__class__.__name__, None)
        if handler is None:
            raise exc
        return await run_sync_or_async(handler, exc)

    def catch_exception(self, func: Callable):
        async def _wrapper(*args, **kwargs):
            try:
                await run_sync_or_async(func, *args, **kwargs)
            except Exception as exc:
                await self.handle_exception(exc)

        return _wrapper

    def render(self) -> None:
        """
        Render initial UI.
        """
        if self._markup is None:
            return
        full_html = self._markup()
        self.root.innerHTML = MiniTemplate(full_html).render({"ctx": self})

    async def _register_components(self):
        if self._components is None:
            return
        for comp in self._components:
            await register_component(comp, self)

    def get_conf(self, key: str, default: Any = None) -> Any:
        return self._configurations.get(key, default)

    @property
    def data(self) -> AppData:
        if self._data is None:
            self._data = AppData({})
        return self._data

    def getData(self, key: str) -> Optional[Any]:
        return getattr(self._data, key, None)

    def setData(self, key: str, value: Any) -> None:
        if self._data is None:
            self._data = AppData({})
        setattr(self._data, key, value)

    @property
    def route_params(self) -> RouteParams:
        if self._route_params is None:
            return RouteParams({})
        return self._route_params

    @route_params.setter
    def route_params(self, params: Optional[RouteParams]) -> None:
        self._route_params = params

    @property
    def location(self) -> "Location":
        return window.location

    @property
    def pathname(self) -> str:
        return self.location.pathname

    @property
    def host(self) -> str:
        return self.location.host

    @property
    def hostname(self) -> str:
        return self.location.hostname

    @property
    def hash(self) -> str:
        return self.location.hash

    @property
    def href(self) -> str:
        return self.location.href

    @property
    def query_string(self) -> str:
        return self.location.search or ""

    @property
    def query_params(self) -> Dict:
        return parse_qs(self.query_string)

    @property
    def port(self) -> str:
        return self.location.port

    @property
    def protocol(self) -> str:
        return self.location.protocol


def create_app(configs: App) -> Application:
    return Application(**configs)
