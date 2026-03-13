"""Controller for state machine extension"""

from enum import Enum, IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

from patera.http_statuses import HttpStatus

from ..controller import Controller, post
from ..request import Request
from ..response import Response

if TYPE_CHECKING:
    from .state_machine import StateMachine


class TransitionRequestData(BaseModel):
    """Request model for state transition"""

    step: Enum | StrEnum | IntEnum = Field(description="Step to perform")
    data: Optional[dict[str, Any]] = Field(
        None, description="Additional data for the transition"
    )


class StateMachineController(Controller):
    """Controller for state machine operations"""

    state_machine: "StateMachine"

    @post("/transition")
    async def transition_state(self, req: Request) -> Response:
        """
        Transition to the next state based on the current state.
        """
        data = await req.json()
        if data is None:
            return req.res.json(
                {"message": "Transition data is missing", "status": "error"}
            ).status(HttpStatus.BAD_REQUEST)
        step = data.pop("step", None)
        if step is None:
            return req.res.json(
                {"message": "Missing step information", "status": "error"}
            ).status(HttpStatus.BAD_REQUEST)

        # pylint: disable-next=W0212
        if step in self.state_machine.steps._member_names_:
            step = self.state_machine.steps[step]
        else:
            return req.res.json(
                {"message": f"Step {step} does not exist.", "status": "error"}
            ).status(HttpStatus.BAD_REQUEST)

        transition_request = self.state_machine.transition_request_data(
            step=step, **data
        ).model_dump()
        current_state, transition_context = await self.state_machine.context_loader(
            req, transition_request
        )
        transition_request["current_state"] = current_state
        method = self.state_machine.step_methods_map.get(step, None)
        if method is None:
            return req.res.json(
                {
                    "message": f"Method for step {step.name} not found in mapping.",
                    "status": "error",
                }
            ).status(HttpStatus.NOT_FOUND)
        next_state = self.state_machine.get_next_state(current_state, step)
        if next_state is None:
            return req.res.json(
                {
                    "message": f"Step {step.name} not allowed from current state {current_state.name}",
                    "status": "error",
                }
            ).status(HttpStatus.BAD_REQUEST)
        return await method(req, transition_request, transition_context, next_state)
