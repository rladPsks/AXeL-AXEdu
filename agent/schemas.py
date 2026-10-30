from typing import Literal
from pydantic import BaseModel, Field

Category = Literal["INFO", "EDU", "SAFE", "COUNSEL", "ADMIN", "STAFF", "OTHER"]
Urgency = Literal["HIGH", "MID", "LOW"]
Stage = Literal[1, 2, 3, 4]

class EvidenceQuote(BaseModel):
    flag: str
    quote: str

class ActionItem(BaseModel):
    action: str
    target_role: str
    reason: str

class TriageResult(BaseModel):
    category: Category = "OTHER"
    subcategory: str = ""
    dept: str = "교육행정"
    stage: Stage = 2
    stage_reason: str = "초기 제안이며 관리자 확인 필요"
    urgency: Urgency = "MID"
    urgency_reason: str = "초기 제안이며 관리자 확인 필요"
    is_informational: bool = False
    infringement_flags: list[str] = Field(default_factory=list)
    infringement_evidence: list[EvidenceQuote] = Field(default_factory=list)
    emotion: Literal["CALM", "UPSET", "HOSTILE"] = "CALM"
    language: str = "ko"
    summary_for_teacher: str = ""
    action_for_teacher: str = "조치 불필요(관리자 처리 중)"
    needs_fact_check: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    requires_human_review: bool = True
