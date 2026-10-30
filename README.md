# AXeL-AXEdu | CARE Agent

학교 민원대응팀의 민원 접수·분류·담당 추천·근거 제시·처리 이력 관리를 지원하는 프로토타입입니다.

## 원칙
- AI는 민원 내용과 맥락을 구조화하고 담당자에게 검토안을 제안합니다.
- 법적 판단, 교육활동 침해 여부 확정, 민원 종결, 발송, 외부기관 이관은 사람이 결정합니다.
- 학교별 업무분장·학사일정이 확인되기 전의 데이터는 데모 템플릿입니다.

## 실행
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

LLM API 키는 로컬 `.env`에만 설정합니다. 현재 분류기는 실행 흐름 확인용 규칙 기반 예비 버전입니다. 학교 규정·업무분장·최신 법령과 대조한 후 운영해야 합니다.
