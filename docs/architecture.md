# AXeL Technical Architecture

## 1. Design Goal

AXeL의 기술 목표는 “민원 답변을 잘 생성하는 챗봇”이 아니라 **학교 민원 처리 workflow를 조율하는 Agent**를 만드는 것입니다.

핵심 설계는 세 가지입니다.

1. LLM의 판단을 공식 근거와 학교 조직 정보에 grounding한다.
2. 사건 총괄과 개별 Task 수행자를 분리한다.
3. 사람의 회신이 들어오면 Agent가 다시 실행되는 multi-step loop를 만든다.

---

## 2. End-to-End Flow

```text
POST /api/intakes
      │
      ├─ Multilingual
      │    └─ 외국어 → 내부 한국어 번역
      │
      ├─ LLM Classifier
      │    └─ nature / urgency / domain / needs_fact_check
      │
      ├─ Official Retrieval
      │    └─ 법령 / 매뉴얼 / 정책 / 공개 학교자료
      │
      ├─ History Agent
      │    └─ unresolved / follow-up / repeat review
      │
      ├─ School Duty Router
      │    └─ primary / collaborator / approver / backup
      │
      └─ Action Router
           └─ FACT_CHECK / ADMIN_REVIEW / HISTORY_REVIEW ...
                    │
                    ▼
              tasks + notifications
                    │
              human responses
                    │
                    ▼
              Agent Run Worker
                    │
          REVIEW_SUPPORT / re-plan
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
 Official Retrieval        Case / Task snapshot
        └───────────┬───────────┘
                    ▼
              Response Draft
                    │
                    ▼
          Deterministic Validator
                    │
                    ▼
               Human Review
```

---

## 3. LLM Triage

`agent/classify.py`는 민원 원문을 structured JSON으로 변환합니다.

주요 출력:
- 민원 성격과 domain
- urgency
- 핵심 요구
- 사실확인 필요 항목
- 정보성 문의 여부
- 위험/보호 검토 신호
- 교사에게 전달할 요약

LLM 사용이 불가능하면 rule fallback으로 접수 workflow 자체는 계속 진행됩니다. UI의 `classifier_mode`로 실제 LLM 실행 여부를 구분할 수 있습니다.

---

## 4. Official RAG

### RAG란?

Retrieval-Augmented Generation은 모델이 기억에 의존해 답하는 대신 **외부 문서에서 관련 근거를 검색해 모델 입력에 함께 제공하는 방식**입니다.

### AXeL Pipeline

```text
PDF / HWPX / HTML
      ↓
ingestion.parsers
      ↓
페이지 · 표 · 위치 · 텍스트 추출
      ↓
ingestion.chunker
      ↓
검색용 chunk
      ↓
source_id / chunk_id / locator / page metadata
      ↓
agent.retrieval
      ↓
현재 민원과 관련된 근거
```

현재 corpus에는 학교민원 처리 매뉴얼, 관련 법령, 교육부 정책자료 등의 공개·가상 데이터가 포함됩니다.

파싱된 corpus와 검수된 baseline corpus를 함께 사용하며, 동일 chunk ID는 최신 parsed/corrected 데이터가 우선합니다. 검수 상태와 페이지 metadata를 보존해 UI와 Agent Run에서 근거를 추적할 수 있도록 설계했습니다.

---

## 5. History Agent

`agent/history_agent.py`는 과거 민원 존재만으로 반복민원이라고 판단하지 않습니다.

비교 신호:
- 내용 유사도
- 새로운 날짜/수치/요구
- 기존 실질 답변 여부
- 미해결 사건 여부

결과:
- `NONE`
- `LINK_UNRESOLVED`
- `REVIEW_FOLLOW_UP`
- `REVIEW_REPEAT`

즉 “몇 번째 민원인가”보다 **이전 사건이 실제로 해결됐는가, 새로운 내용이 있는가**를 먼저 봅니다.

---

## 6. School Duty Tool

`agent/routing.py`는 가상 학교 업무분장 데이터와 민원 context를 함께 사용합니다.

입력:
- 사용자가 선택한 민원 종류
- 발생 경위
- 민원 원문
- LLM domain/subcategory

출력:
- 1순위 담당
- 협조자
- 승인자
- 부재 시 대체 담당
- callback 기본 판단

