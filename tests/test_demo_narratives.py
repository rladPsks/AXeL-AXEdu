import json

from backend.db import Database, now, uid
from backend.seed import seed
from backend.seed_complaints import seed_complaints
from backend.seed_patterns import seed_patterns
from backend.seed_multilingual import seed_multilingual
from backend.demo_narratives import CASE_ORIGINALS, PATTERN_SAMPLES, MULTILINGUAL_ORIGINALS
from backend.refresh_demo_narratives import refresh_demo_narratives


def test_fictional_narrative_upgrade_preserves_written_responses_and_document_history(tmp_path):
    path=tmp_path/'narratives.sqlite3'
    seed(path);seed_complaints(path);seed_patterns(path);seed_multilingual(path)
    assert refresh_demo_narratives(path)==0
    db=Database(path)
    with db.transaction() as connection:
        for cid in ('demo-flow-20-03','demo-pattern-04','demo-multilingual-mn'):
            connection.execute('UPDATE case_intakes SET raw_text=? WHERE case_id=?',('이전 짧은 시연 원문',cid))
        workflow=json.loads(connection.execute("SELECT workflow_json FROM case_intakes WHERE case_id='demo-flow-20-03'").fetchone()[0])
        workflow['teacher_card'].update(summary='담당자가 직접 수정한 요약',edited_by='admin')
        connection.execute("UPDATE case_intakes SET workflow_json=? WHERE case_id='demo-flow-20-03'",(json.dumps(workflow),))
        connection.execute("INSERT INTO case_work_products(id,case_id,kind,revision,content,source_case_version,recorded_case_version,status,created_by,created_at) VALUES (?,'demo-flow-20-03','RESPONSE',1,?,1,1,'DRAFT','admin',?)",
            (uid(),json.dumps({'text':'내가 직접 작성한 학부모 답변'}),now()))
        document=connection.execute("SELECT id FROM case_documents WHERE case_id='demo-pattern-04' AND kind='INTAKE'").fetchone()[0]
        connection.execute("INSERT INTO case_document_versions(id,document_id,revision,content,provenance,occurred_at,delivery_state,recorded_by,created_at) VALUES (?,?,2,'이전 원문 자료','시연 테스트',?,'NOT_APPLICABLE','admin',?)",(uid(),document,now(),now()))
    assert refresh_demo_narratives(path)==3
    assert refresh_demo_narratives(path)==0
    with db.transaction() as connection:
        assert connection.execute("SELECT raw_text FROM case_intakes WHERE case_id='demo-flow-20-03'").fetchone()[0]==CASE_ORIGINALS[3]
        workflow=json.loads(connection.execute("SELECT workflow_json FROM case_intakes WHERE case_id='demo-flow-20-03'").fetchone()[0])
        assert workflow['teacher_card']['summary']=='담당자가 직접 수정한 요약'
        response=connection.execute("SELECT content,status FROM case_work_products WHERE kind='RESPONSE'").fetchone()
        assert json.loads(response['content'])['text']=='내가 직접 작성한 학부모 답변' and response['status']=='DRAFT'
        versions=connection.execute('SELECT content FROM case_document_versions WHERE document_id=? ORDER BY revision',(document,)).fetchall()
        assert versions[-2][0]=='이전 원문 자료' and versions[-1][0]==PATTERN_SAMPLES[3][1]
        translation=connection.execute("SELECT content,status FROM case_work_products WHERE case_id='demo-multilingual-mn' ORDER BY revision DESC").fetchone()
        assert json.loads(translation['content'])['text']==MULTILINGUAL_ORIGINALS['mn']['korean'] and translation['status']=='DRAFT'


def test_unmarked_records_are_never_rewritten(tmp_path):
    path=tmp_path/'ordinary.sqlite3'
    assert refresh_demo_narratives(path)==0
    seed(path);seed_complaints(path)
    with Database(path).transaction() as db:
        db.execute("UPDATE case_intakes SET raw_text='사용자가 입력한 원문',workflow_json='{}' WHERE case_id='demo-flow-20-01'")
    assert refresh_demo_narratives(path)==0
    with Database(path).transaction() as db:
        assert db.execute("SELECT raw_text FROM case_intakes WHERE case_id='demo-flow-20-01'").fetchone()[0]=='사용자가 입력한 원문'
