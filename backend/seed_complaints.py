"""Add 20 explicitly fictional, repeat-safe complaints to an existing demo database."""
import argparse
import json
from datetime import datetime, timedelta, timezone

from agent.routing import route_case
from agent.draft import teacher_card
from backend.db import Database, audit
from backend.demo import seeded

# title, category, urgency, nature, original, teacher action
SAMPLES = [
    ("전학 절차 문의", "INFO", "LOW", "INFO_REQUEST", "다음 달 이사 예정입니다. 전학에 필요한 서류와 전출입 처리 절차를 알고 싶습니다.", "학생의 전학 예정일만 확인해 교무 담당자에게 전달해 주세요."),
    ("교외체험학습 신청 안내", "INFO", "LOW", "INFO_REQUEST", "가족 일정으로 교외체험학습을 신청하려고 합니다. 신청서 제출 방법과 출석인정 기준을 알려 주세요.", "예정된 결석 기간을 확인하고 담당 부서의 안내를 공유해 주세요."),
    ("재학증명서 발급 문의", "INFO", "LOW", "INFO_REQUEST", "재학증명서가 필요합니다. 서류 발급 신청 방법과 방문 시 준비물을 안내해 주세요.", "담임의 별도 조치는 필요하지 않습니다. 행정실에서 안내합니다."),
    ("방과후학교 신청 일정", "INFO", "LOW", "INFO_REQUEST", "방과후학교 미술 프로그램을 신청하고 싶습니다. 신청 일정과 대기자 접수 방법을 알려 주세요.", "늘봄 담당자의 확정 안내를 학급에 공유해 주세요."),
    ("돌봄교실 귀가 동의서", "INFO", "LOW", "INFO_REQUEST", "돌봄교실 이용 학생의 귀가 보호자가 바뀔 예정입니다. 귀가 동의서 변경 절차를 문의합니다.", "돌봄 담당자에게 변경 예정 사실을 전달해 주세요."),
    ("급식비 환불 절차", "INFO", "LOW", "INFO_REQUEST", "스쿨뱅킹으로 납부한 급식비의 환불 가능 여부와 신청 서류를 알고 싶습니다.", "담임의 별도 조치는 필요하지 않습니다. 수납 담당자 확인이 필요합니다."),
    ("졸업식 학사일정 문의", "INFO", "LOW", "INFO_REQUEST", "졸업식 학사일정과 보호자 참석 안내가 언제 공지되는지 알고 싶습니다.", "교무 담당자가 확인한 일정만 공유해 주세요."),
    ("다국어 가정통신문 요청", "INFO", "MID", "INFO_REQUEST", "한국어가 어려워 가정통신문을 이해하지 못했습니다. 다문화 가정을 위한 번역 안내와 통역 지원이 가능한가요?", "보호자가 이해하기 편한 언어를 확인해 담당자에게 전달해 주세요."),
    ("생활지도 상황 확인", "EDU", "MID", "COMPLAINT", "아이가 수업 중 자신만 자주 지적받았다고 합니다. 당시 생활지도 상황과 지도 기준을 확인하고 싶습니다.", "당시 지도 상황과 적용 기준을 사실 중심으로 정리해 주세요."),
    ("학생 갈등 상담 요청", "COUNSEL", "MID", "COUNSEL", "친구 문제로 아이가 등교를 부담스러워합니다. 최근 학생 갈등이 있었는지 확인하고 상담을 요청합니다.", "학생의 이야기를 개별적으로 듣고 확인된 사실과 추가 확인 사항을 구분해 주세요."),
    ("수행평가 기준 확인", "EDU", "MID", "COMPLAINT", "수행평가 결과를 이해하기 어렵습니다. 평가 기준과 학생에게 안내된 내용을 확인해 주세요.", "평가 안내 자료와 학생의 제출 기록을 담당자에게 전달해 주세요."),
    ("화장실 시설물 파손", "ADMIN", "HIGH", "SAFETY", "학생 화장실의 시설물 고장으로 날카로운 부분이 드러나 있습니다. 안전사고가 나기 전에 확인해 주세요.", "위험 장소 접근을 막고 시설 담당자와 관리자에게 즉시 알려 주세요."),
    ("급식 알레르기 표시 확인", "SAFE", "HIGH", "SAFETY", "급식 안내의 알레르기 표시와 학생이 전달받은 내용이 다릅니다. 다음 급식 전에 확인이 필요합니다.", "급식 담당자와 보건교사에게 학생의 확인된 알레르기 정보를 전달해 주세요."),
    ("홈페이지 사진 삭제 요청", "ADMIN", "MID", "COMPLAINT", "홈페이지에 게시된 학생 사진의 공개 동의 여부를 확인해 주세요. 개인정보 보호를 위해 우선 비공개를 요청합니다.", "게시 위치와 동의 기록을 확인해 정보 담당자에게 전달해 주세요."),
    ("통합교육 지원 협의", "COUNSEL", "MID", "COUNSEL", "통합교육 수업에서 아이가 활동에 참여하기 어렵다고 합니다. 특수교육 담당자와 지원 방안을 상담하고 싶습니다.", "수업 참여 상황과 필요한 지원을 정리해 특수교육 담당자와 협의해 주세요."),
    ("하교 안전 동선 확인", "SAFE", "HIGH", "SAFETY", "하교 시간에 학교 앞 공사 차량과 학생 동선이 겹칩니다. 하교 안전을 위한 현장 확인을 요청합니다.", "하교 시 위험 구역을 안내하고 안전 담당자에게 현장 확인을 요청해 주세요."),
    ("교사 대상 폭언 신고", "STAFF", "HIGH", "INFRINGEMENT_REVIEW", "상담 통화 중 보호자가 교사를 향해 반복적으로 모욕적인 표현을 사용했습니다. 교육활동 침해 소지가 있는지 검토를 요청합니다.", "직접 대응을 중단하고 통화 경위와 보존된 기록을 관리자에게 전달해 주세요."),
    ("방문 협박 정황 검토", "STAFF", "HIGH", "INFRINGEMENT_REVIEW", "민원인이 학교에 찾아가 교사를 가만두지 않겠다고 말했습니다. 협박 정황과 교직원 안전 확보 방안을 검토해 주세요.", "관리자에게 즉시 알리고 대면 응대를 혼자 진행하지 마세요."),
    ("수업 중 반복 연락 검토", "STAFF", "MID", "INFRINGEMENT_REVIEW", "학교의 공식 답변 이후에도 같은 요구로 수업 시간마다 교사 개인 번호에 연락이 이어지고 있습니다. 반복 민원과 교육활동 방해 여부를 검토해 주세요.", "연락 일시와 기존 답변을 정리하고 관리자에게 대응 창구 조정을 요청해 주세요."),
    ("교실 방문 수업 방해 검토", "STAFF", "HIGH", "INFRINGEMENT_REVIEW", "예약 없이 교실을 방문한 보호자가 수업 중 큰 소리로 교사를 비난하며 즉시 면담을 요구했습니다. 교육활동 침해 소지 검토를 요청합니다.", "학생의 수업 환경을 확보하고 방문 경위와 목격 사실을 관리자에게 전달해 주세요."),
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
                        "[가상 민원 원문] " + raw, "EXTERNAL_TRANSFER" if index%4 == 0 else "DIRECT",
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
