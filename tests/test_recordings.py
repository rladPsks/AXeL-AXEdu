import json
import sqlite3
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.agents import Handler, ProviderFailure, Registry
from backend.db import now
from backend.main import create_app
from backend.openai_provider import TranscriptSummary
from backend.seed import seed
from backend.speech import AzureSpeechAdapter, speech_handler
from backend.worker import Worker

WAV = b'RIFF$\x00\x00\x00WAVEfmt ' + b'\x00' * 32
STT = {'durationMilliseconds': 5000, 'phrases': [
    {'offsetMilliseconds': 0, 'durationMilliseconds': 2000, 'text': '안녕하세요, 담임입니다.', 'speaker': 1, 'locale': 'ko-KR', 'confidence': 0.9},
    {'offsetMilliseconds': 2200, 'durationMilliseconds': 2800, 'text': '내일 상담이 가능한가요?', 'speaker': 2, 'locale': 'ko-KR', 'confidence': 0.8}]}
SUMMARY = {'requests': [{'text': '상담 가능 여부를 묻는다', 'segment_ids': ['seg-0002']}], 'claims': [],
           'commitments': [], 'needs_check': [], 'unclear_segment_ids': []}


def auth(creds, user='admin'):
    return {'Authorization': 'Bearer ' + creds['tokens'][user], 'Idempotency-Key': str(uuid4())}


@pytest.fixture
def env(tmp_path):
    path = tmp_path / 'recordings.sqlite3'
    creds = seed(path)
    calls = []

    def azure(request):
        calls.append(request)
        return httpx.Response(200, json=STT)
    registry = Registry()
    registry.register(speech_handler(key='test-not-a-key', region='koreacentral',
                                     client=httpx.Client(transport=httpx.MockTransport(azure))))
    registry.register(Handler('SUMMARIZE_TRANSCRIPT', lambda snapshot: SUMMARY, TranscriptSummary, 'summary-test-v1',
                              generation_mode='RULE'))
    app = create_app(path, agent_registry=registry)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, creds, app, registry, calls, path


def version(client, creds):
    return client.get('/api/cases/demo-case', headers=auth(creds)).json()['version']


def upload(client, creds, user='admin', name='call.wav', visibility='CASE'):
    response = client.post(f'/api/cases/demo-case/files?filename={name}&category=AUDIO&visibility={visibility}'
                           f'&expected_version={version(client, creds)}',
                           headers={**auth(creds, user), 'Content-Type': 'application/octet-stream'}, content=WAV)
    assert response.status_code == 201, response.text
    return response.json()['file_id']


def consent(client, creds, file_id, user='admin'):
    return client.post('/api/cases/demo-case/audio-consents', headers=auth(creds, user), json={
        'expected_version': version(client, creds), 'file_id': file_id,
        'subject': '[가상] 통화 상대 구두 동의', 'scope': '전사·요약'})


def revoke(client, creds, consent_id, reason='[가상] 상대가 동의를 철회함'):
    return client.post(f'/api/audio-consents/{consent_id}/revoke', headers=auth(creds), json={
        'expected_version': version(client, creds), 'reason': reason})


def start(client, creds, purpose, ref_type, ref_id, ref_version=1):
    return client.post('/api/cases/demo-case/agent-runs', headers=auth(creds), json={
        'expected_version': version(client, creds), 'purpose': purpose,
        'input_refs': [{'resource_type': ref_type, 'resource_id': ref_id, 'version': ref_version}]})


def run_state(client, creds, run_id):
    return client.get(f'/api/agent-runs/{run_id}', headers=auth(creds)).json()


def review(client, creds, run_id, decision='ACCEPT'):
    return client.post(f'/api/agent-runs/{run_id}/review', headers=auth(creds), json={
        'expected_version': version(client, creds), 'decision': decision, 'reason': '[가상] 음성과 대조함'})


def transcribe(client, creds, app, registry, file_id, accept=True):
    run_id = start(client, creds, 'TRANSCRIBE_AUDIO', 'FILE', file_id).json()['run_id']
    assert Worker(app.state.db, registry).process_once()
    if accept:
        assert review(client, creds, run_id).status_code == 200
    return run_id


def save_original(client, creds, file_id, run_id):
    return client.post('/api/cases/demo-case/transcripts', headers=auth(creds), json={
        'expected_version': version(client, creds), 'file_id': file_id, 'run_id': run_id})


def correct(client, creds, file_id, texts, reason='[가상] 음성 대조 후 정정'):
    edits = [{'id': f'seg-{i:04d}', 'text': text, 'speaker': speaker} for i, (text, speaker) in enumerate(texts, 1)]
    return client.post('/api/cases/demo-case/transcripts', headers=auth(creds), json={
        'expected_version': version(client, creds), 'file_id': file_id, 'edits': edits, 'reason': reason})


