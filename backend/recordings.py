"""Consent-gated recordings: consent records, append-only transcript revisions and worker guards."""
import json
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .access import DomainError, accessible_case, authenticate, fail
from .agents import ProviderFailure, require_usable_result, run_access
from .commands import mutate
from .db import now, uid
from .files import file_access
from .models import Command, Identifier, Text

router = APIRouter()
Speaker = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


def active_consent(db, file_id):
    return db.execute('SELECT * FROM audio_consents WHERE file_id=? AND revoked_at IS NULL', (file_id,)).fetchone()


def audio_file(db, actor, case_id, file_id):
    meta = file_access(db, actor, file_id)
    if meta['case_id'] != case_id or meta['category'] != 'AUDIO':
        fail(422, 'AUDIO_FILE_REQUIRED', '이 민원에 등록한 음성 자료를 선택하세요.')
    return meta


class ConsentCreate(Command):
    file_id: Identifier
    subject: Text
    scope: Text


class ConsentRevoke(Command):
    reason: Text


@router.post('/api/cases/{case_id}/audio-consents', status_code=201)
def record_consent(case_id: str, body: ConsentCreate, request: Request):
    def operation(db, actor, case):
        audio_file(db, actor, case_id, body.file_id)
        if active_consent(db, body.file_id):
            fail(409, 'CONSENT_EXISTS', '이미 동의가 확인된 음성입니다.')
        consent_id = uid()
        db.execute('INSERT INTO audio_consents(id,case_id,file_id,subject,scope,confirmed_by,confirmed_at) '
                   'VALUES (?,?,?,?,?,?,?)',
                   (consent_id, case_id, body.file_id, body.subject, body.scope, actor['user_id'], now()))
        return {'consent_id': consent_id, 'file_id': body.file_id}
    return mutate(request, case_id, body, 'AUDIO_CONSENT_RECORDED', operation, 201)


