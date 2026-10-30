import json
import uuid
import streamlit as st
from agent.pipeline import process
from db import init_db, list_cases, save_case

st.set_page_config(page_title="AXeL | CARE Agent", page_icon="🏫", layout="wide")
init_db()
st.title("AXeL | CARE Agent")
st.caption("학교 민원대응팀을 위한 맥락 기반 분류·라우팅·근거 제시 에이전트")
st.info("데모용 예비 분류 규칙입니다. 최종 판단·발송·이관은 담당자 승인이 필요합니다.")

with st.form("complaint_form"):
    left, right = st.columns(2)
    with left:
        channel = st.selectbox("접수 경로", ["web", "sms", "call_memo"])
        complainant = st.text_input("보호자 ID (가명)", "PARENT-DEMO")
    with right:
        student_ref = st.text_input("학생 식별 (가명)", "3-2 학생A")
    text = st.text_area("민원 내용", height=140)
    submitted = st.form_submit_button("민원 접수 및 AI 분석", type="primary")

if submitted:
    try:
        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        complaint = {"text": text, "channel": channel, "complainant_id": complainant, "student_ref": student_ref}
        result = process(complaint)
        save_case(case_id, complaint, result)
        st.session_state["latest_result"] = result
        st.success(f"{case_id} 분석 결과가 생성되었습니다.")
    except Exception as exc:
        st.error(f"처리 중 오류: {exc}")

result = st.session_state.get("latest_result")
if result:
    st.subheader("AI 분석 결과")
    c1, c2, c3 = st.columns(3)
    c1.metric("유형", result["classification"]["category"])
    c2.metric("긴급도", result["classification"]["urgency"])
    c3.metric("처리 단계 제안", result["classification"]["stage"])
    st.write("**담당 역할 추천**", result["routing"])
    st.write("**근거 검색 결과**")
    for item in result["evidence"]:
        with st.expander(f'{item["title"]} · p.{item["page"]} · {item["id"]}'):
            st.write(item["text"])
    st.write("**응답 초안**")
    st.text(result["response_draft"])
    st.write("**담임 전달 카드**")
    st.json(result["teacher_card"])
    st.warning("승인 대기: 자동 발송·자동 이관은 수행하지 않습니다.")

st.divider()
st.subheader("접수·처리 이력")
rows = list_cases()
if rows:
    st.dataframe([{"ID": r["id"], "접수": r["received_at"], "유형": json.loads(r["classification_json"])["category"], "상태": r["status"]} for r in rows], use_container_width=True, hide_index=True)
else:
    st.caption("아직 접수된 민원이 없습니다.")
