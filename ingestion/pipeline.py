"""문서 파싱·청킹 파이프라인과 명령행 인터페이스."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .chunker import chunk_document
from .parsers import SUPPORTED_EXTENSIONS, load_sidecar_metadata, parse_document


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("._")
    return cleaned or "document"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_file(path: Path, parsed_dir: Path, chunks_dir: Path,
                 max_chars: int = 1800, overlap: int = 180,
                 extract_tables: bool = True, enable_ocr: bool = True,
                 ocr_language: str = "kor+eng", ocr_dpi: int = 250) -> dict[str, Any]:
    metadata = load_sidecar_metadata(path)
    document = parse_document(
        path, metadata, extract_tables=extract_tables,
        enable_ocr=enable_ocr, ocr_language=ocr_language, ocr_dpi=ocr_dpi,
    )
    chunks = chunk_document(document, max_chars=max_chars, overlap=overlap)

    filename = _safe_name(str(document.get("document_id") or path.stem))
    parsed_path = parsed_dir / f"{filename}.parsed.json"
    chunks_path = chunks_dir / f"{filename}.chunks.json"
    _write_json(parsed_path, document)
    _write_json(chunks_path, chunks)

    pages = document.get("pages", [])
    page_warning_list = [
        {
            "page_number": page.get("page_number"),
            "page_type": page.get("page_type"),
            "warnings": page.get("warnings", []),
            "ocr_status": page.get("ocr_status"),
        }
        for page in pages if page.get("warnings")
    ]
    quality = {
        "blank_pages": sum(page.get("page_type") == "blank" for page in pages),
        "section_divider_pages": sum(page.get("page_type") == "section_divider" for page in pages),
        "image_content_unreadable_pages": [
            page.get("page_number") for page in pages
            if page.get("page_type") == "image_content_unreadable"
        ],
        "ocr": document.get("ocr_summary", {}),
        "pages_with_warnings": page_warning_list,
        "law_chunks_requiring_review": sum(
            bool(chunk.get("requires_review")) for chunk in chunks.get("chunks", [])
        ),
    }
    return {
        "file": path.name,
        "document_id": document.get("document_id"),
        "page_or_section_count": len(pages),
        "chunk_count": chunks.get("chunk_count", 0),
        "parsed_output": str(parsed_path),
        "chunk_output": str(chunks_path),
        "warnings": document.get("warnings", []) + chunks.get("warnings", []),
        "quality": quality,
        "status": "ok",
    }


def run(input_dir: Path, parsed_dir: Path, chunks_dir: Path,
        max_chars: int = 1800, overlap: int = 180,
        extract_tables: bool = True, enable_ocr: bool = True,
        ocr_language: str = "kor+eng", ocr_dpi: int = 250) -> dict[str, Any]:
    if not input_dir.exists():
        raise FileNotFoundError(f"입력 폴더가 없습니다: {input_dir}")

    source_files = sorted(
        path for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and not path.name.endswith(".meta.json")
    )
    results = []
    for path in source_files:
        try:
            results.append(process_file(
                path, parsed_dir, chunks_dir, max_chars, overlap,
                extract_tables, enable_ocr, ocr_language, ocr_dpi,
            ))
        except Exception as exc:
            results.append({
                "file": path.name,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    report = {
        "input_dir": str(input_dir),
        "parsed_count": sum(item.get("status") == "ok" for item in results),
        "error_count": sum(item.get("status") == "error" for item in results),
        "results": results,
    }
    _write_json(parsed_dir / "ingestion_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AXeL 문서 파싱 및 청킹 도구")
    parser.add_argument("--input", type=Path, default=Path("documents/raw"), help="원본 문서 폴더")
    parser.add_argument("--parsed-output", type=Path, default=Path("documents/parsed"), help="파싱 결과 저장 폴더")
    parser.add_argument("--chunks-output", type=Path, default=Path("documents/chunks"), help="검색용 청크 저장 폴더")
    parser.add_argument("--max-chars", type=int, default=1800, help="청크 최대 문자 수")
    parser.add_argument("--overlap", type=int, default=180, help="청크 간 겹치는 문자 수")
    parser.add_argument("--no-tables", action="store_true", help="PDF 표 추출 생략")
    parser.add_argument("--no-ocr", action="store_true", help="이미지 페이지 OCR 생략")
    parser.add_argument("--ocr-language", default="kor+eng", help="Tesseract 언어 데이터 (기본: kor+eng)")
    parser.add_argument("--ocr-dpi", type=int, default=250, help="OCR 렌더링 해상도")
    args = parser.parse_args()

    report = run(
        args.input, args.parsed_output, args.chunks_output,
        args.max_chars, args.overlap, not args.no_tables,
        not args.no_ocr, args.ocr_language, args.ocr_dpi,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["error_count"]:
        raise SystemExit(1)
    if report["parsed_count"] == 0:
        print("지원되는 문서가 없습니다. documents/raw 폴더에 PDF, HWPX 또는 HTML 파일을 넣어주세요.")


if __name__ == "__main__":
    main()
