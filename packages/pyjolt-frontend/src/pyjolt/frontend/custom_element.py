"""Custom element"""

from typing import TYPE_CHECKING, Callable, Dict, Any, Optional

if TYPE_CHECKING:
    from .style_element import Style


def define_value(value: Any, reactive: bool = True):
    return (value, reactive)


class CustomElement:
    def __init__(
        self,
        *,
        tag_name: str,
        markup: Optional[Callable] = None,
        before_init: Optional[Dict[str, Callable]] = None,
        after_init: Optional[Dict[str, Callable]] = None,
        on_disconnect: Optional[Dict[str, Callable]] = None,
        methods: Optional[Dict[str, Callable]] = None,
        values: Optional[Dict[str, tuple[Any, bool]]] = None,
        style: Optional["Style"] = None,
    ):
        self._tag_name = tag_name
        self._markup = markup
        self._before_init = before_init
        self._after_init = after_init
        self._on_disconnect = on_disconnect
        self._methods = methods
        self._values = values
        self._style = style

    @property
    def tag_name(self) -> str:
        return self._tag_name

    @property
    def markup(self) -> Callable | None:
        return self._markup

    @property
    def before_init(self) -> Dict[str, Callable]:
        return self._before_init if self._before_init is not None else {}

    @property
    def after_init(self) -> Dict[str, Callable]:
        return self._after_init if self._after_init is not None else {}

    @property
    def on_disconnect(self) -> Dict[str, Callable]:
        return self._on_disconnect if self._on_disconnect is not None else {}

    @property
    def methods(self) -> Dict[str, Callable]:
        return self._methods if self._methods is not None else {}

    @property
    def values(self) -> Dict[str, tuple[Any, bool]]:
        return self._values if self._values is not None else {}

    @property
    def style(self) -> "Style|None":
        return self._style
