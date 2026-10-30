import json
import os
import urllib.error
import urllib.request

import streamlit as st


API_BASE = os.getenv("AXEL_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def api(method: str, path: str, payload: dict | None = None):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        API_BASE + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"FastAPI 서버에 연결할 수 없습니다: {API_BASE}. "
            "먼저 uvicorn backend.main:app --reload 를 실행하세요."
        ) from exc


def set_case(snapshot: dict):
    st.session_state["case_id"] = snapshot["case"]["id"]
    st.session_state["snapshot"] = snapshot


def refresh_case():
    case_id = st.session_state.get("case_id")
    if case_id:
        set_case(api("GET", f"/cases/{case_id}"))


st.set_page_config(page_title="AXeL Agent Dev Console", page_icon="🧪", layout="wide")
st.title("🧪 AXeL Agent Dev Console")
st.caption("개발·검증 전용 콘솔입니다. 최종 제품 UI는 React 프론트엔드에서 구현합니다.")

with st.sidebar:
    st.write("**Backend**")
    st.code(API_BASE)
    if st.button("Health check"):
        try:
            st.success(api("GET", "/health"))
        except Exception as exc:
            st.error(str(exc))
    if st.button("현재 사건 새로고침"):
        try:
            refresh_case()
            st.success("새로고침 완료")
        except Exception as exc:
            st.error(str(exc))

st.subheader("1. 민원 접수 → 사건 생성")
with st.form("create_case"):
    c1, c2 = st.columns(2)
    with c1:
        channel = st.selectbox("접수 경로", ["web", "sms", "call_memo", "visit"])
        complainant_id = st.text_input("보호자 ID", "PARENT-TEST")
    with c2:
        student_ref = st.text_input("학생 식별", "STUDENT-TEST")
        jurisdiction = st.text_input("관할", "")
    text = st.text_area(
        "민원 원문",
        "우리 아이만 선생님이 계속 혼낸다고 하는데 확인해주세요.",
        height=120,
    )
    create_clicked = st.form_submit_button("사건 생성", type="primary")

if create_clicked:
    payload = {
        "text": text,
        "channel": channel,
        "complainant_id": complainant_id or None,
        "student_ref": student_ref or None,
    }
    if jurisdiction.strip():
        payload["jurisdiction"] = jurisdiction.strip()
    try:
        snapshot = api("POST", "/cases", payload)
        set_case(snapshot)
        st.success(f"사건 생성 완료: {snapshot['case']['id']}")
    except Exception as exc:
        st.error(str(exc))

