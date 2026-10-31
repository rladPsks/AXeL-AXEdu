"""Add 20 explicitly fictional, repeat-safe complaints to an existing demo database."""
import argparse
import json
from datetime import datetime, timedelta, timezone

from agent.routing import route_case
from agent.draft import teacher_card
from backend.db import Database, audit
from backend.demo import seeded
from backend.demo_narratives import CASE_ORIGINALS

# title, category, urgency, nature, original, teacher action
SAMPLES = [
    ("전학 절차 문의", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[1], "학생의 전학 예정일만 확인해 교무 담당자에게 전달해 주세요."),
    ("교외체험학습 신청 안내", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[2], "예정된 결석 기간을 확인하고 담당 부서의 안내를 공유해 주세요."),
    ("재학증명서 발급 문의", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[3], "담임의 별도 조치는 필요하지 않습니다. 행정실에서 안내합니다."),
    ("방과후학교 신청 일정", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[4], "늘봄 담당자의 확정 안내를 학급에 공유해 주세요."),
    ("돌봄교실 귀가 동의서", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[5], "돌봄 담당자에게 변경 예정 사실을 전달해 주세요."),
    ("급식비 환불 절차", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[6], "담임의 별도 조치는 필요하지 않습니다. 수납 담당자 확인이 필요합니다."),
    ("졸업식 학사일정 문의", "INFO", "LOW", "INFO_REQUEST", CASE_ORIGINALS[7], "교무 담당자가 확인한 일정만 공유해 주세요."),
    ("다국어 가정통신문 요청", "INFO", "MID", "INFO_REQUEST", CASE_ORIGINALS[8], "보호자가 이해하기 편한 언어를 확인해 담당자에게 전달해 주세요."),
    ("생활지도 상황 확인", "EDU", "MID", "COMPLAINT", CASE_ORIGINALS[9], "당시 지도 상황과 적용 기준을 사실 중심으로 정리해 주세요."),
    ("학생 갈등 상담 요청", "COUNSEL", "MID", "COUNSEL", CASE_ORIGINALS[10], "학생의 이야기를 개별적으로 듣고 확인된 사실과 추가 확인 사항을 구분해 주세요."),
    ("수행평가 기준 확인", "EDU", "MID", "COMPLAINT", CASE_ORIGINALS[11], "평가 안내 자료와 학생의 제출 기록을 담당자에게 전달해 주세요."),
    ("화장실 시설물 파손", "ADMIN", "HIGH", "SAFETY", CASE_ORIGINALS[12], "위험 장소 접근을 막고 시설 담당자와 관리자에게 즉시 알려 주세요."),
    ("급식 알레르기 표시 확인", "SAFE", "HIGH", "SAFETY", CASE_ORIGINALS[13], "급식 담당자와 보건교사에게 학생의 확인된 알레르기 정보를 전달해 주세요."),
    ("홈페이지 사진 삭제 요청", "ADMIN", "MID", "COMPLAINT", CASE_ORIGINALS[14], "게시 위치와 동의 기록을 확인해 정보 담당자에게 전달해 주세요."),
    ("통합교육 지원 협의", "COUNSEL", "MID", "COUNSEL", CASE_ORIGINALS[15], "수업 참여 상황과 필요한 지원을 정리해 특수교육 담당자와 협의해 주세요."),
    ("하교 안전 동선 확인", "SAFE", "HIGH", "SAFETY", CASE_ORIGINALS[16], "하교 시 위험 구역을 안내하고 안전 담당자에게 현장 확인을 요청해 주세요."),
    ("교사 대상 폭언 신고", "STAFF", "HIGH", "INFRINGEMENT_REVIEW", CASE_ORIGINALS[17], "직접 대응을 중단하고 통화 경위와 보존된 기록을 관리자에게 전달해 주세요."),
    ("방문 협박 정황 검토", "STAFF", "HIGH", "INFRINGEMENT_REVIEW", CASE_ORIGINALS[18], "관리자에게 즉시 알리고 대면 응대를 혼자 진행하지 마세요."),
    ("수업 중 반복 연락 검토", "STAFF", "MID", "INFRINGEMENT_REVIEW", CASE_ORIGINALS[19], "연락 일시와 기존 답변을 정리하고 관리자에게 대응 창구 조정을 요청해 주세요."),
    ("교실 방문 수업 방해 검토", "STAFF", "HIGH", "INFRINGEMENT_REVIEW", CASE_ORIGINALS[20], "학생의 수업 환경을 확보하고 방문 경위와 목격 사실을 관리자에게 전달해 주세요."),
]


