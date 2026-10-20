from getpass import getpass

from patera.cli import CLIController, cli_controller, command
from patera.database.sql import cli_session
from patera.injectable import Inject

from app import App
from app.schemas import Role, UserIn
from app.services.accounts import AccountService

ROLE_CHOICES: dict[str, list[Role]] = {
    "instructor": ["INSTRUCTOR"],
    "admin": ["ADMIN"],
    "both": ["INSTRUCTOR", "ADMIN"],
}


@cli_controller(name="users")
class UsersCLI(CLIController[App]):
    accounts: Inject[AccountService]

    @command(
        "create",
        help="Create a user: EMAIL [instructor|admin|both]; prompts for the password",
    )
    @cli_session("exams")
    async def create(self, email: str, role: str = "instructor") -> None:
        roles = ROLE_CHOICES.get(role.lower())
        if roles is None:
            raise ValueError("Role must be instructor, admin, or both")
        password = getpass("Password (12+ characters): ")
        if password != getpass("Confirm password: "):
            raise ValueError("Passwords do not match")
        user = await self.accounts.create_user(
            UserIn(email=email, password=password, roles=roles)
        )
        print(f"Created {user.email} with roles: {', '.join(user.roles)}")
