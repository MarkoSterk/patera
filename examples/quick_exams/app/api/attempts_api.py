from typing import TYPE_CHECKING

from app.schemas import PublicAttemptOut, StartAttemptIn, SubmissionOut, SubmitIn
from app.services.attempts import AttemptService
from patera.database.sql import transactional

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import Controller, consumes, path, post, produces, RequestBody
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/attempts", tags=["Students"])
class AttemptsApi(Controller["App"]):
    """
    Public student endpoints. The unpredictable exam id grants access to an
    exam, and the attempt id returned on start is the only way to submit it.
    Answer keys are sent to a student only once: in the response to their
    own submission, as a review of the submitted attempt.
    """

    attempts: Inject[AttemptService]

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def start_attempt(
        self, req: Request, data: RequestBody[StartAttemptIn]
    ) -> Response[PublicAttemptOut]:
        return req.res.json(await self.attempts.start(data))

    @post("/<attempt_id>/submit")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def submit_attempt(
        self, req: Request, attempt_id: str, data: RequestBody[SubmitIn]
    ) -> Response[SubmissionOut]:
        return req.res.json(await self.attempts.submit(attempt_id, data))
