from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from opsmind.schemas.business import ReadModel


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    approved: bool = Field(strict=True)


class RunRead(ReadModel):
    id: str
    status: Literal["running", "waiting_confirmation", "completed", "failed", "rejected"]
    pending_action: dict | None
    result: str | None
    error_code: str | None
    steps: int
    tool_calls: int
    elapsed_ms: int
    events: list[dict]
