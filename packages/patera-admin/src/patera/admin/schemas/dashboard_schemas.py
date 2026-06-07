from typing import Optional

from pydantic import BaseModel, Field


class LogsQuerySchema(BaseModel):
    count: int = Field(50, description="Number of log messages to display")
    severity: str = Field(
        "INFO",
        description="Severity of messages to display. Everything equal to or above.",
    )
    page: int = Field(1, description="Page to display.")
    query: Optional[str] = Field(
        None, description="String to look for in query messages"
    )
    order_by: str = Field("-time", description="Ordering of log messages by time")
