# AXeL — 학교 민원 대응 AI Agent

> **민원이 교사에게 닿기 전에, AXeL이 먼저 일합니다.**

AXeL은 학교 대표 창구로 들어온 민원을 단순히 교사에게 전달하지 않습니다.  
LLM이 민원의 핵심 요구와 긴급도를 구조화하고, **공식 문서 RAG · 과거 민원 이력 · 학교 업무분장**을 함께 확인해 학교 차원의 대응계획을 준비합니다. 필요한 사실만 담당 교직원에게 요청하고, 회신이 모이면 Agent가 다시 검토해 답변 초안과 지원 방향을 제안합니다.

**Live Demo:** https://axel-axedu.vercel.app  
**Demo data only:** 공개 배포본은 가상 학교·가상 민원으로 구성된 시연 환경입니다.

---

## Why — 민원 창구는 생겼지만, 교사는 여전히 혼자일 수 있습니다

학교 대표 창구가 있어도 민원의 성격을 판단하고 담당을 배분할 사람이 부족하면 민원은 다시 담임·업무담당 교사에게 돌아갑니다.

- **누가 처리할지 판단이 어렵습니다.** 정보 문의인지, 사실확인인지, 관리자 검토가 필요한지 먼저 구분해야 합니다.
- **근거가 흩어져 있습니다.** 학교민원 처리 매뉴얼, 법령, 정책자료와 학교 업무분장을 함께 찾아야 합니다.
- **교사가 민원 처리자가 되기 쉽습니다.** 사실을 가장 잘 아는 교사에게 확인뿐 아니라 보호자 응대 책임까지 집중될 수 있습니다.

AXeL의 목표는 **교사를 AI로 대체하는 것**이 아니라, 민원과 교사 사이에 **학교 차원의 AI 대응 계층**을 만드는 것입니다.

---

## How — AXeL Agent Workflow

```text
민원 접수
   ↓
LLM TRIAGE
유형 · 긴급도 · 핵심 요구 · 사실확인 필요성
   ↓
┌───────────────┬────────────────┬────────────────┐
│ Official RAG  │ History Agent  │ School Duty    │
│ 공식 근거 검색 │ 과거 사건 비교   │ 학교 업무분장 검색 │
└───────────────┴────────────────┴────────────────┘
   ↓
Action Router
담당 · 협조 · 승인 · 필요한 업무 결정
   ↓
필요한 사람에게만 FACT CHECK / SUPPORT TASK
   ↓
교직원 회신
   ↓
Agent Re-planning
FACT / CLAIM / UNVERIFIED 재구성
   ↓
Response Agent → Deterministic Validator
   ↓
Human Review → 학교 공식 답변 / 지원
```

### 핵심 원칙

> **사건 총괄과 업무 수행자를 분리합니다.**

담임교사가 사실확인 Task를 수행하더라도 사건 총괄과 보호자 답변 책임은 학교 대응체계에 유지됩니다.  
AI의 답변·지원 제안도 자동 발송·자동 이관되지 않으며 학교 권한자가 최종 확인합니다.

---

## Key Features

| 기능 | AXeL에서 하는 일 |
|---|---|
| **LLM Triage** | 민원 원문에서 유형·긴급도·핵심 요구·사실확인 필요성을 Structured Output으로 추출 |
| **Official RAG** | 학교민원 처리 매뉴얼·법령·교육부 정책자료를 검색해 문서명·페이지와 함께 근거 제공 |
| **History Agent** | 과거 사건과 비교해 미해결 연결, 후속 민원, 반복 검토 후보를 구분 |
| **School Duty Tool** | 학교 업무분장표에서 1순위 담당·협조자·승인자·대체 담당을 탐색 |
| **Action Router** | 분석 결과를 FACT_CHECK, ADMIN_REVIEW, HISTORY_REVIEW 등의 실제 업무로 변환 |
| **Agent Re-planning** | 교직원 회신이 들어오면 사건 기록과 근거를 다시 읽어 다음 대응을 재계획 |
| **Response + Validator** | 보호자 답변 초안을 만들고 책임 인정·근거 없는 법령·위험한 직접 연락 등을 코드 규칙으로 재검사 |
| **Multilingual / Support** | 외국어 민원을 내부 한국어 workflow로 처리하고, 필요 시 지원·이관 보고서 초안을 준비 |

---

## RAG는 어떻게 동작하나요?

**RAG(Retrieval-Augmented Generation)** 는 LLM이 기억만으로 답하지 않고, 질문과 관련된 공식 문서를 먼저 검색해 그 근거를 함께 사용하도록 하는 방식입니다.

```text
공식 PDF / HWPX / HTML
        ↓
Parser
텍스트 · 표 · 페이지 위치 추출
        ↓
Chunking
검색 가능한 작은 단위로 분할
        ↓
Metadata
source_id · chunk_id · 문서명 · 조문 · PDF page
        ↓
Retrieval
현재 민원과 관련된 근거 검색
        ↓
LLM / Agent
검색 근거 + 사건 기록을 함께 보고 판단
```

AXeL은 파싱 결과를 바로 신뢰하지 않고 검수 상태와 출처 metadata를 보존합니다. 실제 답을 찾지 못한 경우에는 LLM이 학교별 날짜·사실을 만들어내지 않고 담당자 사실확인으로 전환합니다.

---

## Example — 생활지도 민원이 들어오면

**민원**
> “우리 아이가 수업 시간에 다른 학생보다 자주 지적받는다고 합니다. 어떤 상황에서 지도가 이루어졌는지 확인해 주세요. 담임선생님과 통화하고 싶습니다.”

**AXeL 대응**

