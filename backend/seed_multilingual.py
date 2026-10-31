"""Three fictional original-language complaints with labelled Korean demo translations."""
import json

from agent.routing import route_case
from agent.draft import teacher_card
from backend.access import DomainError
from backend.db import Database, audit, now, uid
from backend.demo import seeded

SAMPLES = (
    {'language': 'zh', 'label': '중국어', 'title': '교외체험학습 신청 문의', 'category': 'INFO',
     'nature': 'INFO_REQUEST', 'owner': 'academic-head',
     'original': '我们计划下个月带孩子回中国探亲，想申请校外体验学习。请问需要提交哪些材料、通过什么方式申请，以及如何确认是否可以计入出勤？我的韩语不太好，希望能提供中文说明。',
     'korean': '다음 달 아이와 함께 중국의 친척을 방문할 계획이라 교외체험학습을 신청하려고 합니다. 필요한 서류, 신청 방법, 출석 인정 가능 여부를 확인하는 방법을 알려 주세요. 한국어가 서툴러 중국어 안내를 받고 싶습니다.',
     'action': '교외체험학습 신청 서류와 출석 인정 기준을 교무 담당자가 확인하고 중국어 안내를 준비해 주세요.'},
    {'language': 'mn', 'label': '몽골어', 'title': '학생 갈등 상담 요청', 'category': 'COUNSEL',
     'nature': 'COUNSEL', 'owner': 'life-head',
     'original': 'Манай хүүхэд сүүлийн үед ангийнхаа хүүхдүүдтэй маргалдсанаас болж сургуульдаа явахаас санаа зовж байна. Сургууль дээр юу болсон талаар шалгаж, хүүхэдтэй ярилцан дэмжлэг үзүүлж өгнө үү. Боломжтой бол надад монгол хэлээр тайлбарлаж өгнө үү.',
     'korean': '아이가 최근 같은 반 친구들과 다툰 뒤 학교에 가는 것을 걱정하고 있습니다. 학교에서 무슨 일이 있었는지 확인하고 아이와 이야기하여 지원해 주세요. 가능하면 몽골어로 설명해 주세요.',
     'action': '생활부장과 담임이 학생 갈등 경위를 확인하고 확인된 사실과 추가 확인 사항을 구분해 몽골어 상담 안내를 준비해 주세요.'},
    {'language': 'ru', 'label': '러시아어', 'title': '급식비 환불 절차 문의', 'category': 'ADMIN',
     'nature': 'INFO_REQUEST', 'owner': 'office-head',
     'original': 'Наша семья переезжает, и ребёнок переводится в другую школу. Питание уже оплачено за весь месяц. Подскажите, можно ли вернуть деньги за неиспользованные дни, какие документы нужны и куда подать заявление. Мне трудно понимать корейский язык, поэтому прошу предоставить объяснение на русском языке.',
     'korean': '가족이 이사하여 아이가 다른 학교로 전학합니다. 한 달 급식비를 이미 납부했습니다. 이용하지 않은 날의 급식비를 환불받을 수 있는지, 어떤 서류가 필요한지, 어디에 신청해야 하는지 알려 주세요. 한국어를 이해하기 어려워 러시아어 설명을 요청합니다.',
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
