from patera.database.sql import Repository

from ..models import Attempt, AttemptQuestion


class Attempts(Repository[Attempt]):
    model = Attempt

    async def submitted(self, owner_id: str | None = None) -> list[Attempt]:
        query = self.query.where(Attempt.submitted_at.is_not(None))
        if owner_id is not None:
            query = query.filter_by(owner_id=owner_id)
        return await query.order_by(Attempt.submitted_at).all()


class AttemptQuestions(Repository[AttemptQuestion]):
    model = AttemptQuestion

    async def for_attempt(self, attempt_id: str) -> list[AttemptQuestion]:
        return (
            await self.query.filter_by(attempt_id=attempt_id)
            .order_by(AttemptQuestion.position)
            .all()
        )

    async def for_attempts(
        self, attempt_ids: list[str]
    ) -> dict[str, list[AttemptQuestion]]:
        grouped: dict[str, list[AttemptQuestion]] = {key: [] for key in attempt_ids}
        if not attempt_ids:
            return grouped
        rows = (
            await self.query.where(AttemptQuestion.attempt_id.in_(attempt_ids))
            .order_by(AttemptQuestion.attempt_id, AttemptQuestion.position)
            .all()
        )
        for row in rows:
            grouped[row.attempt_id].append(row)
        return grouped
