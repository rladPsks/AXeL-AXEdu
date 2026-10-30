def draft_information_reply(complaint_text: str, evidence: list[dict]) -> str:
    if not evidence:
        return "확인 가능한 공식 근거를 찾지 못했습니다. 학교 규정과 최신 안내를 확인한 뒤 담당자가 회신해야 합니다."
    refs = "; ".join(f'{x["title"]} p.{x["page"]} ({x["id"]})' for x in evidence)
    return ("안녕하세요. 문의하신 내용을 확인했습니다.\n"
            "현재 검색된 자료를 기준으로 작성한 검토용 초안입니다. 최신 학교 안내와 일치하는지 담당자 확인 후 회신해 주세요.\n"
            f"확인 근거: {refs}")


def teacher_card(summary: str, action: str, risk_present: bool) -> dict:
    return {"summary": summary, "action": action or "조치 불필요(관리자 처리 중)",
            "notice": "민원인에게 직접 연락하지 말고 지정된 학교 담당자의 안내를 따르세요.",
            "raw_complaint_visibility": "HIDDEN" if risk_present else "ROLE_RESTRICTED"}
