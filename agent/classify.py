from .schemas import TriageResult


def classify_complaint(text: str) -> dict:
    if any(w in text for w in ["다쳤", "위험", "자해", "폭력", "안전", "학교폭력"]):
        category, urgency, stage, info = "SAFE", "HIGH", 2, False
    elif any(w in text for w in ["선생님", "수업", "생활지도", "차별", "혼내"]):
        category, urgency, stage, info = "EDU", "MID", 2, False
    elif any(w in text for w in ["언제", "몇 시", "준비물", "일정", "신청", "어디"]):
        category, urgency, stage, info = "INFO", "LOW", 1, True
    else:
        category, urgency, stage, info = "OTHER", "MID", 2, False
    result = TriageResult(category=category, subcategory="규칙 기반 예비 분류",
        dept="안전·보건" if category == "SAFE" else ("교육·학생생활" if category == "EDU" else "교육행정"),
        stage=stage, urgency=urgency, is_informational=info,
        stage_reason="초기 데모 제안이며 담당자 확인이 필요합니다.",
        urgency_reason="본문 키워드 기반 예비 판단입니다.", summary_for_teacher=text[:120],
        action_for_teacher="필요한 사실관계만 확인" if category == "EDU" else "조치 불필요(관리자 처리 중)",
        confidence=0.35, requires_human_review=True)
    return result.model_dump()
