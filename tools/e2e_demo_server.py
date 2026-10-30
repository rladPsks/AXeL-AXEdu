"""Disposable Render-like demo server: auto seed, public fictional login, no model calls."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.agents import Registry
from backend.main import create_app
import uvicorn

directory = Path(sys.argv[1])
directory.mkdir(parents=True, exist_ok=False)
if '--comparison-fixture' in sys.argv[2:]:
    from backend.seed import seed
    from backend.db import Database
    seed(directory / 'demo.sqlite3')
    with Database(directory / 'demo.sqlite3').transaction() as db:
        db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES ('comparison-example','demo-school','[가상] 비교용 이전 문의','deputy','OPEN',1)")
        db.execute("INSERT INTO case_comparison_profiles(case_id,person_key,issue_key,received_at,updated_by,updated_at) VALUES ('comparison-example','sample-person','sample-issue','2026-10-20T01:00:00.000000+00:00','admin','2026-10-20T01:00:00+00:00')")
        db.execute("INSERT INTO case_documents(id,case_id,kind,label,created_by,created_at) VALUES ('fixture-intake','comparison-example','INTAKE','[가상] 이전 접수','admin','2026-10-20T01:00:00+00:00')")
        db.execute("INSERT INTO case_document_versions(id,document_id,revision,content,provenance,occurred_at,delivery_state,recorded_by,created_at) VALUES ('fixture-intake-v1','fixture-intake',1,'[가상] 이전 문의 원문','브라우저 검증 전용 가상 자료','2026-10-20T01:00:00.000000+00:00','UNKNOWN','admin','2026-10-20T01:00:00+00:00')")
os.environ['SCHOOL_AGENT_AUTO_SEED'] = '1'
os.environ['SCHOOL_AGENT_DEMO'] = '1'
os.environ['SCHOOL_AGENT_RUN_WORKER'] = '1'
registry=Registry()
if '--comparison-ai-fixture' in sys.argv[2:]:
    from backend.agents import Handler
    from backend.comparison_review import ComparisonResult
    def fictional_comparison(snapshot):
        source=snapshot['sources'][0]['data']['sources'][0]['ref']['resource_id']
        return {'summary':'[가상 규칙] 비교 제안 — 실제 모델 호출 아님','findings':[{'category':'UNANSWERED_FOLLOWUP','assessment':'UNVERIFIED','detail':'[가상] 기록만으로 실제 미응답을 단정할 수 없음','source_ids':[source]}],
                'missing_information':['실제 답변 전달 증빙'],'follow_up_questions':['[가상] 이전 답변 전달 여부 확인']}
    registry.register(Handler('COMPARE_CASES',fictional_comparison,ComparisonResult,'browser-comparison-test',generation_mode='RULE'))
uvicorn.run(create_app(directory / 'demo.sqlite3', agent_registry=registry), host='127.0.0.1', port=8000, log_level='warning')
