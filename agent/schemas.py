from typing import Literal
from pydantic import BaseModel, Field

Category = Literal["INFO", "EDU", "SAFE", "COUNSEL", "ADMIN", "STAFF", "OTHER"]
Urgency = Literal["HIGH", "MID", "LOW"]
Stage = Literal[1, 2, 3, 4]
Nature = Literal["DIRECT_RELAY", "INFO_REQUEST", "COUNSEL", "COMPLAINT", "SAFETY", "INFRINGEMENT_REVIEW"]
LegalKind = Literal["법정", "질의", "건의", "기타", "고충"]
DomainP55 = Literal["교무/학사", "생활지도/상담", "학부모/교직원 소통", "학교 운영", "기타"]

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
    nature: Nature = "COMPLAINT"
    legal_kind: LegalKind = "기타"
    domain_p55: DomainP55 = "기타"
    special_codes: list[str] = Field(default_factory=list)
    classifier_mode: Literal["LLM", "RULE_FALLBACK"] = "RULE_FALLBACK"