def seed_complaints(path):
    database = Database(path)
    added = 0
    with database.transaction() as db:
        seeded(db)
        for index, (title, category, urgency, nature, raw, action) in enumerate(SAMPLES, 1):
            case_id = f"demo-flow-20-{index:02d}"
            if db.execute("SELECT 1 FROM cases WHERE id=?", (case_id,)).fetchone():
                continue
            info = nature == "INFO_REQUEST"
            risk = nature == "INFRINGEMENT_REVIEW"
            received = (datetime(2026, 10, 31, 9, tzinfo=timezone(timedelta(hours=9))) - timedelta(hours=21-index)).isoformat()
            cls = {
                "category": category, "urgency": urgency, "nature": nature,
                "is_informational": info, "classifier_mode": "DEMO_FIXTURE",
                "summary_for_teacher": title + "에 관한 가상 민원입니다. " + raw,
                "core_demand": title, "action_for_teacher": action,
                "urgency_reason": "안전 확보·관리자 검토 우선" if urgency == "HIGH" else "담당자 확인 후 안내" if urgency == "MID" else "일반 안내 가능",
                "infringement_flags": ["HUMAN_REVIEW_REQUIRED"] if risk else [],
                "handling_route": "ADMIN_REVIEW" if risk or urgency == "HIGH" else "FRONT_DESK_RESOLVE" if info else "STAFF_OR_TEAM",
                "needs_fact_check": [] if info else [action],
                "requires_human_review": True,
            }
            domain = "complex_or_sensitive" if risk or nature == "SAFETY" else "simple_inquiry" if info else "student_counseling" if nature == "COUNSEL" else "fact_check"
            routing = route_case(domain, text=title + " " + raw, classification=cls)
            cls["dept"] = routing.get("duty_label") or "민원대응팀"
            workflow = {
                "phase": "HUMAN_REVIEW", "agent": {"classifier_mode": "DEMO_FIXTURE", "orchestrator": "AXeL"},
                "teacher_card": teacher_card(cls["summary_for_teacher"], action, risk),
                "initial_response_draft": ("[가상 시연용 초안] 안녕하세요. " + title + " 문의를 받았습니다. "
                    "담당 부서에서 최신 학교 안내와 적용 절차를 확인한 뒤 필요한 서류·일정·방법을 안내드리겠습니다. "
                    "추가 확인이 필요한 사항은 학교 공식 창구를 통해 연락드리겠습니다.") if info else "",
                "tools": {"rag": [], "history": [], "duty": routing},
                "action_plan": {"teacher_scope": action, "teacher_direct_contact": False},
                "fixture": {"fictional": True, "batch": "demo-flow-20", "legal_verification": False},
            }
            db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES (?,?,?,?,'OPEN',1)",
                       (case_id, "demo-school", "[가상] " + title, "deputy"))
            db.execute("INSERT INTO case_intakes(case_id,received_at,channel,complainant_name,student_name,complaint_type,related_people,incident_context,raw_text,source_type,classification_json,routing_json,created_by,created_at,workflow_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (case_id, received, ["homepage", "ieodream", "message", "external_transfer"][(index-1)%4],
                        f"가상보호자{index:02d}", f"가상학생{index:02d}", title, "[]", "가상 학교 시스템에서 수신한 민원 시연 데이터",
                        raw, "EXTERNAL_TRANSFER" if index%4 == 0 else "DIRECT",
                        json.dumps(cls, ensure_ascii=False), json.dumps(routing, ensure_ascii=False), "admin", received,
                        json.dumps(workflow, ensure_ascii=False)))
            for user in ("admin", "deputy", "teacher"):
                db.execute("INSERT INTO case_participants(case_id,user_id) VALUES (?,?)", (case_id, user))
            audit(db, {"user_id": "admin"}, case_id, "DEMO_CASE_CREATED", 1, {"fictional": True, "batch": "demo-flow-20"})
            added += 1
    return {"added": added, "batch_size": len(SAMPLES), "database": str(path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/private/dev.sqlite3")
    print(json.dumps(seed_complaints(parser.parse_args().db), ensure_ascii=False))
