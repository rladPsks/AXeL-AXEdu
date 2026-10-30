# 문서 파싱·청킹 도구

원본 PDF·HWPX·HTML에서 텍스트, 표, 위치 및 문서 구조를 추출하고 검색용 청크를 생성합니다. 원문은 요약하거나 다시 쓰지 않습니다.

## 실행

프로젝트 루트에서:

\`\`\`powershell
python -m ingestion.pipeline
\`\`\`

기본 입력 폴더는 \`documents/raw\`, 파싱 결과는 \`documents/parsed\`, 청크는 \`documents/chunks\`입니다.

옵션:
- \`--no-ocr\`: OCR 비활성화
- \`--ocr-language kor+eng\`: Tesseract 언어
- \`--ocr-dpi 250\`: OCR 해상도
- \`--no-tables\`: PDF 표 추출 생략

## OCR 설치 (Windows)

선택적 OCR에는 외부 Tesseract 프로그램이 필요합니다. Python 패키지 설치만으로 Tesseract가 설치되지는 않습니다.

1. Windows용 Tesseract를 설치합니다.
2. 설치 과정에서 Korean 언어 데이터(\`kor\`)와 English(\`eng\`)를 포함합니다.
3. 설치 후 새 터미널에서 \`tesseract --version\`을 실행해 확인합니다.
4. 언어 데이터가 자동으로 검색되지 않으면 \`TESSDATA_PREFIX\` 환경변수를 tessdata 폴더로 지정합니다.

Tesseract가 없으면 일반 텍스트 파싱은 계속 진행하고, OCR이 필요한 페이지에만 경고를 기록합니다. 실제 빈 페이지와 단순 구분 페이지에는 OCR을 수행하지 않습니다.

## 파싱·OCR 정책

- PDF 본문은 PyMuPDF로 추출합니다.
- 이미지가 포함되어 있고 네이티브 텍스트가 적은 페이지에만 선택적으로 OCR합니다.
- OCR 결과는 \`extraction_method=pymupdf+ocr\`로 구분합니다.
- 페이지마다 \`page_type\`, \`image_coverage\`, \`ocr_status\`, \`warnings\`를 기록합니다.
- PDF 페이지 번호와 문서 인쇄 쪽수는 별도 필드로 관리합니다.
- PDF 텍스트의 색상·글꼴·위치 정보를 함께 추출합니다.

## 법령 청킹

- 법령명·법률번호·시행일 등 표제부는 조문 청크로 만들지 않습니다.
- 조문은 제목을 기준으로 나누고 페이지가 바뀌어도 원문 순서를 유지합니다.
- 빨간색 조문은 개정 후보로 식별합니다.
- 파란색 개정·시행 주석에서 명시적인 시행일을 찾으면 시행 예정 버전으로 별도 표시합니다.
- 색상만으로 시행일을 추정하지 않습니다. 빨간색 개정 후보에서 시행일을 확인할 수 없으면 \`amended_unverified\`와 \`requires_review=true\`로 표시해 검색·응답에 사용하기 전에 검수하도록 합니다.
- 기존 조문과 시행 예정 조문은 \`version_group\`, \`version_status\`, \`effective_from\`, \`effective_to\`로 연결합니다.

## 품질 검수

\`documents/parsed/ingestion_report.json\`에서 문서별 페이지 유형, 빈 페이지, 구분 페이지, OCR 성공·실패 및 페이지별 경고를 확인합니다.

파싱 결과는 자동으로 정식 RAG에 승인되지 않습니다. 특히 OCR 텍스트, 개정 조문, 표, 페이지 위치는 원본 PDF와 대조해야 합니다.

## 개인정보·저작권

실제 학교 내부 문서와 개인정보가 포함된 민원 원문, 파싱 결과는 저장소에 커밋하지 마세요. 가상·비식별화 자료만 공유합니다.