@router.post('/api/audio-consents/{consent_id}/revoke')
def revoke_consent(consent_id: str, body: ConsentRevoke, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        row = db.execute('SELECT c.case_id AS case_id FROM audio_consents c JOIN cases k ON k.id=c.case_id '
                         'WHERE c.id=? AND k.school_id=?', (consent_id, actor['school_id'])).fetchone()
        if row is None:
            fail(404, 'CONSENT_NOT_FOUND', '동의 기록을 찾을 수 없습니다.')
        case_id = row['case_id']

    def operation(db, actor, case):
        row = db.execute('SELECT * FROM audio_consents WHERE id=? AND case_id=?', (consent_id, case_id)).fetchone()
        file_access(db, actor, row['file_id'])
        if row['revoked_at'] is not None:
            fail(409, 'CONSENT_ALREADY_REVOKED', '이미 철회된 동의입니다.')
        db.execute('UPDATE audio_consents SET revoked_at=?,revoked_by=?,revoke_reason=? WHERE id=?',
                   (now(), actor['user_id'], body.reason, consent_id))
        return {'consent_id': consent_id, 'revoked': True}
    return mutate(request, case_id, body, 'AUDIO_CONSENT_REVOKED', operation, allow_closed=True)


@router.get('/api/cases/{case_id}/audio-consents')
def list_consents(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        items = []
        for row in db.execute('SELECT * FROM audio_consents WHERE case_id=? ORDER BY confirmed_at,id', (case_id,)):
            try:
                file_access(db, actor, row['file_id'])
            except DomainError:
                continue  # restricted recordings stay hidden from other participants
            items.append(dict(row))
        return items


class SegmentEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Identifier
    text: Text
    speaker: Speaker


class TranscriptSave(Command):
    file_id: Identifier
    run_id: Identifier | None = None
    edits: list[SegmentEdit] | None = Field(default=None, min_length=1, max_length=2000)
    reason: Text | None = None

    @model_validator(mode='after')
    def original_or_correction(self):
        if (self.run_id is None) == (self.edits is None):
            raise ValueError('원본 저장(run_id) 또는 정정(edits) 중 하나만 지정하세요.')
        if self.edits is not None and self.reason is None:
            raise ValueError('정정 사유가 필요합니다.')
        return self


@router.post('/api/cases/{case_id}/transcripts', status_code=201)
def save_transcript(case_id: str, body: TranscriptSave, request: Request):
    def operation(db, actor, case):
        audio_file(db, actor, case_id, body.file_id)
        if active_consent(db, body.file_id) is None:
            fail(409, 'AUDIO_CONSENT_REQUIRED', '동의가 확인되지 않았거나 철회된 음성입니다.')
        latest = db.execute('SELECT * FROM transcripts WHERE file_id=? ORDER BY revision DESC LIMIT 1',
                            (body.file_id,)).fetchone()
        if body.run_id is not None:
            if latest is not None:
                fail(409, 'TRANSCRIPT_EXISTS', '원본 전사가 이미 저장되어 있습니다. 수정은 정정 버전으로 저장하세요.')
            result = require_usable_result(db, actor, case, body.run_id, 'TRANSCRIBE_AUDIO')
            run, _ = run_access(db, actor, body.run_id)
            refs = json.loads(run['input_refs'])['input_refs']
            if not any(r['resource_type'] == 'FILE' and r['resource_id'] == body.file_id for r in refs):
                fail(422, 'RUN_FILE_MISMATCH', '선택한 음성에 대한 전사 결과가 아닙니다.')
            segments, revision, reason, source_run = result['segments'], 1, None, body.run_id
        else:
            if latest is None:
                fail(409, 'TRANSCRIPT_REQUIRED', '먼저 원본 전사를 저장하세요.')
            previous = json.loads(latest['segments'])
            edits = {edit.id: edit for edit in body.edits}
            if len(edits) != len(body.edits) or set(edits) != {segment['id'] for segment in previous}:
                fail(422, 'SEGMENT_MISMATCH', '정정에는 모든 구간이 한 번씩 포함되어야 합니다.')
            # Times and ids always come from the stored revision; only text and speaker can be corrected.
            segments = [{**segment, 'text': edits[segment['id']].text, 'speaker': edits[segment['id']].speaker}
                        for segment in previous]
            if segments == previous:
                fail(422, 'NO_CHANGE', '변경된 내용이 없습니다.')
            revision, reason, source_run = latest['revision'] + 1, body.reason, None
        transcript_id = uid()
        db.execute('INSERT INTO transcripts(id,case_id,file_id,revision,source_run_id,segments,reason,created_by,created_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?)',
                   (transcript_id, case_id, body.file_id, revision, source_run,
                    json.dumps(segments, ensure_ascii=False), reason, actor['user_id'], now()))
        return {'transcript_id': transcript_id, 'file_id': body.file_id, 'revision': revision}
    return mutate(request, case_id, body, 'TRANSCRIPT_SAVED', operation, 201)


@router.get('/api/cases/{case_id}/transcripts')
def list_transcripts(case_id: str, request: Request, file_id: str = Query(min_length=1, max_length=128)):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        audio_file(db, actor, case_id, file_id)
        rows = db.execute('SELECT * FROM transcripts WHERE case_id=? AND file_id=? ORDER BY revision',
                          (case_id, file_id)).fetchall()
        return [{'id': r['id'], 'file_id': r['file_id'], 'revision': r['revision'], 'source_run_id': r['source_run_id'],
                 'reason': r['reason'], 'created_by': r['created_by'], 'created_at': r['created_at'],
                 'segments': json.loads(r['segments'])} for r in rows]


def transcript_row(db, actor, transcript_id):
    row = db.execute('SELECT t.* FROM transcripts t JOIN cases c ON c.id=t.case_id WHERE t.id=? AND c.school_id=?',
                     (transcript_id, actor['school_id'])).fetchone()
    if row is None:
        fail(404, 'TRANSCRIPT_NOT_FOUND', '전사를 찾을 수 없습니다.')
    accessible_case(db, actor, row['case_id'])
    file_access(db, actor, row['file_id'])
    return row


def transcript_input(db, actor, transcript_id):
    """Snapshot input for a summary: the latest revision of a recording whose consent is still active."""
    row = transcript_row(db, actor, transcript_id)
    latest = db.execute('SELECT MAX(revision) FROM transcripts WHERE file_id=?', (row['file_id'],)).fetchone()[0]
    if row['revision'] != latest:
        fail(409, 'INPUT_VERSION_CONFLICT', '가장 최근에 정정한 전사를 선택하세요.')
    consent = active_consent(db, row['file_id'])
    if consent is None:
        fail(409, 'AUDIO_CONSENT_REQUIRED', '동의가 철회되었거나 확인되지 않은 음성의 전사는 분석할 수 없습니다.')
    return {'id': row['id'], 'case_id': row['case_id'], 'file_id': row['file_id'], 'revision': row['revision'],
            'consent_id': consent['id'], 'segments': json.loads(row['segments'])}


def consent_guard(db, job):
    """Worker check right before audio or a transcript leaves the server for a provider."""
    if job['purpose'] not in {'TRANSCRIBE_AUDIO', 'SUMMARIZE_TRANSCRIPT'}:
        return
    for source in json.loads(job['snapshot'])['sources']:
        data = source['data']
        file_id = data['id'] if source['ref']['resource_type'] == 'FILE' else data['file_id']
        consent = active_consent(db, file_id)
        if consent is None or consent['id'] != data.get('consent_id'):
            raise ProviderFailure('AUDIO_CONSENT_REVOKED', '음성 분석 동의가 철회되었거나 확인되지 않아 처리하지 않았습니다.')


def audio_payload(db, job):
    """In-memory only: audio bytes are never stored in the run snapshot."""
    snapshot = json.loads(job['snapshot'])
    file_id = snapshot['sources'][0]['data']['id']
    row = db.execute('SELECT content,filename,media_type FROM private_files WHERE id=?', (file_id,)).fetchone()
    if row is None:
        raise ProviderFailure('AUDIO_MISSING', '음성 파일을 찾을 수 없습니다.')
    snapshot['audio'] = {'bytes': bytes(row['content']), 'filename': row['filename'], 'media_type': row['media_type']}
    return snapshot


def summary_citations_valid(result, snapshot):
    ids = {segment['id'] for segment in snapshot['sources'][0]['data']['segments']}
    items = [item for key in ('requests', 'claims', 'commitments', 'needs_check') for item in result.get(key, [])]
    cited = [segment_id for item in items for segment_id in item['segment_ids']] + list(result.get('unclear_segment_ids', []))
    return all(item['segment_ids'] for item in items) and all(segment_id in ids for segment_id in cited)
