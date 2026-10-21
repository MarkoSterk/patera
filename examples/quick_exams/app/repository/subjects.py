from patera.database.sql import Repository

from ..models import Subject


class Subjects(Repository[Subject]):
    model = Subject

    async def owned_by(self, owner_id: str) -> list[Subject]:
        return (
            await self.query.filter_by(owner_id=owner_id).order_by(Subject.name).all()
        )
