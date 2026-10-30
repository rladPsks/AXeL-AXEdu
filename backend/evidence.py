"""Append-only original/evidence/response records. No implicit factual verification."""
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field

from .access import accessible_case, admin, authenticate, fail
from .commands import mutate
from .coordination import utc
from .db import now, uid
from .files import file_access
from .models import Command, Identifier, Text

router = APIRouter()


class DocumentVersion(Command):
    content: Text
    provenance: Text
    occurred_at: AwareDatetime
    delivery_state: Literal['DELIVERED','NOT_DELIVERED','UNKNOWN','NOT_APPLICABLE'] = 'UNKNOWN'
    file_id: Identifier | None = None


class DocumentCreate(DocumentVersion):
    kind: Literal['INTAKE','EVIDENCE','OFFICIAL_DOCUMENT','RESPONSE','ACTION']
    label: Identifier


class DocumentAppend(DocumentVersion):
    expected_document_revision: int = Field(ge=1)


def document_version(db, actor, version_id):
    admin(actor)
    row = db.execute('SELECT v.*,d.case_id,d.kind,d.label FROM case_document_versions v JOIN case_documents d ON d.id=v.document_id '
                     'JOIN cases c ON c.id=d.case_id WHERE v.id=? AND c.school_id=?', (version_id,actor['school_id'])).fetchone()
    if row is None:
        fail(404,'DOCUMENT_VERSION_NOT_FOUND','원문 버전을 찾을 수 없습니다.')
    accessible_case(db,actor,row['case_id'])
    if row['file_id']:
        file_access(db,actor,row['file_id'])
    return row


def append(db, actor, case, document_id, revision, body, kind):
    if kind != 'RESPONSE' and body.delivery_state in {'DELIVERED','NOT_DELIVERED'}:
        fail(422,'INVALID_DELIVERY_STATE','답변 자료에만 전달 여부를 기록하세요.')
    if body.file_id:
        file = file_access(db,actor,body.file_id)
        if file['case_id'] != case['id']:
            fail(422,'DOCUMENT_FILE_CASE_MISMATCH','같은 민원의 파일을 선택하세요.')
        if file['category'] == 'AUDIO':
            fail(422,'AUDIO_CONSENT_REQUIRED','음성은 동의·전사 경로에서 확인해야 합니다.')
    version_id = uid()
    db.execute('INSERT INTO case_document_versions(id,document_id,revision,content,provenance,occurred_at,delivery_state,file_id,recorded_by,created_at) '
               'VALUES (?,?,?,?,?,?,?,?,?,?)', (version_id,document_id,revision,body.content,body.provenance,utc(body.occurred_at),body.delivery_state,body.file_id,actor['user_id'],now()))
    return {'document_id':document_id,'document_version_id':version_id,'document_revision':revision}


@router.post('/api/cases/{case_id}/documents',status_code=201)
def create_document(case_id:str,body:DocumentCreate,request:Request):
    def operation(db,actor,case):
        admin(actor)
        document_id = uid()
        db.execute('INSERT INTO case_documents(id,case_id,kind,label,created_by,created_at) VALUES (?,?,?,?,?,?)',
                   (document_id,case_id,body.kind,body.label,actor['user_id'],now()))
        return append(db,actor,case,document_id,1,body,body.kind)
    return mutate(request,case_id,body,'CASE_DOCUMENT_RECORDED',operation,201)


@router.post('/api/documents/{document_id}/versions',status_code=201)
def append_document(document_id:str,body:DocumentAppend,request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        document=db.execute('SELECT d.* FROM case_documents d JOIN cases c ON c.id=d.case_id WHERE d.id=? AND c.school_id=?',(document_id,actor['school_id'])).fetchone()
        if document is None:
            fail(404,'DOCUMENT_NOT_FOUND','원문 자료를 찾을 수 없습니다.')
        case_id=document['case_id']
    def operation(db,actor,case):
        admin(actor)
        latest=db.execute('SELECT MAX(revision) FROM case_document_versions WHERE document_id=?',(document_id,)).fetchone()[0]
        if latest!=body.expected_document_revision:
            fail(409,'DOCUMENT_VERSION_CONFLICT','최신 원문 버전을 조회한 뒤 정정하세요.')
        return append(db,actor,case,document_id,latest+1,body,document['kind'])
    return mutate(request,case_id,body,'CASE_DOCUMENT_RECORDED',operation,201)


def documents(db,actor,case_id):
    admin(actor)
    accessible_case(db,actor,case_id)
    rows=db.execute('SELECT v.id FROM case_document_versions v JOIN case_documents d ON d.id=v.document_id WHERE d.case_id=? '
                    'ORDER BY v.occurred_at,v.created_at,v.id',(case_id,)).fetchall()
    return [dict(document_version(db,actor,row['id'])) for row in rows]


@router.get('/api/cases/{case_id}/documents')
def list_documents(case_id:str,request:Request):
    with request.app.state.db.transaction() as db:
        return documents(db,authenticate(db,request),case_id)


@router.get('/api/document-versions/{version_id}')
def get_document_version(version_id:str,request:Request):
    with request.app.state.db.transaction() as db:
        return dict(document_version(db,authenticate(db,request),version_id))
