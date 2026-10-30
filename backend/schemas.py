from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CaseCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    channel: Literal["web", "sms", "call_memo", "visit"] = "web"
    complainant_id: str | None = None
    student_ref: str | None = None
    as_of_date: str | None = None
    jurisdiction: str | None = None


class TaskCompleteRequest(BaseModel):
    result_text: str = Field(min_length=1)
    actor: str = "staff"


class SupportRequestCreate(BaseModel):
    requested_by: str
    support_type: Literal[
        "JUDGMENT_CONSULT",
        "ADMIN_PRESENT",
        "JOINT_RESPONSE",
        "TAKEOVER_REVIEW",
        "IMMEDIATE_HELP",
    ]
    note: str = ""


class CaseSnapshotResponse(BaseModel):
    case: dict
    tasks: list[dict]
    events: list[dict]
    support_requests: list[dict]
