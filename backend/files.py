"""Private, bounded binary uploads stored atomically with domain metadata in SQLite.

No filesystem path or public static URL is derived from the original filename.
This development store can later be replaced behind the same file_id API.
"""
import hashlib
import os
from pathlib import PurePath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import StringConstraints
from typing_extensions import Annotated

from .access import accessible_case, authenticate, fail
from .commands import mutate
from .db import now, uid
from .models import Command

router = APIRouter()
EXTENSIONS = ['.txt', '.md', '.pdf', '.png', '.jpg', '.jpeg', '.wav', '.mp3', '.ogg']
Filename = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Category = Literal['EVIDENCE', 'SOURCE', 'AUDIO', 'EXPORT']
Visibility = Literal['CASE', 'RESTRICTED']
META = 'id, case_id, uploader_id, filename, category, visibility, media_type, size_bytes, sha256, created_at'


class FileCommand(Command):
    filename: Filename
    category: Category
    visibility: Visibility
    sha256: str


def upload_limit():
    value = int(os.getenv('SCHOOL_AGENT_MAX_FILE_BYTES', str(10 * 1024 * 1024)))
    if value < 1:
        raise ValueError('SCHOOL_AGENT_MAX_FILE_BYTES must be positive')
    return value


def media_type(filename, content, category):
    if any(ord(c) < 32 or ord(c) == 127 for c in filename) or '/' in filename or '\\' in filename:
        fail(422, 'INVALID_FILENAME', '경로와 제어 문자가 없는 파일명을 사용하세요.')
    suffix = PurePath(filename).suffix.lower()
    detected = None
    if suffix in {'.txt', '.md'}:
        try:
            text = content.decode('utf-8-sig')
            if '\x00' not in text:
                detected = 'text/plain'
        except UnicodeDecodeError:
            pass
    elif suffix == '.pdf' and content.startswith(b'%PDF-'):
        detected = 'application/pdf'
    elif suffix == '.png' and content.startswith(b'\x89PNG\r\n\x1a\n'):
        detected = 'image/png'
    elif suffix in {'.jpg', '.jpeg'} and content.startswith(b'\xff\xd8\xff'):
        detected = 'image/jpeg'
    elif suffix == '.wav' and content[:4] == b'RIFF' and content[8:12] == b'WAVE':
        detected = 'audio/wav'
    elif suffix == '.mp3' and (content.startswith(b'ID3') or (len(content) > 1 and content[0] == 255 and content[1] & 224 == 224)):
        detected = 'audio/mpeg'
    elif suffix == '.ogg' and content.startswith(b'OggS'):
        detected = 'audio/ogg'
    if not detected or (category == 'AUDIO' and not detected.startswith('audio/')):
        fail(422, 'UNSUPPORTED_FILE', '허용된 확장자와 파일 형식을 확인하세요.')
    return detected


def file_access(db, actor, file_id):
    row = db.execute(f'SELECT {META} FROM private_files WHERE id=? AND case_id IN '
                     '(SELECT id FROM cases WHERE school_id=?)', (file_id,actor['school_id'])).fetchone()
    if row is None:
        fail(404, 'FILE_NOT_FOUND', '파일을 찾을 수 없습니다.')
    accessible_case(db, actor, row['case_id'])
    if row['visibility'] == 'RESTRICTED' and actor['role'] != 'ADMIN' and row['uploader_id'] != actor['user_id']:
        fail(403, 'FILE_FORBIDDEN', '이 파일을 열람할 권한이 없습니다.')
    return row


@router.get('/api/file-policy')
def file_policy(request: Request):
    with request.app.state.db.transaction() as db:
        authenticate(db, request)
    return {'max_bytes': request.app.state.max_file_bytes, 'extensions': EXTENSIONS}


@router.get('/api/cases/{case_id}/files')
def list_files(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        return [dict(r) for r in db.execute(
            f'SELECT {META} FROM private_files WHERE case_id=? '
            "AND (visibility='CASE' OR uploader_id=? OR ?='ADMIN') ORDER BY created_at, id",
            (case_id, actor['user_id'], actor['role']))]


@router.post('/api/cases/{case_id}/files', status_code=201, openapi_extra={
    'requestBody': {'required': True, 'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}}}
})
async def upload_file(case_id: str, request: Request, filename: Filename,
                      expected_version: int = Query(ge=1), category: Category = 'EVIDENCE',
                      visibility: Visibility = 'CASE'):
    # Authenticate before reading any bytes, then recheck in mutate after the upload.
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
    maximum = request.app.state.max_file_bytes
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum:
            fail(413, 'FILE_TOO_LARGE', '업로드 가능한 파일 크기를 초과했습니다.', max_bytes=maximum)
        content.extend(chunk)
    if not content:
        fail(422, 'EMPTY_FILE', '빈 파일은 업로드할 수 없습니다.')
    content = bytes(content)
    mime = media_type(filename, content, category)
    body = FileCommand(expected_version=expected_version, filename=filename, category=category,
                       visibility=visibility, sha256=hashlib.sha256(content).hexdigest())

    def operation(db, actor, case):
        file_id = uid()
        db.execute('INSERT INTO private_files(id, case_id, uploader_id, filename, category, visibility, '
                   'media_type, size_bytes, sha256, content, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (file_id, case_id, actor['user_id'], filename, category, visibility, mime,
                    len(content), body.sha256, content, now()))
        return {'file_id': file_id, 'filename': filename, 'size_bytes': len(content),
                'sha256': body.sha256, 'media_type': mime, 'visibility': visibility}
    return mutate(request, case_id, body, 'FILE_UPLOADED', operation, 201)


@router.get('/api/files/{file_id}/download')
def download_file(file_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        metadata = file_access(db, actor, file_id)
        content = db.execute('SELECT content FROM private_files WHERE id=?', (file_id,)).fetchone()[0]
        db.execute('INSERT INTO file_access_events(id, file_id, actor_id, created_at) VALUES (?,?,?,?)',
                   (uid(), file_id, actor['user_id'], now()))
    return Response(content, media_type=metadata['media_type'], headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(metadata['filename'], safe=''),
        'X-Content-Type-Options': 'nosniff',
    })
