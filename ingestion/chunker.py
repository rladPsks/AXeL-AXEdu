"""원문 구조·개정 버전·페이지 위치를 보존하는 청킹 모듈."""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

ARTICLE_RE = re.compile(r"^\s*(제\s*\d+\s*조(?:의\s*\d+)?(?:\s*\([^)]*\))?)")
ARTICLE_NO_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
LAW_TYPES = {"law", "decree", "law_amendment_scheduled", "ordinance", "local_rule"}
DATE_RE = re.compile(r"시행일\s*[:：]?\s*(\d{4})\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})")
ANNOTATION_RE = re.compile(r"^\s*(?:\[.*(?:개정|시행|본조신설|종전|이동)|<.*(?:개정|시행).*>|※)")


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


def _rgb_name(hex_color: str) -> str:
    try:
        value = hex_color.lstrip("#")
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return "unknown"
    if r > 150 and g < 120 and b < 120 and r > g * 1.4 and r > b * 1.4:
        return "red"
    if b > 130 and r < 130 and g < 150 and b > r * 1.2:
        return "blue"
    if max(r, g, b) < 100:
        return "black"
    return "other"


def _line_color(line: dict[str, Any]) -> str:
    segments = line.get("segments", [])
    counts: dict[str, int] = {}
    for segment in segments:
        color = _rgb_name(segment.get("color", ""))
        counts[color] = counts.get(color, 0) + len(segment.get("text", "").strip())
    if not counts:
        return "unknown"
    return max(counts, key=counts.get)


