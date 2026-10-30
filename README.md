# AXeL-AXEdu

A·B 통합 시 [확정 계약 v1.2](docs/개발자_AB_통합계약_확정_v1.md)을 우선 적용합니다. React 공통 구조·레이아웃·API 클라이언트도 B 담당입니다. B 기준 충돌 방지 규칙과 현재 구현·후속 구현 계약을 구분한 문서입니다.

최신 개발: 비공개 파일·보호자 관계 검사·공통 AI worker·OpenAI Responses adapter와 화면을 추가했습니다. **[파일·보호자·OpenAI 연결 안내](docs/B_파일_보호자_AI_연결안내.md)**를 확인하세요. 실제 모델 호출은 로컬 OPENAI_API_KEY/OPENAI_MODEL 설정 후 검증해야 합니다. 일정·알림·반복 비교·동의 녹취·대시보드는 후속 개발입니다.

개발 갱신: 공통 서버 서비스·정식 migration·React 공통 기반·교사 업무/지원/인계 화면을 추가했습니다. **현재 실행 및 A 연결은 [B 공통 기반 연결 안내](docs/B_공통기반_연결안내.md)를 참고하세요.** 아래 첫 서버 안내의 후속 작업 중 공통 서비스·migration·첫 React 화면은 구현되었습니다. AI·실제 인증·파일·알림·녹취·대시보드 등은 계속 개발합니다.

학교 민원 에이전트 개발자 B의 첫 서버 구현입니다. Python 3.12 기준, FastAPI·SQLite를 초기 선택으로 사용합니다. 기술 선택은 팀 합의에 따라 조정할 수 있습니다.

## 실행 (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

시드 명령은 빈 개발 DB에 가상 사건 `demo-case`와 개발 계정을 생성하고 무작위 Bearer 토큰을 출력합니다. 토큰 원문은 DB에 저장하지 않으며 8시간 후 만료됩니다. 기관 인증·로그인 기능은 아직 구현하지 않았습니다. 기본 서버는 시드나 세션을 자동 생성하지 않습니다. 기본 DB는 `data/private/dev.sqlite3`이며 `SCHOOL_AGENT_DB`로 변경합니다. 별도 DB 시드에는 `--db 경로`를 사용합니다.

API 문서: <http://127.0.0.1:8000/docs>. 요청 헤더에 `Authorization: Bearer <시드에서 받은 토큰>`을 넣습니다. 변경 요청에는 `Idempotency-Key`와 본문의 `expected_version`도 필요합니다. API 연결 예시는 [계약 문서](docs/b-first-slice.md)를 참고하세요.

API 계약 재생성: `.\.venv\Scripts\python.exe -m backend.export_contract`. 모든 설치 버전을 재현하려면 `requirements-lock.txt`를 설치합니다. 이 파일은 Python 3.12·Windows에서 검증한 개발 환경의 전체 의존성입니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

학교·사건 권한, 중복 요청, 동시 수정 충돌, 총괄 인수 수락, 지원 수신 확인, 종결 가드, 재시작 후 저장, 감사 실패 시 트랜잭션 취소를 검증합니다.

## 구현 범위

- 세션 검사·학교 소속·사건 참여 기반 접근 검사
- 교사 업무 생성·확인·완료 회신
- 학교 지원 요청·지정 관리자 확인·조치·결과
- 총괄 인계 요청·지정 인수자 수락
- 남은 업무·지원·인계 확인 후 종결, 사유를 남기는 재개
- 서버 UTC 시각·추가형 감사 이력·사건 버전·중복 방지

전체 제품이나 B-01~04의 완료를 뜻하지 않습니다. React 화면, 실제 인증, 권한 세분화·보호자 관계 검사, AI 실행기/공급자·복구, 비공개 파일 다운로드, 반복 비교, 알림 전달·대체자 설정, 녹취, 대시보드, 정식 마이그레이션은 후속 작업입니다. `URGENT` 지원도 현재는 DB 기록만 생성하며 관리자에게 실시간 알림을 보내지 않습니다.

A의 접수·분류·근거·답변·번역·보고서 기능은 포함하지 않았습니다. 사건 테이블과 조회는 첫 연결을 위한 최소 계약이며, 현재 종결 검사는 B가 구현한 세 테이블만 확인합니다. A의 답변 전달·승인·후속 업무 조건을 연결하기 전에는 제품 전체의 종결 조건을 충족하지 않습니다. [작업 경계와 다음 순서](docs/b-first-slice.md)를 참고하세요.
