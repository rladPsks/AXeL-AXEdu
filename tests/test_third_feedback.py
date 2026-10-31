from fastapi.testclient import TestClient
from backend.main import create_app
from backend.seed import seed
from backend.db import Database


def test_batch_support_is_atomic_and_replay_safe(tmp_path):
    path = tmp_path / 'third.sqlite3'
    tokens = seed(path)['tokens']
    client = TestClient(create_app(path, inbox_worker=False))
    headers = {'Authorization': f"Bearer {tokens['deputy']}", 'Idempotency-Key': 'batch'}
    body = {'expected_version': 1, 'coordinator_ids': ['admin', 'teacher'], 'type': 'JOINT_RESPONSE', 'reason': '가상 공동 지원'}
    response = client.post('/api/cases/demo-case/support-requests', headers=headers, json=body)
    assert response.status_code == 201, response.text
    assert len(response.json()['support_requests']) == 2
    assert client.post('/api/cases/demo-case/support-requests', headers=headers, json=body).json() == response.json()
    with Database(path).transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM support_requests').fetchone()[0] == 2
        assert db.execute("SELECT owner_id FROM cases WHERE id='demo-case'").fetchone()[0] == 'admin'
    teacher_request = next(r for r in response.json()['support_requests'] if r['coordinator_id'] == 'teacher')
    ack = client.patch('/api/support-requests/' + teacher_request['support_request_id'], headers={'Authorization': f"Bearer {tokens['teacher']}", 'Idempotency-Key': 'ack'}, json={'expected_version': 2, 'status': 'ACKNOWLEDGED'})
    assert ack.status_code == 200, ack.text
    failed = client.post('/api/cases/demo-case/support-requests', headers={**headers, 'Idempotency-Key': 'invalid-batch'}, json={**body, 'expected_version': 3, 'coordinator_ids': ['admin', 'other-admin']})
    assert failed.status_code == 422
    with Database(path).transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM support_requests').fetchone()[0] == 2