```text
LLM        → 생활지도 관련 사실확인 필요
RAG        → 학교민원 처리 매뉴얼의 담당자 협조 근거 검색
History    → 동일 학생/보호자의 과거 사건 확인
Duty       → 생활체육부장(1순위) + 담임(협조) + 교감(승인)
Action     → 담당자에게 필요한 사실확인 Task
Teacher    → 수업 당시 확인 가능한 사실만 회신
Direct call→ 현재 단계에서는 요청하지 않음
```

회신이 완료되면 Agent가 다시 실행되어 확인된 사실·당사자 주장·미확인 내용을 분리하고 보호자 답변 초안을 준비합니다.

---

## Safety & Human-in-the-loop

AXeL은 민원을 자동으로 종결하거나 교육활동 침해를 확정하지 않습니다.

- **RAG grounding:** 법령·매뉴얼 주장은 연결된 공식 근거를 확인
- **Deterministic Validator:** LLM과 별도로 코드 규칙으로 위험 표현 검사
- **No auto-send:** `auto_send_allowed = false`
- **Human review:** 담당·승인·콜백·대외 답변·지원/이관은 학교 권한자가 확정
- **Audit trail:** 사건·Task·Agent Run·검토 이력을 DB에 기록
- **Privacy:** 실제 개인정보·민원 원문·DB·API key는 저장소에 커밋하지 않음

---

## Architecture

```text
┌──────────────────────────────┐
│ React + TypeScript + Vite    │  Vercel
│ Intake / Case / Task / Review│
└──────────────┬───────────────┘
               │ REST API
┌──────────────▼───────────────┐
│ FastAPI                      │  Render
│ Auth / Case / Task / Worker  │
└───────┬───────────────┬──────┘
        │               │
        ▼               ▼
┌───────────────┐  ┌──────────────┐
│ AXeL Agent    │  │ SQLite       │
│ LLM / RAG     │  │ Case / Task  │
│ History / Duty│  │ Agent / Audit│
│ Validator     │  └──────────────┘
└───────┬───────┘
        ▼
   OpenAI API
```

### Tech Stack

- **Frontend:** React 19, TypeScript, Vite, TanStack Query, React Router
- **Backend:** Python, FastAPI, SQLite, Background Worker
- **AI:** OpenAI Structured Output, Agent orchestration, deterministic validation
- **RAG:** PDF/HWPX/HTML ingestion, chunking, metadata normalization, lexical retrieval
- **Deployment:** Vercel + Render

더 자세한 구조는 [Architecture](docs/architecture.md)를 참고하세요.

---

## Hackathon Scope

### Level 1
- 민원 유형·긴급도·담당 분류
- 정보성 민원 공식 근거 검색 및 응답 초안
- 사건·업무·Agent 처리 이력 기록

### Level 2
- 반복·누적 민원 비교 및 미해결/후속/반복 검토
- 공식 근거 기반 관리자·지원 방향 제안
- 답변 초안 + 안전 검증
- 사건 총괄과 교사 업무 수행 분리

### Level 3
- 교육지원청 지원·이관 보고서 초안
- 활동·지원 현황 대시보드
- 다국어 민원 workflow
- 동의 기반 녹취·전사·요약 workflow

> Level 3 기능은 데모 구현 범위이며 실제 기관 연계·실제 학교 데이터 운영을 의미하지 않습니다.

---

## Demo Scenario

심사·시연용 권장 시나리오는 [Demo Scenario](docs/demo-scenario.md)에 정리되어 있습니다.

핵심 확인 포인트:

1. 새 생활지도 민원 접수
2. `LLM 분류: LLM` 확인
3. RAG 공식 근거와 페이지 확인
4. 생활체육부장 / 담임 협조 / 교감 승인 확인
5. `보호자 직접 연락: 현재 단계에서는 요청하지 않음`
6. 교직원 사실확인 Task
7. AI 지원 검토에서 FACT / CLAIM / UNVERIFIED 및 답변 초안 확인
8. Validator + 사람 검토 확인

---

## Run Locally

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m backend.seed
$env:SCHOOL_AGENT_RUN_WORKER="1"
python -m uvicorn backend.main:create_app --factory --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

브라우저: http://127.0.0.1:5173

### Environment

`.env.example`을 참고해 서버 환경에 다음 값을 설정합니다.

```text
OPENAI_API_KEY=
OPENAI_MODEL=
SCHOOL_AGENT_RUN_WORKER=1
```

Azure Speech 기반 녹취 전사를 사용할 경우 `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`도 설정합니다.

**API key, 개발 세션 토큰, 실제 민원 데이터는 Git에 올리지 마세요.**

---

## Repository Structure

```text
frontend/      React 웹앱
backend/       FastAPI, DB, Task, Agent Run, Audit
agent/         LLM/RAG/History/Duty/Response/Validator
ingestion/     공식 문서 parsing & chunking
data/          공개·가상 RAG 및 업무분장 데이터
docs/          architecture / demo / deployment docs
tests/         backend & agent regression tests
```

---

## Team

팀원명과 역할은 최종 제출 시 아래 형식으로 업데이트해 주세요.

| Role | Member |
|---|---|
| Planning / Product | — |
| AI / Agent / RAG | — |
| Backend | — |
| Frontend | — |

---

## Disclaimer

본 저장소와 공개 배포본은 **해커톤 시연용 프로토타입**입니다. 가상 학교·가상 민원 데이터를 사용하며, 실제 학교 운영에서는 기관 인증, 개인정보보호, 실제 학교 업무분장·규정 검증, 교육청 연계 절차와 별도의 운영 검토가 필요합니다.