snapshot = st.session_state.get("snapshot")
if snapshot:
    case = snapshot["case"]
    cls = case.get("classification", {})
    routing = case.get("routing", {})

    st.divider()
    st.subheader("2. 현재 사건 상태")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Case", case["id"])
    m2.metric("Status", case.get("status", "-"))
    m3.metric("Next action", case.get("next_action", "-"))
    m4.metric("Owner", case.get("owner_role", "-"))

    with st.expander("AI 분류", expanded=True):
        st.json({
            "classifier_mode": cls.get("classifier_mode"),
            "category": cls.get("category"),
            "nature": cls.get("nature"),
            "domain_p55": cls.get("domain_p55"),
            "urgency": cls.get("urgency"),
            "stage_reason": cls.get("stage_reason"),
            "urgency_reason": cls.get("urgency_reason"),
            "summary_for_teacher": cls.get("summary_for_teacher"),
            "needs_fact_check": cls.get("needs_fact_check"),
            "special_codes": cls.get("special_codes"),
        })

    with st.expander("라우팅"):
        st.json(routing)

    st.subheader("3. 생성된 업무")
    open_task_count = 0
    for task in snapshot.get("tasks", []):
        if task["status"] != "COMPLETED":
            open_task_count += 1
        title = f"{task['task_type']} · {task['assignee_role']} · {task['status']}"
        with st.expander(title, expanded=task["status"] != "COMPLETED"):
            st.write("**Reason**", task.get("reason", ""))
            try:
                instructions = json.loads(task.get("instructions_json") or "[]")
            except Exception:
                instructions = []
            if instructions:
                st.write("**Instructions**")
                for item in instructions:
                    st.write(f"- {item}")

            if task.get("result_text"):
                st.success(f"회신: {task['result_text']}")

            if task["status"] != "COMPLETED":
                result_text = st.text_area(
                    "회신/검토 결과",
                    key=f"task-result-{task['id']}",
                    placeholder="교사 확인 결과 또는 검토 의견을 입력하세요.",
                )
                if st.button("업무 완료 + Agent 재실행", key=f"task-complete-{task['id']}"):
                    if not result_text.strip():
                        st.warning("회신 내용을 입력하세요.")
                    else:
                        try:
                            updated = api(
                                "POST",
                                f"/cases/{case['id']}/tasks/{task['id']}/complete",
                                {
                                    "result_text": result_text.strip(),
                                    "actor": task["assignee_role"],
                                },
                            )
                            set_case(updated)
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

    if open_task_count == 0:
        st.info("현재 미완료 업무가 없습니다.")

    st.subheader("4. 보호자 답변 초안")
    st.text_area(
        "현재 draft",
        case.get("response_draft") or "아직 답변 초안이 없습니다.",
        height=180,
        disabled=True,
    )

    st.subheader("4-1. AI 판단·답변 근거")
    c_product, c_raw = st.columns(2)
    with c_product:
        if st.button("제품용 근거 카드 불러오기"):
            try:
                st.session_state["explanation_view"] = api(
                    "GET", f"/cases/{case['id']}/explanation"
                )
            except Exception as exc:
                st.error(str(exc))
    with c_raw:
        if st.button("개발용 raw 근거 불러오기"):
            try:
                st.session_state["evidence_view"] = api(
                    "GET", f"/cases/{case['id']}/evidence"
                )
            except Exception as exc:
                st.error(str(exc))

    explanation_view = st.session_state.get("explanation_view")
    if explanation_view:
        with st.expander("제품용 설명 카드", expanded=True):
            judgment = explanation_view.get("judgment") or {}
            st.write(f"**분류**: {judgment.get('category') or '-'}")
            st.write(f"**긴급도**: {judgment.get('urgency') or '-'}")
            st.write("**왜 이렇게 판단했나요?**")
            for item in judgment.get("why") or []:
                st.write(f"- {item}")

            facts = explanation_view.get("facts") or {}
            st.write("**확인된 사실**")
            for item in facts.get("confirmed") or []:
                st.write(f"- {item}")
            if not facts.get("confirmed"):
                st.write("- 현재 사건에서 별도 확인 사실 없음")

            st.write("**보호자 주장 / 요청**")
            for item in facts.get("complainant_claims") or []:
                st.write(f"- {item}")
            if not facts.get("complainant_claims"):
                st.write("- 별도 주장 항목 없음")

            st.write("**추가 확인 필요**")
            for item in facts.get("needs_confirmation") or []:
                st.write(f"- {item}")
            if not facts.get("needs_confirmation"):
                st.write("- 없음")

            st.write("**공식 근거**")
            for item in explanation_view.get("official_basis") or []:
                location = f" · {item.get('location')}" if item.get("location") else ""
                st.write(f"- {item.get('title')} ({item.get('authority')}){location}")
            if not explanation_view.get("official_basis"):
                st.write("- 이번 판단에 사용된 외부 공식 근거 없음")

            history_card = explanation_view.get("history") or {}
            st.write("**반복·누적 맥락**")
            st.write(f"- {history_card.get('label')}")
            if history_card.get("reason"):
                st.caption(history_card.get("reason"))

            safety = explanation_view.get("safety") or {}
            st.info(safety.get("note") or "")

    evidence_view = st.session_state.get("evidence_view")
    if evidence_view:
        with st.expander("분류·라우팅 근거", expanded=True):
            st.json({
                "run_type": evidence_view.get("run_type"),
                "classification_basis": evidence_view.get("classification_basis"),
                "routing_basis": evidence_view.get("routing_basis"),
            })

        response_basis = evidence_view.get("response_basis") or {}
        with st.expander("답변 생성 근거", expanded=True):
            st.write("**사용한 확인 사실 / 근거 요약**")
            st.write(response_basis.get("basis_summary") or "없음")
            st.write("**추가 확인 필요**")
            st.write(response_basis.get("missing_information") or "없음")
            st.write("**사람 검토 필요 주장**")
            st.write(response_basis.get("claims_requiring_review") or "없음")
            st.write("**사람 검토 준비 여부**", response_basis.get("ready_for_human_review"))

        rag_items = evidence_view.get("evidence") or []
        with st.expander(f"RAG 검색 근거 ({len(rag_items)}건)", expanded=True):
            if not rag_items:
                st.info("이번 Agent 실행에서 사용된 외부 문서 근거가 없습니다.")
            for idx, item in enumerate(rag_items, 1):
                st.markdown(f"**{idx}. {item.get('title') or item.get('source_id')}**")
                st.caption(
                    f"source={item.get('source_id')} · type={item.get('source_type')} · "
                    f"page={item.get('pdf_page')} · score={item.get('score')} · "
                    f"review={item.get('verification_status')}"
                )
                if item.get("article"):
                    st.write("조항/위치:", item.get("article"))
                st.write(item.get("text") or "")
                st.divider()

    st.subheader("5. 학교 지원 요청")
    s1, s2 = st.columns(2)
    with s1:
        support_type = st.selectbox(
            "지원 유형",
            [
                "JUDGMENT_CONSULT",
                "ADMIN_PRESENT",
                "JOINT_RESPONSE",
                "TAKEOVER_REVIEW",
                "IMMEDIATE_HELP",
            ],
        )
    with s2:
        requested_by = st.text_input("요청자", "homeroom_teacher")
    note = st.text_input("지원 요청 메모", "보호자 상담 시 관리자 동석을 요청합니다.")

    if st.button("지원 요청 생성"):
        try:
            updated = api(
                "POST",
                f"/cases/{case['id']}/support",
                {
                    "requested_by": requested_by,
                    "support_type": support_type,
                    "note": note,
                },
            )
            set_case(updated)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if snapshot.get("support_requests"):
        st.dataframe(snapshot["support_requests"], use_container_width=True, hide_index=True)

    st.subheader("6. Agent 도구 테스트")
    c_hist, c_report = st.columns(2)

    with c_hist:
        if st.button("반복·누적 맥락 비교"):
            try:
                st.session_state["history_review"] = api(
                    "GET", f"/cases/{case['id']}/history-review"
                )
            except Exception as exc:
                st.error(str(exc))

    with c_report:
        if st.button("교육지원청 지원 보고서 초안 생성"):
            try:
                st.session_state["support_report"] = api(
                    "POST", f"/cases/{case['id']}/support-report"
                )
            except Exception as exc:
                st.error(str(exc))

    if "history_review" in st.session_state:
        with st.expander("History review 결과", expanded=True):
            st.json(st.session_state["history_review"])

    if "support_report" in st.session_state:
        with st.expander("Support report 결과", expanded=True):
            st.json(st.session_state["support_report"])

    st.subheader("7. 사건 Timeline")
    events = []
    for event in snapshot.get("events", []):
        payload = event.get("payload_json")
        try:
            payload = json.loads(payload or "{}")
        except Exception:
            pass
        events.append({
            "created_at": event.get("created_at"),
            "event_type": event.get("event_type"),
            "actor": event.get("actor"),
            "payload": payload,
        })
    st.dataframe(events, use_container_width=True, hide_index=True)
else:
    st.info("위에서 민원을 입력하고 사건을 생성하세요.")