def test_audio_without_consent_is_rejected_and_never_sent(env):
    client, creds, app, registry, calls, _ = env
    file_id = upload(client, creds)
    response = start(client, creds, 'TRANSCRIBE_AUDIO', 'FILE', file_id)
    assert response.status_code == 422 and response.json()['code'] == 'AUDIO_CONSENT_REQUIRED'
    assert not Worker(app.state.db, registry).process_once() and calls == []
    # Non-audio files and other purposes cannot be used to reach the provider either.
    evidence = client.post(f'/api/cases/demo-case/files?filename=a.txt&expected_version={version(client, creds)}',
                           headers={**auth(creds), 'Content-Type': 'application/octet-stream'}, content=b'text').json()['file_id']
    assert start(client, creds, 'TRANSCRIBE_AUDIO', 'FILE', evidence).json()['code'] == 'AUDIO_FILE_REQUIRED'
    registry.handlers['REVIEW_SUPPORT'] = Handler('REVIEW_SUPPORT', lambda s: {}, TranscriptSummary, 'x', generation_mode='RULE')
    other = start(client, creds, 'REVIEW_SUPPORT', 'FILE', file_id)
    assert other.status_code == 422 and other.json()['code'] == 'AUDIO_CONSENT_REQUIRED'
    assert calls == []


def test_consented_audio_flows_from_transcription_to_preserved_corrections(env):
    client, creds, app, registry, calls, path = env
    file_id = upload(client, creds)
    assert consent(client, creds, file_id).status_code == 201
    assert consent(client, creds, file_id).json()['code'] == 'CONSENT_EXISTS'
    run_id = start(client, creds, 'TRANSCRIBE_AUDIO', 'FILE', file_id).json()['run_id']
    assert Worker(app.state.db, registry).process_once()
    run = run_state(client, creds, run_id)
    assert run['status'] == 'WAITING_REVIEW' and len(calls) == 1
    assert [s['speaker'] for s in run['result']['segments']] == ['화자 1', '화자 2']
    assert run['result']['segments'][1]['start'] == 2.2 and run['result']['segments'][1]['end'] == 5.0
    request = calls[0]
    assert request.url.path.endswith('/speechtotext/transcriptions:transcribe')
    assert request.headers['Ocp-Apim-Subscription-Key'] == 'test-not-a-key'
    body = request.read()
    assert b'ko-KR' in body and b'diarization' in body and WAV in body
    # The stored run snapshot never contains the recording itself.
    with app.state.db.transaction() as db:
        assert 'RIFF' not in db.execute('SELECT snapshot FROM agent_runs').fetchone()[0]
    assert save_original(client, creds, file_id, run_id).status_code == 409  # still waiting for human review
    assert review(client, creds, run_id).status_code == 200
    first = save_original(client, creds, file_id, run_id)
    assert first.status_code == 201 and first.json()['revision'] == 1
    assert save_original(client, creds, file_id, run_id).json()['code'] == 'TRANSCRIPT_EXISTS'
    fixed = correct(client, creds, file_id, [('안녕하세요, 담임교사입니다.', '교사'), ('내일 상담이 가능한가요?', '화자 2')])
    assert fixed.status_code == 201 and fixed.json()['revision'] == 2
    listed = client.get(f'/api/cases/demo-case/transcripts?file_id={file_id}', headers=auth(creds)).json()
    assert [t['revision'] for t in listed] == [1, 2]
    assert listed[0]['segments'][0]['text'] == '안녕하세요, 담임입니다.' and listed[0]['segments'][0]['speaker'] == '화자 1'
    assert listed[1]['segments'][0]['text'] == '안녕하세요, 담임교사입니다.' and listed[1]['reason']
    assert [s['start'] for s in listed[1]['segments']] == [s['start'] for s in listed[0]['segments']]
    same = correct(client, creds, file_id, [('안녕하세요, 담임교사입니다.', '교사'), ('내일 상담이 가능한가요?', '화자 2')])
    assert same.status_code == 422 and same.json()['code'] == 'NO_CHANGE'
    short = client.post('/api/cases/demo-case/transcripts', headers=auth(creds), json={
        'expected_version': version(client, creds), 'file_id': file_id, 'reason': '[가상]',
        'edits': [{'id': 'seg-0001', 'text': '일부만', 'speaker': '교사'}]})
    assert short.status_code == 422 and short.json()['code'] == 'SEGMENT_MISMATCH'
    db = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE transcripts SET segments='[]'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('DELETE FROM transcripts')
    db.close()


