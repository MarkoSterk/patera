from patera.desktop.ui import ExceptionHandler, PageContext, handles
from ..components.error_page import ErrorPage


class Errors(ExceptionHandler):
    @handles(Exception)
    async def error(self, ctx: PageContext | None, error: Exception) -> None:
        await self.app.show_error_page(
            ErrorPage,
            error=error,
            title="Unable to open this page",
            args={"message": str(error)},
        )
