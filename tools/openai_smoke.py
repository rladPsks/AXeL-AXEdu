"""Optional live smoke test using only isolated fictional inputs. Requires local credentials."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.openai_provider import create_registry
from backend.seed import seed
from backend.worker import Worker


def main():
    registry=create_registry()
    if 'REVIEW_SUPPORT' not in registry.handlers:
        print('OPENAI_API_KEY와 OPENAI_MODEL을 로컬 환경변수로 설정하세요. 외부 호출을 하지 않았습니다.')
        return 1
    root=Path('.test-tmp')
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openai-smoke-',dir=root) as directory:
        path=Path(directory)/'fictional.sqlite3'
        credentials=seed(path)
        app=create_app(path,agent_registry=registry)
        headers={'Authorization':'Bearer '+credentials['tokens']['admin'],'Idempotency-Key':'fictional-live-start'}
        with TestClient(app) as client:
            started=client.post('/api/cases/demo-case/agent-runs',headers=headers,json={
                'expected_version':1,'purpose':'REVIEW_SUPPORT',
                'input_refs':[{'resource_type':'CASE','resource_id':'demo-case','version':1}]})
            if started.status_code!=202:
                print('가상 실행을 시작하지 못했습니다.');return 1
            run_id=started.json()['run_id']
            Worker(app.state.db,registry).process_once()
            result=client.get('/api/agent-runs/'+run_id,headers=headers).json()
            if result['status']!='WAITING_REVIEW':
                print('실제 모델 점검 미완료:',result['status'],(result['error'] or {}).get('code'))
                return 1
            review=client.post('/api/agent-runs/'+run_id+'/review',headers={**headers,'Idempotency-Key':'fictional-review'},
                               json={'expected_version':1,'decision':'ACCEPT','reason':'가상 입력으로 구조화 응답 경로 점검'})
            if review.status_code!=200:
                print('모델 응답 이후 검토 저장을 확인하지 못했습니다.');return 1
            print('가상 사건의 실제 OpenAI 생성·구조화 응답·검토 저장 확인. 실제 기록은 처리하지 않았습니다.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
