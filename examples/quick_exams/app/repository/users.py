from patera.database.sql import Repository

from ..models import User


class Users(Repository[User]):
    model = User

    async def count_admins(self) -> int:
        return await self.count(is_admin=True)
