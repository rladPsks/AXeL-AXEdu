"""원문 구조와 위치를 보존하는 문서 청킹 모듈."""
from __future__ import annotations

import hashlib
import re
from typing import Any

ARTICLE_RE = re.compile(r"^\s*(제\s*\d+\s*조(?:의\s*\d+)?(?:\s*\([^)]*\))?)")
LAW_TYPES = {"law", "decree", "law_amendment_scheduled", "ordinance", "local_rule"}


def _stable_id(document_id: str, locator: str, index: int) -> str:
    raw = f"{document_id}|{locator}|{index}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    pieces = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                end = min(len(paragraph), start + max_chars)
                pieces.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(start + 1, end - overlap)
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = paragraph

    if current:
        pieces.append(current)
    return pieces


def _table_to_text(table: list[list[str]]) -> str:
    return "\n".join(" | ".join(cell for cell in row) for row in table)


def _base_chunk(document: dict[str, Any], text: str, locator: str,
                index: int, page_start: int | None, page_end: int | None,
                chunk_type: str, title: str | None = None) -> dict[str, Any]:
    fields = [
        "document_id", "title", "source_type", "issuer", "jurisdiction",
        "published_at", "effective_from", "effective_to", "official_url",
        "file_name", "file_sha256",
    ]
    chunk = {field: document.get(field) for field in fields}
    chunk.update({
        "chunk_id": _stable_id(str(document.get("document_id", "document")), locator, index),
        "chunk_type": chunk_type,
        "section_title": title,
        "locator": locator,
        "page_start": page_start,
        "page_end": page_end,
        "text": text,
        "char_count": len(text),
    })
    return chunk


def _law_units(document: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """법령의 조문 표식을 찾아 조문 단위로 나눕니다."""
    units = []
    current_title = None
    current_lines: list[str] = []
    current_start = None
    current_end = None

    def flush():
        nonlocal current_title, current_lines, current_start, current_end
        body = "\n".join(current_lines).strip()
        if body:
            units.append({
                "title": current_title,
                "text": body,
                "page_start": current_start,
                "page_end": current_end,
            })
        current_title, current_lines, current_start, current_end = None, [], None, None

    for page in document.get("pages", []):
        page_no = page.get("page_number")
        for line in (page.get("text") or "").splitlines():
            match = ARTICLE_RE.match(line)
            if match:
                flush()
                current_title = match.group(1).strip()
                current_start = page_no
            if line.strip():
                current_lines.append(line.rstrip())
                if page_no is not None:
                    current_end = page_no
    flush()

    found_article_markers = any(unit.get("title") for unit in units)
    if not found_article_markers:
        for page in document.get("pages", []):
            text = (page.get("text") or "").strip()
            if text:
                units.append({
                    "title": None,
                    "text": text,
                    "page_start": page.get("page_number"),
                    "page_end": page.get("page_number"),
                })
    return units, found_article_markers


def chunk_document(document: dict[str, Any], max_chars: int = 1800,
                   overlap: int = 180) -> dict[str, Any]:
    if max_chars < 200:
        raise ValueError("max_chars는 200 이상이어야 합니다.")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap은 0 이상 max_chars 미만이어야 합니다.")

    source_type = str(document.get("source_type", "")).lower()
    chunks = []
    index = 0
    warnings = list(document.get("warnings", []))

    if source_type in LAW_TYPES:
        units, found_article_markers = _law_units(document)
        if units and not found_article_markers:
            warnings.append("법령 조문 표식을 찾지 못해 페이지 단위로 임시 청킹했습니다. 원문 구조 검토가 필요합니다.")
        for unit in units:
            pieces = _split_long_text(unit["text"], max_chars, overlap)
            for part_no, piece in enumerate(pieces, start=1):
                index += 1
                locator = unit.get("title") or f"p{unit.get('page_start')}"
                if len(pieces) > 1:
                    locator = f"{locator}#part{part_no}"
                chunks.append(_base_chunk(
                    document, piece, locator, index,
                    unit.get("page_start"), unit.get("page_end"),
                    "law_article" if unit.get("title") else "law_page",
                    unit.get("title"),
                ))

    else:
        for page in document.get("pages", []):
            text = (page.get("text") or "").strip()
            if text:
                pieces = _split_long_text(text, max_chars, overlap)
                for part_no, piece in enumerate(pieces, start=1):
                    index += 1
                    locator = (
                        f"p{page.get('page_number')}"
                        if page.get("page_number")
                        else f"section{page.get('section_number')}"
                    )
                    if len(pieces) > 1:
                        locator += f"#part{part_no}"
                    chunks.append(_base_chunk(
                        document, piece, locator, index,
                        page.get("page_number"), page.get("page_number"), "body",
                    ))

            for table_no, table in enumerate(page.get("tables", []), start=1):
                table_text = _table_to_text(table)
                if table_text.strip():
                    index += 1
                    locator = (
                        f"p{page.get('page_number')}-table{table_no}"
                        if page.get("page_number")
                        else f"section{page.get('section_number')}-table{table_no}"
                    )
                    chunks.append(_base_chunk(
                        document, table_text, locator, index,
                        page.get("page_number"), page.get("page_number"),
                        "table", f"표 {table_no}",
                    ))

    return {
        "document_id": document.get("document_id"),
        "document_title": document.get("title"),
        "source_type": source_type,
        "file_sha256": document.get("file_sha256"),
        "chunking": {"max_chars": max_chars, "overlap": overlap},
        "chunk_count": len(chunks),
        "chunks": chunks,
        "warnings": warnings,
    }
