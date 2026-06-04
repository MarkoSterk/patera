"""
Admin extension controller
"""

from patera.controller import Controller, get
from patera import Patera, Request, Response


class AdminController(Controller[Patera]):
    """
    Admin controller
    """

    @get("/")
    async def login(self, req: Request) -> Response:
        """
        Login page
        """
        return await req.res.html("_admin/login.html")

    @get("/dashboard")
    async def dashboard(self, req: Request) -> Response:
        """
        Admin dashboard page
        """
        return await req.res.html("_admin/dashboard.html")