예: 생활지도·학생 갈등 → 생활체육부장 / 담임 협조 / 교감 승인.

실제 도입 시 `data/school_duty_map_demo.json`을 해당 학교의 학년도별 업무분장 데이터로 교체해야 합니다.

---

## 7. Action Router & Teacher Protection

`agent/action_router.py`는 분석 결과를 실제 업무 단위로 변환합니다.

예:
- `FACT_CHECK`
- `COOP_FACT_CHECK`
- `STUDENT_COUNSEL`
- `ADMIN_REVIEW`
- `HISTORY_REVIEW`
- `RESPONSE_REVIEW`

중요한 데이터 모델:

```text
case.owner_id != task.assignee_id
```

Task를 수행한 교직원이 자동으로 사건 총괄자가 되지 않습니다. 교사에게는 확인 가능한 사실만 요청하고 보호자 응대 책임은 학교 대응체계에 유지할 수 있습니다.

---

## 8. Agent Re-planning

Agent 실행은 `agent_runs`에 snapshot과 함께 저장되고 background worker가 provider를 호출합니다.

후속 검토에서는:
- 사건 원문
- 초기 classification/routing
- 공식 근거
- Task 회신
- 지원 기록
- 선택한 문서 버전

을 함께 읽습니다.

모델은 관찰을:
- `FACT`
- `CLAIM`
- `UNVERIFIED`

로 구분하고 missing information, 지원 방향, 행동 옵션, 보호자 답변 초안을 반환합니다.

---

## 9. Deterministic Validator

`agent/validator.py`는 LLM과 별도로 코드 규칙으로 답변을 검사합니다.

현재 검사 예:
- `UNAUTHORIZED_PROMISE`: 확정되지 않은 책임 인정·보상/처벌 약속
- `UNGROUNDED_POLICY_CLAIM`: 공식 evidence 없는 법령·정책 표현
- `RISKY_DIRECT_CONTACT`: 위험 사건에서 교직원 직접 전화/방문 자동 권유
- `HUMAN_REVIEW_CLAIM`: 사람이 추가 확인해야 하는 주장

항상:
```text
auto_send_allowed = false
human_review_required = true
```

를 유지합니다.

---

## 10. Multilingual & Support Report

### Multilingual

`agent/multilingual.py`
```text
foreign language
→ detect
→ translate to Korean
→ same Agent workflow
→ Korean draft
→ translate back
→ human semantic review
```

원문의 강도·요구를 임의로 완화하지 않도록 prompt를 분리합니다.

### Support Report

`agent/report_agent.py`는 사건·Task·지원·timeline을 모아 교육지원청 지원/이관 검토용 초안을 생성합니다.

`report_status = DRAFT`이며 자동 제출하지 않습니다.

---

## 11. Data & Audit

주요 저장 구조:
- `cases`: 사건 원장
- `case_intakes`: 원문, classification, routing, workflow
- `tasks`: 교직원 확인 업무와 reply
- `agent_runs`: Agent snapshot/status/result
- `agent_run_events`: Agent 실행 상태 이력
- `support_requests`: 학교 지원 요청
- `audit_events`: 사용자 행동/사건 변경 기록
- documents / recordings / transcripts: 버전·녹취 관련 기록

---

## 12. Runtime Architecture

- **Frontend:** React + TypeScript + Vite
- **API:** FastAPI
- **Agent Provider:** OpenAI Responses API / Structured Output
- **Database:** SQLite (hackathon demo)
- **Worker:** FastAPI 내부 background worker 또는 별도 worker
- **Frontend deployment:** Vercel
- **Backend deployment:** Render

공개 배포본은 가상 데이터 기반 시연 환경이며 Render free-tier 특성상 runtime SQLite 데이터는 영구 저장소로 간주하지 않습니다.

---

## 13. Safety Boundary

AXeL이 자동으로 하지 않는 것:
- 교육활동 침해/악성 민원 법적 확정
- 교사 책임 확정
- 사건 자동 종결
- 보호자 답변 자동 발송
- 교육지원청 자동 제출
- 실제 담당/승인 권한의 무검토 변경

Agent는 **판단에 필요한 정보와 다음 행동을 준비하고, 최종 결정은 학교 권한자에게 남깁니다.**
