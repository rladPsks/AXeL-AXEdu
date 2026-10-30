# B 녹취·활동 기록·대시보드 연결 안내

## 구성
- 활동 기록: `POST/GET /api/cases/{id}/activities` (사건 탭 "활동 기록"). 시간 미입력은 0분이 아닌 "시간 미기록".
- 대시보드: `GET /api/dashboard?from=&to=` (관리자 전용, 한국 시간 기준 날짜, 순위 없음). 화면 `/dashboard`.
- 동의 녹취: 동의 기록 → Azure 전사(`TRANSCRIBE_AUDIO`) → 사람의 음성 대조 → 원본 저장(rev 1) → 정정(rev N+1, 이전 버전 보존) → 발화 요약(`SUMMARIZE_TRANSCRIPT`, 구간 근거 필수).
- 동의가 없거나 철회되면 음성은 STT로 전송되지 않으며, 실행 중 철회되면 결과를 폐기합니다.

## 환경변수
`AZURE_SPEECH_KEY` + (`AZURE_SPEECH_REGION` 또는 `AZURE_SPEECH_ENDPOINT`). 요약에는 기존 `OPENAI_API_KEY`/`OPENAI_MODEL`이 필요합니다.

## 로컬 검증 순서
1. `.\.venv\Scripts\python.exe -m pytest -q`  (신규: tests/test_dashboard.py, tests/test_recordings.py)
2. `cd frontend; npm.cmd run build; npm.cmd test`
3. `python -m backend.export_contract` 로 contracts/openapi.json 갱신
4. 짧은 한국어 음성(wav/mp3/ogg, 10MB 이하)으로 실제 Azure 전사 확인

## 알려진 한계
- 위 테스트는 작성만 되었고 아직 실행되지 않았습니다.
- 전사본 보관·삭제 정책(동의 철회 후)은 학교 정책에 따릅니다.
- 화자 구분은 자동 번호이며 신원·역할이 아닙니다.