def test_revoking_consent_after_queueing_blocks_the_provider_call(env):
    client, creds, app, registry, calls, _ = env
    file_id = upload(client, creds)
    consent_id = consent(client, creds, file_id).json()['consent_id']
    run_id = start(client, creds, 'TRANSCRIBE_AUDIO', 'FILE', file_id).json()['run_id']
    assert revoke(client, creds, consent_id).status_code == 200
    assert revoke(client, creds, consent_id, '다시').json()['code'] == 'CONSENT_ALREADY_REVOKED'
    assert Worker(app.state.db, registry).process_once()
    run = run_state(client, creds, run_id)
    assert run['status'] == 'FAILED' and run['error']['code'] == 'AUDIO_CONSENT_REVOKED' and not run['error']['retryable']
    assert calls == []
    # A fresh consent is a new, explicit decision and re-enables processing.
    assert consent(client, creds, file_id).status_code == 201


def test_consent_revoked_while_provider_runs_discards_the_result(env):
    client, creds, app, registry, calls, _ = env
    file_id = upload(client, creds)
    consent_id = consent(client, creds, file_id).json()['consent_id']
    run_id = start(client, creds, 'TRANSCRIBE_AUDIO', 'FILE', file_id).json()['run_id']
    original = registry.handlers['TRANSCRIBE_AUDIO']

    def revoke_during_call(snapshot):
        with app.state.db.transaction() as db:
            db.execute("UPDATE audio_consents SET revoked_at=?,revoked_by='admin' WHERE id=?", (now(), consent_id))
        return original.execute(snapshot)
    registry.handlers['TRANSCRIBE_AUDIO'] = Handler('TRANSCRIBE_AUDIO', revoke_during_call, original.result_model,
                                                    original.version, metadata=original.metadata)
    assert Worker(app.state.db, registry).process_once()
    run = run_state(client, creds, run_id)
    assert run['status'] == 'FAILED' and run['result'] is None and run['error']['code'] == 'AUDIO_CONSENT_REVOKED'


def test_original_transcript_needs_an_accepted_run_for_the_same_file(env):
    client, creds, app, registry, calls, _ = env
    first, second = upload(client, creds), upload(client, creds, name='other.wav')
    assert consent(client, creds, first).status_code == 201 and consent(client, creds, second).status_code == 201
    accepted = transcribe(client, creds, app, registry, first)
    mismatch = save_original(client, creds, second, accepted)
    assert mismatch.status_code == 422 and mismatch.json()['code'] == 'RUN_FILE_MISMATCH'
    pending = transcribe(client, creds, app, registry, second, accept=False)
    assert save_original(client, creds, second, pending).json()['code'] == 'AGENT_RESULT_NOT_READY'
    both = client.post('/api/cases/demo-case/transcripts', headers=auth(creds), json={
        'expected_version': version(client, creds), 'file_id': first, 'run_id': accepted, 'reason': '[가상]',
        'edits': [{'id': 'seg-0001', 'text': '둘 다', 'speaker': '교사'}]})
    assert both.status_code == 422
    assert correct(client, creds, first, [('먼저 원본을 저장해야 함', '교사')] * 2).json()['code'] == 'TRANSCRIPT_REQUIRED'


def test_summary_needs_latest_consented_transcript_and_real_citations(env):
    client, creds, app, registry, calls, _ = env
    file_id = upload(client, creds)
    consent_id = consent(client, creds, file_id).json()['consent_id']
    run_id = transcribe(client, creds, app, registry, file_id)
    transcript_id = save_original(client, creds, file_id, run_id).json()['transcript_id']
    ok = start(client, creds, 'SUMMARIZE_TRANSCRIPT', 'TRANSCRIPT', transcript_id)
    assert ok.status_code == 202
    assert Worker(app.state.db, registry).process_once()
    assert run_state(client, creds, ok.json()['run_id'])['status'] == 'WAITING_REVIEW'
    # A summary may only cite segments that exist in the transcript.
    bad = {**SUMMARY, 'claims': [{'text': '없는 구간', 'segment_ids': ['seg-9999']}]}
    registry.handlers['SUMMARIZE_TRANSCRIPT'] = Handler('SUMMARIZE_TRANSCRIPT', lambda s: bad, TranscriptSummary,
                                                        'summary-bad-v1', generation_mode='RULE')
    invented = start(client, creds, 'SUMMARIZE_TRANSCRIPT', 'TRANSCRIPT', transcript_id).json()['run_id']
    assert Worker(app.state.db, registry).process_once()
    failed = run_state(client, creds, invented)
    assert failed['status'] == 'FAILED' and failed['error']['code'] == 'INVALID_CITATION'
    # Summaries of an older revision are refused once a correction exists.
    assert correct(client, creds, file_id, [('정정한 첫 문장', '교사'), ('내일 상담이 가능한가요?', '화자 2')]).status_code == 201
    stale = start(client, creds, 'SUMMARIZE_TRANSCRIPT', 'TRANSCRIPT', transcript_id)
    assert stale.status_code == 409 and stale.json()['code'] == 'INPUT_VERSION_CONFLICT'
    wrong_input = start(client, creds, 'SUMMARIZE_TRANSCRIPT', 'FILE', file_id)
    assert wrong_input.status_code == 422 and wrong_input.json()['code'] == 'TRANSCRIPT_INPUT_REQUIRED'
    # Once consent is withdrawn nothing derived from the recording can be processed.
    assert revoke(client, creds, consent_id, '[가상] 철회').status_code == 200
    latest = client.get(f'/api/cases/demo-case/transcripts?file_id={file_id}', headers=auth(creds)).json()[-1]
    blocked = start(client, creds, 'SUMMARIZE_TRANSCRIPT', 'TRANSCRIPT', latest['id'], 2)
    assert blocked.status_code == 409 and blocked.json()['code'] == 'AUDIO_CONSENT_REQUIRED'
    assert save_original(client, creds, file_id, run_id).status_code == 409


