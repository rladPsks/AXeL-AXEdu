"""Update only marked fictional fixtures, retaining original/document and response history."""
import json

from agent.routing import route_case
from .access import DomainError
from .db import Database, audit, now, uid
from .demo import seeded
from .demo_narratives import CASE_ORIGINALS, PATTERN_SAMPLES, MULTILINGUAL_ORIGINALS


def refresh_demo_narratives(path):
    targets = [(f'demo-flow-20-{i:02d}', text, None) for i, text in CASE_ORIGINALS.items()]
    targets += [(f'demo-pattern-{i:02d}', sample[1], None) for i, sample in enumerate(PATTERN_SAMPLES, 1)]
    targets += [('demo-multilingual-'+lang, sample['original'], sample['korean']) for lang, sample in MULTILINGUAL_ORIGINALS.items()]
    updated = 0
    with Database(path).transaction() as db:
        try:
            seeded(db)
        except DomainError:
            return 0
        for cid, original, korean in targets:
            row = db.execute("SELECT i.*,c.version FROM case_intakes i JOIN cases c ON c.id=i.case_id WHERE i.case_id=? AND c.school_id='demo-school'",(cid,)).fetchone()
            if row is None:
                continue
            workflow = json.loads(row['workflow_json'] or '{}')
            if (workflow.get('fixture') or {}).get('fictional') is not True or row['raw_text'] == original:
                continue
            cls = json.loads(row['classification_json'] or '{}')
            analysis_text = korean or original
            if cls.get('classifier_mode') == 'DEMO_FIXTURE':
                cls['summary_for_teacher'] = analysis_text
                card = workflow.setdefault('teacher_card', {})
                if not card.get('edited_by'):
                    card['summary'] = analysis_text
            else:
                cls['analysis_stale'] = True
            domain = 'complex_or_sensitive' if cls.get('nature') in {'SAFETY','INFRINGEMENT_REVIEW'} else 'simple_inquiry' if cls.get('is_informational') else 'fact_check'
            routing = route_case(domain,text=row['complaint_type']+' '+analysis_text,classification=cls)
            tools = workflow.setdefault('tools', {})
            tools.update(rag=[],duty=routing)
            tools.pop('rag_search',None)
            workflow['fixture']['narrative_version'] = 2
            version = row['version']+1
            if korean:
                language = cid.removeprefix('demo-multilingual-')
                workflow.setdefault('multilingual',{}).update(detected_language=language,translated_text_ko=korean,
                    translation_mode='DEMO_FIXTURE',review_status='DRAFT')
                latest = db.execute("SELECT MAX(revision) FROM case_work_products WHERE case_id=? AND kind='TRANSLATION'",(cid,)).fetchone()[0] or 0
                db.execute("INSERT INTO case_work_products(id,case_id,kind,revision,content,source_case_version,recorded_case_version,status,created_by,created_at) VALUES (?,?,'TRANSLATION',?,?,?,?,'DRAFT','admin',?)",
                    (uid(),cid,latest+1,json.dumps({'text':korean,'original':original,'language':language},ensure_ascii=False),version,version,now()))
            document = db.execute("SELECT id FROM case_documents WHERE case_id=? AND kind='INTAKE' ORDER BY created_at,id LIMIT 1",(cid,)).fetchone()
            if document:
                revision = db.execute('SELECT MAX(revision) FROM case_document_versions WHERE document_id=?',(document['id'],)).fetchone()[0] or 0
                db.execute("INSERT INTO case_document_versions(id,document_id,revision,content,provenance,occurred_at,delivery_state,recorded_by,created_at) VALUES (?,?,?,?,?,?,'NOT_APPLICABLE','admin',?)",
                    (uid(),document['id'],revision+1,original,'가상 시연 원문 개선 v2 · 실제 사건 아님',row['received_at'],now()))
            db.execute('UPDATE case_intakes SET raw_text=?,classification_json=?,routing_json=?,workflow_json=? WHERE case_id=?',
                (original,json.dumps(cls,ensure_ascii=False),json.dumps(routing,ensure_ascii=False),json.dumps(workflow,ensure_ascii=False),cid))
            db.execute('UPDATE cases SET version=? WHERE id=?',(version,cid))
            audit(db,{'user_id':'admin'},cid,'DEMO_NARRATIVE_UPDATED',version,{'fictional':True,'narrative_version':2})
            updated += 1
    return updated
