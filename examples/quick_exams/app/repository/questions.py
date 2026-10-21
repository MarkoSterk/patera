from patera.database.sql import Repository

from ..models import Question


class Questions(Repository[Question]):
    model = Question

    async def owned_by(self, owner_id: str) -> list[Question]:
        return (
            await self.query.filter_by(owner_id=owner_id)
            .order_by(Question.question_text)
            .all()
        )

    async def ids_in_categories(
        self, owner_id: str, subject_id: str, category_ids: list[str]
    ) -> list[str]:
        questions = await self.query.where(
            Question.owner_id == owner_id,
            Question.subject_id == subject_id,
            Question.category_id.in_(category_ids),
        ).all()
        return [question.id for question in questions]
