"""PDF, HWPX, HTML 원본 문서 파서.

원칙:
- 추출한 원문을 요약하거나 문장을 고쳐 쓰지 않습니다.
- PDF는 실제 PDF 페이지를, HWPX는 구역(section)을 위치 정보로 보존합니다.
- 텍스트가 거의 없는 페이지는 OCR하지 않고 검토 대상으로 표시합니다.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

SUPPORTED_EXTENSIONS = {".pdf", ".hwpx", ".html", ".htm"}
PARSER_VERSION = "0.1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sidecar_metadata(path: Path) -> dict[str, Any]:
    """문서 옆의 <파일명>.<확장자>.meta.json 또는 <파일명>.meta.json을 읽습니다."""
    candidates = [
        path.with_name(path.name + ".meta.json"),
        path.with_suffix(".meta.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            import json
            try:
                value = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"메타데이터 파일을 읽을 수 없습니다: {candidate}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"메타데이터는 JSON 객체여야 합니다: {candidate}")
            return value
    return {}


def _base_document(path: Path, metadata: dict[str, Any], file_type: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "document_id": str(metadata.get("source_id") or path.stem),
        "title": str(metadata.get("title") or path.stem),
        "source_type": str(metadata.get("source_type") or "unclassified"),
        "issuer": metadata.get("issuer"),
        "jurisdiction": metadata.get("jurisdiction"),
        "published_at": metadata.get("published_at"),
        "effective_from": metadata.get("effective_from"),
        "effective_to": metadata.get("effective_to"),
        "official_url": metadata.get("official_url"),
        "file_name": path.name,
        "file_type": file_type,
        "file_sha256": sha256_file(path),
        "parser_version": PARSER_VERSION,
        "parsed_at": now,
        "pages": [],
        "warnings": [],
    }


def _clean_table(table: list[list[Any]] | None) -> list[list[str]]:
    if not table:
        return []
    cleaned = []
    for row in table:
        cells = [re.sub(r"\\s+", " ", str(cell or "")).strip() for cell in row]
        if any(cells):
            cleaned.append(cells)
    return cleaned


def parse_pdf(path: Path, metadata: dict[str, Any] | None = None,
              min_text_chars: int = 20, extract_tables: bool = True) -> dict[str, Any]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF 파싱에는 PyMuPDF가 필요합니다. pip install PyMuPDF") from exc

    metadata = metadata or {}
    document = _base_document(path, metadata, "pdf")
    table_pages: dict[int, list[list[list[str]]]] = {}
    if extract_tables:
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    extracted = []
                    for table in page.extract_tables() or []:
                        cleaned = _clean_table(table)
                        if cleaned:
                            extracted.append(cleaned)
                    if extracted:
                        table_pages[index] = extracted
        except Exception as exc:  # 표 추출 실패는 본문 파싱 실패로 처리하지 않습니다.
            document["warnings"].append(f"표 추출을 완료하지 못했습니다: {type(exc).__name__}: {exc}")

    with fitz.open(path) as pdf:
        document["page_count"] = pdf.page_count
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text", sort=True) or ""
            text = text.replace("\x00", "").strip()
            warnings = []
            if len(text) < min_text_chars:
                warnings.append("텍스트가 거의 없습니다. 이미지 기반 문서일 수 있어 원본 페이지 확인 또는 OCR이 필요합니다.")
            document["pages"].append({
                "page_number": index,
                "section_number": None,
                "text": text,
                "tables": table_pages.get(index, []),
                "char_count": len(text),
                "extraction_method": "pymupdf",
                "warnings": warnings,
            })
    if not document["pages"]:
        document["warnings"].append("PDF에서 페이지를 추출하지 못했습니다.")
    return document


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _element_text(element: ET.Element) -> str:
    parts = []
    for node in element.iter():
        if _local_name(node.tag) in {"t", "text"} and node.text:
            parts.append(node.text)
    return "".join(parts).strip()


def _inside_table(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    current = parents.get(element)
    while current is not None:
        if _local_name(current.tag) in {"tbl", "table"}:
            return True
        current = parents.get(current)
    return False


def _parse_hwpx_section(xml_bytes: bytes) -> tuple[str, list[list[list[str]]]]:
    root = ET.fromstring(xml_bytes)
    parents = {child: parent for parent in root.iter() for child in parent}
    paragraphs = []
    for element in root.iter():
        if _local_name(element.tag) == "p" and not _inside_table(element, parents):
            text = _element_text(element)
            if text:
                paragraphs.append(text)

    tables = []
    for table in root.iter():
        if _local_name(table.tag) not in {"tbl", "table"}:
            continue
        rows = []
        for row in table.iter():
            if _local_name(row.tag) not in {"tr", "row"}:
                continue
            cells = []
            for cell in row.iter():
                if _local_name(cell.tag) in {"tc", "cell"}:
                    cell_text = _element_text(cell)
                    cells.append(re.sub(r"\\s+", " ", cell_text).strip())
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return "\\n".join(paragraphs), tables


def parse_hwpx(path: Path, metadata: dict[str, Any] | None = None,
               min_text_chars: int = 20) -> dict[str, Any]:
    metadata = metadata or {}
    document = _base_document(path, metadata, "hwpx")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            section_names = [
                name for name in names
                if re.fullmatch(r"Contents/section\\d+\\.xml", name, flags=re.IGNORECASE)
            ]
            section_names.sort(key=lambda name: int(re.search(r"section(\\d+)", name, re.IGNORECASE).group(1)))
            if not section_names:
                raise ValueError("HWPX 내부에서 Contents/section*.xml 파일을 찾지 못했습니다.")
            for section_index, name in enumerate(section_names, start=1):
                text, tables = _parse_hwpx_section(archive.read(name))
                warnings = []
                if len(text) < min_text_chars:
                    warnings.append("추출된 텍스트가 적습니다. 원본 한글 문서의 구역 내용을 확인해 주세요.")
                document["pages"].append({
                    "page_number": None,
                    "section_number": section_index,
                    "section_file": name,
                    "text": text,
                    "tables": tables,
                    "char_count": len(text),
                    "extraction_method": "hwpx_xml",
                    "warnings": warnings,
                })
    except zipfile.BadZipFile as exc:
        raise ValueError(f"유효한 HWPX 압축 문서가 아닙니다: {path}") from exc
    document["section_count"] = len(document["pages"])
    document["warnings"].append("HWPX 구역은 실제 인쇄 페이지와 일치하지 않을 수 있습니다. 페이지 단위 인용이 필요한 경우 PDF 변환본과 대조하세요.")
    return document


def parse_html(path: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("HTML 파싱에는 beautifulsoup4가 필요합니다.") from exc

    metadata = metadata or {}
    document = _base_document(path, metadata, "html")
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    if title and not metadata.get("title"):
        document["title"] = title

    body = soup.body or soup
    blocks = []
    for element in body.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = element.get_text(" ", strip=True)
        if text:
            blocks.append(text)

    tables = []
    for table in body.find_all("table"):
        rows = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)

    text = "\\n".join(blocks)
    document["pages"].append({
        "page_number": None,
        "section_number": None,
        "text": text,
        "tables": tables,
        "char_count": len(text),
        "extraction_method": "beautifulsoup",
        "warnings": [],
    })
    document["warnings"].append("HTML 문서는 고정 페이지가 없으므로 페이지 인용 대신 제목·문서 URL·문단 위치를 사용해야 합니다.")
    return document


def parse_document(path: Path, metadata: dict[str, Any] | None = None,
                   min_text_chars: int = 20, extract_tables: bool = True) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path, metadata, min_text_chars, extract_tables)
    if suffix == ".hwpx":
        return parse_hwpx(path, metadata, min_text_chars)
    if suffix in {".html", ".htm"}:
        return parse_html(path, metadata)
    raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix}")
