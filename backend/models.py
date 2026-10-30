from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class TaskCreate(Command):
    type: Literal["FACT_CHECK", "COUNSEL", "CALLBACK", "FOLLOW_UP"]
    assignee_id: Identifier
    question: Text
    callback_needed: Literal["REQUIRED", "NOT_REQUIRED", "UNDECIDED"] = "UNDECIDED"


class TaskUpdate(Command):
    status: Literal["ACKNOWLEDGED", "COMPLETED"]
    reply: Text | None = None


class SupportCreate(Command):
    coordinator_id: Identifier
    type: Literal["ATTEND", "JOINT_RESPONSE", "TAKEOVER", "URGENT"]
    reason: Text


class SupportUpdate(Command):
    status: Literal["ACKNOWLEDGED", "IN_PROGRESS", "COMPLETED"]
    result: Text | None = None


class HandoverCreate(Command):
    to_owner_id: Identifier
    reason: Text


class CaseTransition(Command):
    reason: Text
