import json
import streamlit as st

from agent.workflow import create_case, complete_task, get_case_snapshot, request_support
from db import init_db, list_cases

st.set_page_config(page_title="AXeL | CARE Agent", page_icon="🏫", layout="wide")
init_db()
st.title("AXeL | CARE Agent")
st.caption("학교 공식 민원 흐름을 사건·업무·지원·기록으로 연결하는 AI Agent")
st.info("AI가 업무를 생성·정리하지만 교육활동 침해 확정, 자동 제재·이관·외부 발송은 학교 권한자가 결정합니다.")

with st.form("complaint_form"):
    left, right = st.columns(2)
    with left:
        channel = st.selectbox("접수 경로", ["web", "sms", "call_memo", "visit"])
        complainant = st.text_input("보호자 ID (가명)", "PARENT-DEMO")
    with right:
        student_ref = st.text_input("학생 식별 (가명)", "3-2 학생A")
    text = st.text_area("민원 내용", height=140)
    submitted = st.form_submit_button("민원 접수", type="primary")

if submitted:
    try:
        snapshot = create_case({
            "text": text,
            "channel": channel,
            "complainant_id": complainant,
            "student_ref": student_ref,
        })
        st.session_state["case_id"] = snapshot["case"]["id"]
        st.success(f"{snapshot['case']['id']} 사건이 생성되고 필요한 업무가 배정되었습니다.")
    except Exception as exc:
        st.error(f"처리 중 오류: {exc}")

case_id = st.session_state.get("case_id")
if case_id:
    snapshot = get_case_snapshot(case_id)
    case = snapshot["case"]
    cls = case.get("classification", {})

    st.subheader("사건 작업 공간")
    a, b, c, d = st.columns(4)
    a.metric("상태", case["status"])
    b.metric("긴급도", case.get("urgency") or "-")
    c.metric("총괄 역할", case["owner_role"])
    d.metric("다음 행동", case.get("next_action") or "-")

    st.write("**AI 초기 분류**")
    st.json({
        "nature": cls.get("nature"),
        "domain_p55": cls.get("domain_p55"),
        "urgency": cls.get("urgency"),
        "summary_for_teacher": cls.get("summary_for_teacher"),
        "classifier_mode": cls.get("classifier_mode"),
    })

    st.write("**교직원 업무**")
    for task in snapshot["tasks"]:
        with st.expander(f"{task['task_type']} · {task['assignee_role']} · {task['status']}"):
            st.write(task["reason"])
            try:
                instructions = json.loads(task["instructions_json"])
            except Exception:
                instructions = []
            for item in instructions:
                st.write(f"- {item}")
            if task["status"] != "COMPLETED":
                result_text = st.text_area("회신/확인 결과", key=f"result-{task['id']}")
                if st.button("업무 완료 및 Agent 재실행", key=f"complete-{task['id']}"):
                    try:
                        complete_task(task["id"], result_text, actor=task["assignee_role"])
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            elif task.get("result_text"):
                st.success(task["result_text"])

    with st.expander("학교 지원 요청"):
        support_type = st.selectbox(
            "지원 종류",
            ["JUDGMENT_CONSULT", "ADMIN_PRESENT", "JOINT_RESPONSE", "TAKEOVER_REVIEW", "IMMEDIATE_HELP"],
        )
        support_note = st.text_input("요청 메모")
        if st.button("지원 요청"):
            request_support(case_id, "current_staff", support_type, support_note)
            st.rerun()

    if snapshot["support_requests"]:
        st.write("**지원 요청 현황**")
        st.dataframe(snapshot["support_requests"], use_container_width=True, hide_index=True)

    st.write("**현재 보호자 답변 초안**")
    st.text(case.get("response_draft") or "아직 답변 초안이 없습니다.")

    st.write("**사건 타임라인**")
    timeline = []
    for e in snapshot["events"]:
        timeline.append({
            "시각": e["created_at"],
            "행동": e["event_type"],
            "주체": e["actor"],
        })
    st.dataframe(timeline, use_container_width=True, hide_index=True)

st.divider()
st.subheader("학교 업무 현황")
rows = list_cases()
if rows:
    table = []
    for r in rows:
        if "owner_role" in r:
            table.append({
                "ID": r["id"],
                "접수": r["received_at"],
                "상태": r["status"],
                "총괄": r["owner_role"],
                "다음 행동": r.get("next_action"),
            })
        else:
            table.append({"ID": r["id"], "접수": r["received_at"], "상태": r["status"]})
    st.dataframe(table, use_container_width=True, hide_index=True)
else:
    st.caption("아직 접수된 민원이 없습니다.")
