from agent.knowledge import retrieve


def test_school_complaint_law_is_retrievable():
    results = retrieve("학교민원 민원대응팀 설치", as_of_date="2026-10-30")
    citations = [item.get("citation", "") for item in results]
    assert any("초·중등교육법 제37조" in citation for citation in citations)


def test_future_teacher_act_amendment_is_not_current_before_effective_date():
    results = retrieve("교육활동 침해 반복민원 대면 비대면", as_of_date="2026-10-30")
    ids = {item["id"] for item in results}
    assert "TEACHER-ACT-19-FUTURE-20261203" not in ids


def test_future_teacher_act_amendment_is_used_on_effective_date():
    results = retrieve("교육활동 침해 반복민원 대면 비대면", as_of_date="2026-12-03")
    ids = {item["id"] for item in results}
    assert "TEACHER-ACT-19-FUTURE-20261203" in ids
    assert "TEACHER-ACT-19-CURRENT" not in ids


def test_privacy_minimization_rule_is_retrievable():
    results = retrieve("개인정보 최소 수집 학생 보호자 정보", as_of_date="2026-10-30")
    citations = [item.get("citation", "") for item in results]
    assert any("개인정보 보호법 제16조" in citation for citation in citations)