def test_restricted_recordings_stay_hidden_from_other_participants(env):
    client, creds, *_ = env
    file_id = upload(client, creds, visibility='RESTRICTED')
    assert consent(client, creds, file_id).status_code == 201
    assert client.get('/api/cases/demo-case/audio-consents', headers=auth(creds, 'teacher')).json() == []
    assert len(client.get('/api/cases/demo-case/audio-consents', headers=auth(creds)).json()) == 1
    denied = client.get(f'/api/cases/demo-case/transcripts?file_id={file_id}', headers=auth(creds, 'teacher'))
    assert denied.status_code == 403
    assert consent(client, creds, file_id, 'teacher').status_code == 403
    assert client.get('/api/cases/demo-case/audio-consents').status_code == 401


def transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def azure_audio():
    return {'audio': {'filename': 'a.wav', 'bytes': b'abc', 'media_type': 'audio/wav'}}


@pytest.mark.parametrize('status,code,retryable', [(401, 'PROVIDER_AUTH', False), (403, 'PROVIDER_AUTH', False),
                                                  (429, 'PROVIDER_RATE_LIMIT', True), (503, 'PROVIDER_UNAVAILABLE', True),
                                                  (400, 'STT_REQUEST_REJECTED', False)])
def test_azure_errors_are_classified_without_echoing_provider_text(status, code, retryable):
    secret = '비밀 통화 내용 SECRET-KEY-VALUE'
    adapter = AzureSpeechAdapter('SECRET-KEY-VALUE', 'https://koreacentral.api.cognitive.microsoft.com',
                                 client=transport(lambda r: httpx.Response(status, text=secret)))
    with pytest.raises(ProviderFailure) as caught:
        adapter.transcribe(azure_audio())
    assert caught.value.code == code and caught.value.retryable is retryable
    assert 'SECRET' not in caught.value.message and '비밀' not in caught.value.message


def test_azure_connection_empty_and_speaker_handling():
    def broken(request):
        raise httpx.ConnectError('boom')
    with pytest.raises(ProviderFailure) as caught:
        AzureSpeechAdapter('k', 'https://x.cognitiveservices.azure.com', client=transport(broken)).transcribe(azure_audio())
    assert caught.value.code == 'PROVIDER_CONNECTION' and caught.value.retryable
    with pytest.raises(ProviderFailure) as empty:
        AzureSpeechAdapter('k', 'https://x.cognitiveservices.azure.com',
                           client=transport(lambda r: httpx.Response(200, json={'phrases': [{'text': '  '}]}))).transcribe(azure_audio())
    assert empty.value.code == 'EMPTY_TRANSCRIPT'
    seen = []

    def speakerless(request):
        seen.append(request.read())
        return httpx.Response(200, json={'phrases': [{'offsetMilliseconds': 10, 'durationMilliseconds': 90, 'text': '네'}]})
    result = AzureSpeechAdapter('k', 'https://x.cognitiveservices.azure.com', diarization=False,
                                client=transport(speakerless)).transcribe(azure_audio())
    assert result['segments'][0]['speaker'] == '미상' and result['language'] == 'ko-KR'
    assert b'diarization' not in seen[0]
    with pytest.raises(ValueError):
        AzureSpeechAdapter('k', 'http://insecure.example')


def test_speech_handler_is_only_registered_when_configured(monkeypatch):
    for name in ('AZURE_SPEECH_KEY', 'AZURE_SPEECH_ENDPOINT', 'AZURE_SPEECH_REGION'):
        monkeypatch.delenv(name, raising=False)
    assert speech_handler() is None
    assert speech_handler(key='k') is None
    handler = speech_handler(key='secret-key-value', region='koreacentral')
    assert handler.purpose == 'TRANSCRIBE_AUDIO' and handler.metadata['provider'] == 'azure-speech'
    assert 'secret-key-value' not in json.dumps(handler.metadata)
    with pytest.raises(ValueError):
        speech_handler(key='k', region='evil.example.com/x')
