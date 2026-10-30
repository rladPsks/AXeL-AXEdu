"""Single-process durable worker with leases, fenced results and bounded retries."""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from .access import DomainError
from .agents import ProviderFailure, event, run_access
from .db import Database, now, uid


class Worker:
    def __init__(self, database, registry, lease_seconds=60, clock=time.time):
        if lease_seconds < 1:
            raise ValueError('Lease must be at least one second')
        self.database, self.registry = database, registry
        self.lease_seconds, self.clock = lease_seconds, clock

    def _claim(self):
        with self.database.transaction() as db:
            exhausted = db.execute("SELECT id FROM agent_runs WHERE status='RUNNING' AND lease_until<=? AND attempts>=max_attempts",(self.clock(),)).fetchall()
            for row in exhausted:
                error = json.dumps({'code':'WORKER_INTERRUPTED','message':'중단 복구 재시도 한도를 초과했습니다.','retryable':True},ensure_ascii=False)
                db.execute("UPDATE agent_runs SET status='FAILED',step='failed',error=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",(error,now(),row['id']))
                event(db,row['id'],'FAILED','retry_limit','worker')
            row = db.execute("SELECT * FROM agent_runs WHERE attempts<max_attempts AND "
                             "((status='QUEUED' AND next_attempt_at<=?) OR (status='RUNNING' AND lease_until<=?)) "
                             "ORDER BY created_at,id LIMIT 1",(self.clock(),self.clock())).fetchone()
            if row is None:
                return None
            token = uid()
            db.execute("UPDATE agent_runs SET status='RUNNING',step='generating',lease_token=?,lease_until=?,attempts=attempts+1,error=NULL,updated_at=? WHERE id=?",
                       (token,self.clock()+self.lease_seconds,now(),row['id']))
            event(db,row['id'],'RUNNING','generating','worker')
            return dict(db.execute('SELECT * FROM agent_runs WHERE id=?',(row['id'],)).fetchone())

    def _access(self, db, job):
        actor = db.execute('SELECT * FROM memberships WHERE user_id=? AND school_id=? AND active=1',
                           (job['requested_by'],job['school_id'])).fetchone()
        if actor is None:
            raise ProviderFailure('ACCESS_REVOKED','실행 요청자의 학교 권한이 변경되었습니다.')
        try:
            run_access(db,actor,job['id'])
        except DomainError:
            raise ProviderFailure('ACCESS_REVOKED','사건 또는 입력 자료의 접근 권한이 변경되었습니다.') from None
        from .recordings import consent_guard
        consent_guard(db,job)

    def _payload(self, db, job):
        if job['purpose']=='TRANSCRIBE_AUDIO':
            from .recordings import audio_payload
            return audio_payload(db,job)
        return json.loads(job['snapshot'])

    def _heartbeat(self, job):
        with self.database.transaction() as db:
            db.execute("UPDATE agent_runs SET lease_until=? WHERE id=? AND lease_token=? AND status='RUNNING'",
                       (self.clock()+self.lease_seconds,job['id'],job['lease_token']))

    def _finish(self, job, result=None, error=None):
        with self.database.transaction() as db:
            current = db.execute('SELECT * FROM agent_runs WHERE id=?',(job['id'],)).fetchone()
            if current['status'] != 'RUNNING' or current['lease_token'] != job['lease_token']:
                return
            try:
                self._access(db,job)
            except ProviderFailure as exc:
                error, result = exc, None
            if error:
                retry = error.retryable and current['attempts'] < current['max_attempts']
                status, step = ('QUEUED','retry_wait') if retry else ('FAILED','failed')
                saved_error = json.dumps({'code':error.code,'message':error.message,'retryable':error.retryable},ensure_ascii=False)
                next_at = self.clock()+min(60,2**current['attempts']) if retry else 0
                encoded = None
            else:
                handler = self.registry.handlers[job['purpose']]
                status = 'WAITING_REVIEW' if handler.requires_review else 'SUCCEEDED'
                step, saved_error, next_at = 'generated', None, 0
                encoded = json.dumps(result,ensure_ascii=False)
            db.execute('UPDATE agent_runs SET status=?,step=?,result=?,error=?,lease_token=NULL,lease_until=NULL,next_attempt_at=?,updated_at=? WHERE id=?',
                       (status,step,encoded,saved_error,next_at,now(),job['id']))
            event(db,job['id'],status,step,'worker',{'error_code':error.code} if error else None)

    def process_once(self):
        job = self._claim()
        if job is None:
            return False
        try:
            handler = self.registry.handlers.get(job['purpose'])
            if (handler is None or handler.version != job['handler_version'] or
                    handler.metadata != json.loads(job['provider_metadata'])):
                raise ProviderFailure('HANDLER_CHANGED','실행 설정이 변경되었습니다. 설정을 확인하고 다시 요청하세요.')
            with self.database.transaction() as db:
                self._access(db,job)
                payload = self._payload(db,job)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler.execute,payload)
                while True:
                    try:
                        raw = future.result(timeout=max(.2,self.lease_seconds/3))
                        break
                    except TimeoutError:
                        if future.done():
                            raise
                        self._heartbeat(job)
            result = handler.result_model.model_validate(raw).model_dump(mode='json')
            if job['purpose']=='COMPARE_CASES':
                from .comparison_review import ComparisonResult,validate_citations
                parsed=ComparisonResult.model_validate(result)
                sources=json.loads(job['snapshot'])['sources'][0]['data']['sources']
                if not validate_citations(parsed.findings,sources):
                    raise ProviderFailure('INVALID_CITATION','비교 입력에 없는 출처가 포함되어 재검토가 필요합니다.')
            if job['purpose']=='SUMMARIZE_TRANSCRIPT':
                from .recordings import summary_citations_valid
                if not summary_citations_valid(result,json.loads(job['snapshot'])):
                    raise ProviderFailure('INVALID_CITATION','전사에 없는 구간이 인용되어 재검토가 필요합니다.')
            if len(json.dumps(result,ensure_ascii=False).encode()) > 1024*1024:
                raise ProviderFailure('RESULT_TOO_LARGE','생성 결과 크기가 허용 범위를 초과했습니다.')
            self._finish(job,result=result)
        except ProviderFailure as exc:
            self._finish(job,error=exc)
        except Exception:
            self._finish(job,error=ProviderFailure('GENERATION_FAILED','생성 결과를 처리하지 못했습니다.'))
        return True


if __name__ == '__main__':
    from .runtime import build_registry
    parser = argparse.ArgumentParser()
    parser.add_argument('--db',default=os.getenv('SCHOOL_AGENT_DB','data/private/dev.sqlite3'))
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    worker = Worker(Database(args.db),build_registry())
    while True:
        worked = worker.process_once()
        if args.once:
            break
        if not worked:
            time.sleep(1)
