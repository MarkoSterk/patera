from typing import Optional, TypeVar, Generic, cast, Any
from patera import Patera, BaseExtension
from pydantic import BaseModel, Field
import webview
from webview.menu import Menu

from .desktop_cli import DesktopCLI

AppT = TypeVar("AppT", bound="Patera[Any]")


class DesktopConfig(BaseModel):
    """
    Configuration for the Patera desktop extension.

    The WINDOW_* options are passed to pywebview.create_window(...)
    when the main desktop window is created.
    """

    HOME_URL: str = Field(
        ...,
        description="Home screen URL for the desktop app.",
    )

    STARTUP_WAIT_TIME: int = Field(
        default=5,
        description=(
            "Maximum time in seconds to wait for the Patera HTTP server "
            "to become reachable before opening the desktop window."
        ),
    )

    WINDOW_WIDTH: int = Field(
        default=1200,
        description="Initial desktop window width in logical pixels.",
    )

    WINDOW_HEIGHT: int = Field(
        default=800,
        description="Initial desktop window height in logical pixels.",
    )

    WINDOW_X: Optional[int] = Field(
        default=None,
        description="Initial X coordinate of the window. None means centered.",
    )

    WINDOW_Y: Optional[int] = Field(
        default=None,
        description="Initial Y coordinate of the window. None means centered.",
    )

    WINDOW_MIN_WIDTH: int = Field(
        default=800,
        description="Minimum desktop window width in logical pixels.",
    )

    WINDOW_MIN_HEIGHT: int = Field(
        default=600,
        description="Minimum desktop window height in logical pixels.",
    )

    WINDOW_RESIZABLE: bool = Field(
        default=True,
        description="Whether the desktop window can be resized.",
    )

    WINDOW_FULLSCREEN: bool = Field(
        default=False,
        description="Whether the desktop window starts in fullscreen mode.",
    )

    WINDOW_MAXIMIZED: bool = Field(
        default=False,
        description="Whether the desktop window starts maximized.",
    )

    WINDOW_MINIMIZED: bool = Field(
        default=False,
        description="Whether the desktop window starts minimized.",
    )

    WINDOW_HIDDEN: bool = Field(
        default=False,
        description="Whether the desktop window is initially hidden.",
    )

    WINDOW_FRAMELESS: bool = Field(
        default=False,
        description="Whether to create a frameless desktop window.",
    )

    WINDOW_EASY_DRAG: bool = Field(
        default=True,
        description=(
            "Whether a frameless window can be dragged from any point. "
            "Has no effect for normal framed windows."
        ),
    )

    WINDOW_SHADOW: bool = Field(
        default=True,
        description="Whether to add a window shadow where supported.",
    )

    WINDOW_FOCUS: bool = Field(
        default=True,
        description="Whether the desktop window should receive focus.",
    )

    WINDOW_ON_TOP: bool = Field(
        default=False,
        description="Whether the desktop window should stay above other windows.",
    )

    WINDOW_CONFIRM_CLOSE: bool = Field(
        default=False,
        description="Whether pywebview should ask for confirmation before closing.",
    )

    WINDOW_BACKGROUND_COLOR: str = Field(
        default="#FFFFFF",
        description="Background color shown before the webview content is loaded.",
    )

    WINDOW_TRANSPARENT: bool = Field(
        default=False,
        description=(
            "Whether to create a transparent window where supported. "
            "For custom chrome, usually combine with WINDOW_FRAMELESS."
        ),
    )

    WINDOW_TEXT_SELECT: bool = Field(
        default=True,
        description="Whether document text selection is enabled.",
    )

    WINDOW_ZOOMABLE: bool = Field(
        default=False,
        description="Whether document zooming is enabled.",
    )

    WINDOW_DRAGGABLE: bool = Field(
        default=False,
        description="Whether image and link dragging is enabled.",
    )

    WINDOW_TITLE: Optional[str] = Field(
        default=None,
        description=(
            "Optional desktop window title. If not set, APP_NAME from the "
            "Patera application config is used."
        ),
    )

    WINDOW_LOCALIZATION: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional pywebview localization dictionary for this window.",
    )

    def window_kwargs(self) -> dict[str, Any]:
        """
        Return keyword arguments suitable for webview.create_window(...).

        title and url are intentionally excluded because they are passed
        separately by the Desktop extension.
        """
        return {
            "url": self.HOME_URL,
            "width": self.WINDOW_WIDTH,
            "height": self.WINDOW_HEIGHT,
            "x": self.WINDOW_X,
            "y": self.WINDOW_Y,
            "resizable": self.WINDOW_RESIZABLE,
            "fullscreen": self.WINDOW_FULLSCREEN,
            "min_size": (
                self.WINDOW_MIN_WIDTH,
                self.WINDOW_MIN_HEIGHT,
            ),
            "hidden": self.WINDOW_HIDDEN,
            "frameless": self.WINDOW_FRAMELESS,
            "easy_drag": self.WINDOW_EASY_DRAG,
            "shadow": self.WINDOW_SHADOW,
            "focus": self.WINDOW_FOCUS,
            "minimized": self.WINDOW_MINIMIZED,
            "maximized": self.WINDOW_MAXIMIZED,
            "on_top": self.WINDOW_ON_TOP,
            "confirm_close": self.WINDOW_CONFIRM_CLOSE,
            "background_color": self.WINDOW_BACKGROUND_COLOR,
            "transparent": self.WINDOW_TRANSPARENT,
            "text_select": self.WINDOW_TEXT_SELECT,
            "zoomable": self.WINDOW_ZOOMABLE,
            "draggable": self.WINDOW_DRAGGABLE,
            "localization": self.WINDOW_LOCALIZATION,
        }


class Desktop(BaseExtension[AppT, DesktopConfig], Generic[AppT]):
    def __init__(self, app: AppT) -> None:
        self._window: webview.Window = cast(webview.Window, None)
        self._active_windows: list[webview.Window] = []
        super().__init__(app)

    def init(self) -> None:
        self._cli_controller = DesktopCLI(self._app, self)  # type: ignore
        self._app.register_cli_controller(self._cli_controller)

    def create_window(
        self, *, url: str, title: Optional[str] = None, **kwargs
    ) -> webview.Window:
        if title is None:
            title = cast(str, self.app.configs.APP_NAME)
        new_window: webview.Window = cast(
            webview.Window,
            webview.create_window(
                title,  # type: ignore
                url,
                **kwargs,
            ),
        )
        self.add_active_window(new_window)
        return new_window

    def menu(self) -> list[Menu]:
        """Override this method to provide an application menu"""
        return []

    def get_active_window(self) -> Optional[webview.Window]:
        return webview.active_window()

    def add_active_window(self, window: webview.Window) -> None:
        self._active_windows.append(window)

    @property
    def active_windows(self) -> list[webview.Window]:
        return self._active_windows

    @property
    def main_window(self) -> webview.Window:
        return self._window

    @main_window.setter
    def main_window(self, window: webview.Window) -> None:
        self._window = window