def _line_records(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for page in document.get("pages", []):
        page_no = page.get("page_number")
        styled = page.get("styled_lines") or []
        if styled:
            for line in styled:
                value = dict(line)
                value["page_number"] = page_no
                value["color_name"] = _line_color(line)
                records.append(value)
        else:
            for line in (page.get("text") or "").splitlines():
                if line.strip():
                    records.append({
                        "text": line.strip(),
                        "segments": [],
                        "color_name": "unknown",
                        "page_number": page_no,
                    })
    return records


def _extract_effective_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _law_occurrences(document: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    records = _line_records(document)
    occurrences: list[dict[str, Any]] = []
    preamble: list[str] = []
    current: dict[str, Any] | None = None

    def flush():
        nonlocal current
        if not current:
            return
        lines = current["lines"]
        all_text = "\n".join(item["text"] for item in lines).strip()
        if all_text:
            heading_color = lines[0].get("color_name", "unknown") if lines else "unknown"
            red_chars = sum(
                len(item["text"]) for item in lines
                if item.get("color_name") == "red"
            )
            total_chars = sum(len(item["text"]) for item in lines)
            red_ratio = red_chars / max(total_chars, 1)
            annotations = [
                item["text"] for item in lines
                if item.get("color_name") == "blue"
                or ANNOTATION_RE.match(item["text"])
            ]
            body_lines = [
                item["text"] for item in lines
                if item.get("color_name") != "blue"
                and not ANNOTATION_RE.match(item["text"])
            ]
            body = "\n".join(body_lines).strip()
            # 빨간 글자 비중은 개정 표시를 찾는 신호일 뿐, 시행일의 법적 판단을 대신하지 않습니다.
            # 개정 표시 PDF는 조문 제목만 빨간색이고 본문 일부는 검은색일 수 있습니다.
            # 따라서 제목 색상을 우선 사용하고, 본문 색상 비율은 보조 신호로만 씁니다.
            is_red_revision = heading_color == "red" or red_ratio >= 0.25
            date_text = "\n".join(annotations + [all_text])
            revision_date = _extract_effective_date(date_text) if is_red_revision else None
            if is_red_revision:
                version_status = "scheduled" if revision_date else "amended_unverified"
            else:
                version_status = "in_force"
            article_match = ARTICLE_NO_RE.search(current["title"])
            article_no = None
            if article_match:
                article_no = article_match.group(1)
                if article_match.group(2):
                    article_no += f"의{article_match.group(2)}"
            occurrences.append({
                "title": current["title"],
                "article_number": article_no,
                "text": body or all_text,
                "raw_text": all_text,
                "annotations": annotations,
                "page_start": current["page_start"],
                "page_end": current["page_end"],
                "visual_color": "red" if is_red_revision else "black_or_unclassified",
                "heading_color": heading_color,
                "version_status": version_status,
                "revision_effective_from": revision_date,
                "requires_review": version_status == "amended_unverified",
                "red_ratio": round(red_ratio, 3),
            })
        current = None

    for record in records:
        text = record["text"]
        match = ARTICLE_RE.match(text)
        if match:
            flush()
            current = {
                "title": match.group(1).strip(),
                "page_start": record.get("page_number"),
                "page_end": record.get("page_number"),
                "lines": [],
            }
        if current is None:
            if text.strip():
                preamble.append(text.strip())
            continue
        current["lines"].append(record)
        if record.get("page_number") is not None:
            current["page_end"] = record["page_number"]
    flush()
    return occurrences, preamble


def _law_units(document: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, list[str]]:
    occurrences, preamble = _law_occurrences(document)
    units = []

    # 동일 조문에 대해 현행본과 시행 예정 개정본이 모두 있으면 시행일을 연결합니다.
    scheduled_by_article = {}
    for occurrence in occurrences:
        if occurrence["version_status"] == "scheduled" and occurrence.get("revision_effective_from"):
            scheduled_by_article.setdefault(occurrence["article_number"], []).append(
                occurrence["revision_effective_from"]
            )

    for occurrence in occurrences:
        item = dict(occurrence)
        if item["version_status"] == "in_force":
            future_dates = scheduled_by_article.get(item["article_number"], [])
            future_dates = [value for value in future_dates if value > str(document.get("effective_from") or "0001-01-01")]
            if future_dates:
                first_date = min(future_dates)
                item["effective_to"] = (date.fromisoformat(first_date) - timedelta(days=1)).isoformat()
            else:
                item["effective_to"] = document.get("effective_to")
            item["effective_from"] = document.get("effective_from")
        elif item["version_status"] == "scheduled":
            item["effective_from"] = item["revision_effective_from"]
            item["effective_to"] = None
        else:
            item["effective_from"] = None
            item["effective_to"] = None
        units.append(item)

    return units, bool(occurrences), preamble


def _base_chunk(document: dict[str, Any], text: str, locator: str,
                index: int, page_start: int | None, page_end: int | None,
                chunk_type: str, title: str | None = None,
                extra: dict[str, Any] | None = None) -> dict[str, Any]:
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
    if extra:
        chunk.update(extra)
    return chunk


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
    document_header = []

    if source_type in LAW_TYPES:
        units, found_article_markers, document_header = _law_units(document)
        if not found_article_markers:
            warnings.append("법령 조문 표식을 찾지 못했습니다. 원문 구조를 검토해야 합니다.")
        # 조문 이전의 법령명·법률번호·담당기관 표시는 조문 청크로 만들지 않습니다.

        for unit_index, unit in enumerate(units, start=1):
            pieces = _split_long_text(unit["text"], max_chars, overlap)
            for part_no, piece in enumerate(pieces, start=1):
                index += 1
                article_label = unit.get("title") or f"p{unit.get('page_start')}"
                version = unit.get("version_status", "in_force")
                locator = f'{article_label}@{version}'
                if len(pieces) > 1:
                    locator += f"#part{part_no}"
                extra = {
                    "article_number": unit.get("article_number"),
                    "version_status": version,
                    "effective_from": unit.get("effective_from"),
                    "effective_to": unit.get("effective_to"),
                    "revision_effective_from": unit.get("revision_effective_from"),
                    "revision_annotations": unit.get("annotations", []),
                    "visual_color": unit.get("visual_color"),
                    "requires_review": unit.get("requires_review", False),
                    "version_group": f'{document.get("document_id")}:{unit.get("article_number")}',
                    "paragraph_markers": sorted(set(re.findall(r"(?:^|\s)([①-⑳]|[1-9]\d*\.)", piece))),
                }
                chunks.append(_base_chunk(
                    document, piece, locator, index,
                    unit.get("page_start"), unit.get("page_end"),
                    "law_article", unit.get("title"), extra,
                ))
    else:
        for page in document.get("pages", []):
            text = (page.get("text") or "").strip()
            page_type = page.get("page_type", "content")
            if text and page_type not in {"blank"}:
                pieces = _split_long_text(text, max_chars, overlap)
                for part_no, piece in enumerate(pieces, start=1):
                    index += 1
                    locator = (
                        f"p{page.get('page_number')}"
                        if page.get("page_number")
                        else f"section{page.get('section_number')}"
                    )
                    if page_type == "section_divider":
                        locator += "-heading"
                    if len(pieces) > 1:
                        locator += f"#part{part_no}"
                    extra = {
                        "page_type": page_type,
                        "extraction_method": page.get("extraction_method"),
                        "printed_page_number": page.get("printed_page_number"),
                    }
                    chunks.append(_base_chunk(
                        document, piece, locator, index,
                        page.get("page_number"), page.get("page_number"),
                        "section_heading" if page_type == "section_divider" else "body",
                        None, extra,
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
        "document_header": document_header,
        "chunking": {"max_chars": max_chars, "overlap": overlap},
        "chunk_count": len(chunks),
        "chunks": chunks,
        "warnings": warnings,
    }
