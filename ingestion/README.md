# 문서 파싱·청킹 도구

이 도구는 원본 문서를 읽어 **원문에 가까운 파싱 결과**와 검색용 청크 JSON을 생성합니다. 현재 지원 형식은 PDF, HWPX, HTML입니다.

## 1. 폴더 준비

프로젝트 루트에 다음 폴더를 만듭니다.

```text
documents/
├── raw/       # 원본 문서를 넣는 곳(학교 내부 자료는 Git에 올리지 않음)
├── parsed/    # 페이지·구역별 파싱 결과
└── chunks/    # 검색용 청크
```

## 2. 설치 및 실행

프로젝트 루트에서:

```bash
pip install -r requirements.txt
python -m ingestion.pipeline
```

입력·출력 경로를 바꾸려면:

```bash
python -m ingestion.pipeline --input documents/raw --parsed-output documents/parsed --chunks-output documents/chunks
```

## 3. 문서 메타데이터

원본 파일 옆에 `파일명.확장자.meta.json` 파일을 둘 수 있습니다. 예를 들어 `학교민원매뉴얼.pdf`의 메타데이터 파일 이름은 `학교민원매뉴얼.pdf.meta.json`입니다.

```json
{
  "source_id": "MOE-SCHOOL-COMPLAINT-MANUAL-2026",
  "title": "학교민원 처리 매뉴얼",
  "source_type": "official_manual",
  "issuer": "교육부·한국교육개발원",
  "jurisdiction": "national",
  "published_at": "2026-02",
  "effective_from": "2026-02",
  "official_url": "공식 원문 URL"
}
```

법령은 `source_type`을 `law` 또는 `decree`로 지정해야 조문 단위 청킹을 시도합니다. 지역교육청 규정은 `local_rule`, 학교 자체 문서는 `school_policy`로 분류합니다. 메타데이터를 제공하지 않으면 `unclassified`로 남기며, 법령·학교 규정으로 임의 추정하지 않습니다.

## 4. 출력 결과

각 원본 문서마다 다음 파일이 생성됩니다.

- `documents/parsed/{문서ID}.parsed.json`: 페이지 또는 HWPX 구역별 원문, 표, 문자 수, 추출 경고
- `documents/chunks/{문서ID}.chunks.json`: 청크 텍스트와 출처·페이지·시행일 메타데이터
- `documents/parsed/ingestion_report.json`: 전체 처리 성공·실패 및 검토 경고

## 5. 청킹 규칙

- 법률·시행령: 제○조 표식을 기준으로 조문 단위 청킹을 우선합니다. 조문이 추출되지 않으면 페이지 단위로 임시 생성하고 경고를 남깁니다.
- 매뉴얼·정책 문서: PDF 페이지 또는 HWPX 구역 단위로 원문을 나누고, 긴 문서는 최대 문자 수에 맞춰 분할합니다.
- 표: 본문과 분리된 표 청크로 저장해 표 구조를 보존합니다.
- 모든 청크에는 문서 ID, 파일 해시, 원문 위치를 저장합니다.

## 6. 파싱 품질 확인

- PDF에서 텍스트가 거의 없는 페이지는 OCR을 수행하지 않고 경고로 표시합니다.
- HWPX의 구역 번호는 실제 인쇄 페이지 번호와 다를 수 있습니다. 페이지 인용이 필요한 자료는 PDF 변환본과 대조해야 합니다.
- 표 추출 결과, 조문 제목, 페이지 누락 여부를 원본과 비교해야 합니다.
- 파서 결과는 자동으로 공식 지식베이스에 반영되지 않습니다. 검토 후 승인된 결과만 RAG 색인에 넣습니다.

## 주의

민원 원문이나 학생·보호자 개인정보가 포함된 내부 문서는 저장소에 커밋하지 마세요. 원본과 파싱 결과 모두 로컬에서 관리하고, 비식별화한 테스트 자료만 공유합니다.
