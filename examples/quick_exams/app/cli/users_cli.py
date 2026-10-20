from getpass import getpass

from patera.cli import CLIController, cli_controller, command
from app import App
from app import store


@cli_controller(name="users")
class UsersCLI(CLIController[App]):
    @command(
        "create",
        help="Create a user: EMAIL [instructor|admin|both]; prompts for password",
    )
    def create(self, email: str, role: str = "instructor") -> None:
        choices = {
            "instructor": ["INSTRUCTOR"],
            "admin": ["ADMIN"],
            "both": ["INSTRUCTOR", "ADMIN"],
        }
        roles = choices.get(role.lower())
        store.require(roles is not None, "Role must be instructor, admin, or both")
        email = store.email_value(email)
        password = getpass("Password (12+ characters): ")
        store.require(
            password == getpass("Confirm password: "), "Passwords do not match"
        )
        with store.database() as db:
            store.user_save(db, {"email": email, "password": password, "roles": roles})
        print(f"Created {email} with roles: {', '.join(roles)}")
