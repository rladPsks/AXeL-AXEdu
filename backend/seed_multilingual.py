"""Three fictional original-language complaints with labelled Korean demo translations."""
import json

from agent.routing import route_case
from agent.draft import teacher_card
from backend.access import DomainError
from backend.db import Database, audit, now, uid
from backend.demo import seeded
from backend.demo_narratives import MULTILINGUAL_ORIGINALS

SAMPLES = (
    {'language': 'zh', 'label': '중국어', 'title': '교외체험학습 신청 문의', 'category': 'INFO',
     'nature': 'INFO_REQUEST', 'owner': 'academic-head',
     'original': MULTILINGUAL_ORIGINALS['zh']['original'],
     'korean': MULTILINGUAL_ORIGINALS['zh']['korean'],
     'action': '교외체험학습 신청 서류와 출석 인정 기준을 교무 담당자가 확인하고 중국어 안내를 준비해 주세요.'},
    {'language': 'mn', 'label': '몽골어', 'title': '학생 갈등 상담 요청', 'category': 'COUNSEL',
     'nature': 'COUNSEL', 'owner': 'life-head',
     'original': MULTILINGUAL_ORIGINALS['mn']['original'],
     'korean': MULTILINGUAL_ORIGINALS['mn']['korean'],
     'action': '생활부장과 담임이 학생 갈등 경위를 확인하고 확인된 사실과 추가 확인 사항을 구분해 몽골어 상담 안내를 준비해 주세요.'},
    {'language': 'ru', 'label': '러시아어', 'title': '급식비 환불 절차 문의', 'category': 'ADMIN',
     'nature': 'INFO_REQUEST', 'owner': 'office-head',
     'original': MULTILINGUAL_ORIGINALS['ru']['original'],
     'korean': MULTILINGUAL_ORIGINALS['ru']['korean'],
     'action': '행정실에서 납부 내역과 급식비 환불 기준·신청 서류를 확인하고 러시아어 안내를 준비해 주세요.'},
)


def marker(sample):
    return f"[다국어-{sample['language']}] {sample['label']} {sample['title']}"


def seed_multilingual(path):
    added = 0
    with Database(path).transaction() as db:
        try:
            seeded(db)
        except DomainError:
            return 0
        for sample in SAMPLES:
            case_id = 'demo-multilingual-' + sample['language']
            if db.execute('SELECT 1 FROM cases WHERE id=? OR (school_id=? AND title=?)',
                          (case_id, 'demo-school', marker(sample))).fetchone():
                continue
            at = now()
            owner = sample['owner']
            if not db.execute("SELECT 1 FROM memberships WHERE school_id='demo-school' AND user_id=? AND active=1", (owner,)).fetchone():
                owner = 'admin'
            cls = {'category': sample['category'], 'nature': sample['nature'], 'urgency': 'MID',
                'is_informational': sample['nature'] == 'INFO_REQUEST', 'classifier_mode': 'DEMO_FIXTURE',
                'original_language': sample['language'], 'translation_mode': 'DEMO_FIXTURE',
                'core_demand': sample['title'], 'summary_for_teacher': sample['korean'],
                'action_for_teacher': sample['action'], 'infringement_flags': [],
                'handling_route': 'STAFF_OR_TEAM',
                'urgency_reason': '담당자 확인과 번역 내용 검토 후 안내가 필요한 가상 사례'}
            routing = route_case('fact_check', text=sample['korean'], classification=cls)
            workflow = {'agent': {'classifier_mode': 'DEMO_FIXTURE'},
                'teacher_card': teacher_card(sample['korean'], sample['action'], False),
                'tools': {'rag': [], 'history': [], 'duty': routing},
                'multilingual': {'detected_language': sample['language'], 'translated_text_ko': sample['korean'],
                    'translation_mode': 'DEMO_FIXTURE', 'review_status': 'DRAFT'},
                'fixture': {'fictional': True, 'batch': 'multilingual-v1'}, 'initial_response_draft': ''}
            db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES (?,'demo-school',?,?,'OPEN',1)",
                       (case_id, marker(sample), owner))
            db.execute("INSERT INTO case_intakes(case_id,received_at,channel,complainant_name,student_name,complaint_type,related_people,incident_context,raw_text,source_type,classification_json,routing_json,created_by,created_at,workflow_json) VALUES (?,?,'homepage',?,?,?,'[]',?,?,'DIRECT',?,?,'admin',?,?)",
                       (case_id, at, '가상보호자-'+sample['language'], '가상학생-'+sample['language'], marker(sample),
                        '다국어 가상 민원 시연 · 실제 인물·사건과 무관', sample['original'],
                        json.dumps(cls, ensure_ascii=False), json.dumps(routing, ensure_ascii=False), at, json.dumps(workflow, ensure_ascii=False)))
            for user in {'admin', owner}:
                db.execute('INSERT OR IGNORE INTO case_participants(case_id,user_id) VALUES (?,?)', (case_id, user))
            content = {'text': sample['korean'], 'original': sample['original'], 'language': sample['language']}
            db.execute("INSERT INTO case_work_products(id,case_id,kind,revision,content,source_case_version,recorded_case_version,status,created_by,created_at) VALUES (?,?,'TRANSLATION',1,?,1,1,'DRAFT','admin',?)",
                       (uid(), case_id, json.dumps(content, ensure_ascii=False), at))
            audit(db, {'user_id': 'admin'}, case_id, 'DEMO_MULTILINGUAL_CREATED', 1, {'fictional': True, 'language': sample['language']})
            added += 1
    return added
