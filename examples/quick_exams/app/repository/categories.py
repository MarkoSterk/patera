from patera.database.sql import Repository

from ..models import Category


class Categories(Repository[Category]):
    model = Category

    async def owned_by(self, owner_id: str) -> list[Category]:
        return (
            await self.query.filter_by(owner_id=owner_id).order_by(Category.name).all()
        )
