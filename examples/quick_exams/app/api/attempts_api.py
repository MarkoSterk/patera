from typing import TYPE_CHECKING

from app.schemas import PublicAttemptOut, ResultOut, StartAttemptIn, SubmitIn
from app.services.attempts import AttemptService
from patera.database.sql import transactional

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import Controller, consumes, path, post, produces
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/attempts", tags=["Students"])
class AttemptsApi(Controller["App"]):
    """
    Public student endpoints. The unpredictable exam id grants access to an
    exam, and the attempt id returned on start is the only way to submit it.
    Answer keys are never sent to students.
    """

    attempts: Inject[AttemptService]

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def start_attempt(
        self, req: Request, data: StartAttemptIn
    ) -> Response[PublicAttemptOut]:
        return req.res.json(await self.attempts.start(data))

    @post("/<attempt_id>/submit")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def submit_attempt(
        self, req: Request, attempt_id: str, data: SubmitIn
    ) -> Response[ResultOut]:
        return req.res.json(await self.attempts.submit(attempt_id, data))
