from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CaseCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    channel: Literal[
        "web", "sms", "call_memo", "visit",
        "phone", "message", "ieodream", "homepage",
        "external_transfer", "other"
    ] = "web"
    complainant_id: str | None = None
    student_ref: str | None = None
    complainant_name: str | None = None
    student_name: str | None = None
    complaint_type: str | None = None
    related_people: list[str] = Field(default_factory=list)
    incident_context: str | None = None
    received_at: str | None = None
    source_type: Literal["DIRECT", "EXTERNAL_TRANSFER"] = "DIRECT"
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



class DeliveryRequest(BaseModel):
    actor: str = "complaint_response_team"
    channel: str = "official_channel"
    note: str = ""



class DelegationRequest(BaseModel):
    actor: str
    note: str = ""
