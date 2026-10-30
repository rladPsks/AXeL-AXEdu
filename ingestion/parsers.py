"""PDF, HWPX, HTML 원본 문서 파서.

원문을 요약·재작성하지 않고 텍스트, 표, 페이지 위치, 글자 스타일을 보존합니다.
PDF의 저텍스트 페이지는 이미지가 있는 경우에만 선택적으로 OCR합니다.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

SUPPORTED_EXTENSIONS = {".pdf", ".hwpx", ".html", ".htm"}
PARSER_VERSION = "0.2.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sidecar_metadata(path: Path) -> dict[str, Any]:
    """<파일명>.<확장자>.meta.json 또는 <파일명>.meta.json을 읽습니다."""
    candidates = [path.with_name(path.name + ".meta.json"), path.with_suffix(".meta.json")]
    for candidate in candidates:
        if candidate.exists():
            try:
                # PowerShell이 생성한 UTF-8 BOM 포함 JSON도 허용합니다.
                value = json.loads(candidate.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"메타데이터 파일을 읽을 수 없습니다: {candidate}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"메타데이터는 JSON 객체여야 합니다: {candidate}")
            return value
    return {}


def _base_document(path: Path, metadata: dict[str, Any], file_type: str) -> dict[str, Any]:
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
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "pages": [],
        "warnings": [],
    }


def _clean_table(table: list[list[Any]] | None) -> list[list[str]]:
    if not table:
        return []
    cleaned = []
    for row in table:
        cells = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
        if any(cells):
            cleaned.append(cells)
    return cleaned


def _color_hex(color: Any) -> str:
    """PyMuPDF의 RGB 정수 색상값을 #RRGGBB로 변환합니다."""
    if not isinstance(color, int):
        return "#000000"
    return f"#{color & 0xFFFFFF:06X}"


def _extract_styled_lines(page: Any) -> list[dict[str, Any]]:
    """PDF 텍스트를 줄 단위로 추출하면서 색상·위치·글꼴 정보를 보존합니다."""
    result = []
    page_dict = page.get_text("dict", sort=True)
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            segments = []
            texts = []
            for span in line.get("spans", []):
                value = span.get("text", "")
                if not value:
                    continue
                color = _color_hex(span.get("color", 0))
                segments.append({
                    "text": value,
                    "color": color,
                    "font": span.get("font"),
                    "size": round(float(span.get("size", 0)), 2),
                    "bbox": [round(float(v), 2) for v in span.get("bbox", [])],
                })
                texts.append(value)
            line_text = "".join(texts).strip()
            if line_text:
                result.append({
                    "text": line_text,
                    "bbox": [round(float(v), 2) for v in line.get("bbox", [])],
                    "segments": segments,
                })
    return result


def _image_coverage(page: Any) -> tuple[float, int]:
    """페이지 내 이미지가 차지하는 대략적인 면적 비율과 이미지 수를 계산합니다."""
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    rects = []
    try:
        for image in page.get_images(full=True):
            xref = image[0]
            rects.extend(page.get_image_rects(xref))
    except Exception:
        return 0.0, 0
    # 겹치는 이미지가 있을 수 있어 합산 비율은 1.0에서 제한합니다.
    covered = sum(max(0.0, float(rect.width * rect.height)) for rect in rects)
    return min(covered / page_area, 1.0), len(rects)


def _printed_page_number(text: str) -> str | None:
    """문서에 인쇄된 쪽수 후보를 추출합니다. PDF 페이지 번호와 별도로 보관합니다."""
    patterns = [
        r"(?:^|\n)\s*[-–]\s*(\d{1,4})\s*[-–]\s*(?:\n|$)",
        r"법제처\s*(\d{1,4})\s*국가법령정보센터",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            return match.group(1)
    return None


def _try_ocr(page: Any, language: str, dpi: int) -> tuple[str | None, str | None]:
    """Tesseract가 설치된 경우 이미지 영역의 글자를 OCR합니다."""
    if shutil.which("tesseract") is None:
        return None, "Tesseract 실행 파일을 찾지 못했습니다. OCR이 필요한 페이지는 원본 확인 대상으로 남겼습니다."
    try:
        text_page = page.get_textpage_ocr(language=language, dpi=dpi, full=False)
        value = page.get_text("text", textpage=text_page, sort=True).strip()
        if not value:
            return None, "OCR을 실행했지만 인식된 텍스트가 없습니다."
        return value, None
    except Exception as exc:
        return None, f"OCR 실패: {type(exc).__name__}: {exc}"


def parse_pdf(
    path: Path,
    metadata: dict[str, Any] | None = None,
    min_text_chars: int = 20,
    extract_tables: bool = True,
    enable_ocr: bool = True,
    ocr_language: str = "kor+eng",
    ocr_dpi: int = 250,
    ocr_image_coverage: float = 0.05,
) -> dict[str, Any]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF 파싱에는 PyMuPDF가 필요합니다. pip install PyMuPDF") from exc

    document = _base_document(path, metadata or {}, "pdf")
    table_pages: dict[int, list[list[list[str]]]] = {}

    if extract_tables:
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                for page_number, page in enumerate(pdf.pages, start=1):
                    extracted = []
                    for table in page.extract_tables() or []:
                        cleaned = _clean_table(table)
                        if cleaned:
                            extracted.append(cleaned)
                    if extracted:
                        table_pages[page_number] = extracted
        except Exception as exc:
            document["warnings"].append(
                f"표 추출 경고: {type(exc).__name__}: {exc}. 본문 텍스트는 별도로 추출했습니다."
            )

    with pymupdf.open(path) as pdf:
        if pdf.is_encrypted and not pdf.authenticate(""):
            raise ValueError("암호가 설정된 PDF입니다. 암호를 해제한 사본을 사용하세요.")
        document["page_count"] = pdf.page_count

        for page_number, page in enumerate(pdf, start=1):
            native_text = (page.get_text("text", sort=True) or "").replace("\x00", "").strip()
            styled_lines = _extract_styled_lines(page)
            image_ratio, image_count = _image_coverage(page)
            tables = table_pages.get(page_number, [])
            text = native_text
            warnings = []
            ocr_status = "not_needed"
            extraction_method = "pymupdf"

            # 이미지 면적이 있고 원문 텍스트가 적은 페이지에만 선택적으로 OCR합니다.
            should_ocr = (
                enable_ocr
                and image_count > 0
                and image_ratio >= ocr_image_coverage
            )
            if should_ocr:
                ocr_text, ocr_warning = _try_ocr(page, ocr_language, ocr_dpi)
                if ocr_text:
                    text = ocr_text
                    extraction_method = "pymupdf+ocr"
                    ocr_status = "success"
                else:
                    ocr_status = "failed"
                    warnings.append(ocr_warning or "OCR 결과가 비어 있습니다.")
            elif image_count > 0 and image_ratio >= ocr_image_coverage and not enable_ocr:
                ocr_status = "disabled"
                warnings.append("본문과 별개로 이미지 영역에 텍스트가 있을 수 있으나 OCR이 비활성화되어 있습니다.")

            # 제목만 있는 구분 페이지와 실제 빈 페이지를 다르게 기록합니다.
            if not text and not tables and image_count == 0:
                try:
                    has_drawings = bool(page.get_drawings())
                except Exception:
                    has_drawings = False
                page_type = "blank" if not has_drawings else "graphic_or_blank"
            elif len(text) < 100 and text:
                page_type = "section_divider"
            elif not text and image_count > 0:
                page_type = "image_content_unreadable"
                if not warnings:
                    warnings.append("이미지 영역에서 텍스트를 추출하지 못했습니다. OCR 또는 원본 검토가 필요합니다.")
            else:
                page_type = "content"

            if page_type == "blank":
                # 실제 빈 페이지는 오류나 OCR 대상으로 처리하지 않습니다.
                ocr_status = "not_applicable"

            document["pages"].append({
                "page_number": page_number,
                "printed_page_number": _printed_page_number(text or native_text),
                "section_number": None,
                "page_type": page_type,
                "text": text,
                "native_text": native_text,
                "styled_lines": styled_lines,
                "tables": tables,
                "char_count": len(text),
                "native_char_count": len(native_text),
                "image_count": image_count,
                "image_coverage": round(image_ratio, 4),
                "ocr_status": ocr_status,
                "ocr_language": ocr_language if ocr_status in {"success", "failed"} else None,
                "extraction_method": extraction_method,
                "warnings": warnings,
            })

    if not document["pages"]:
        document["warnings"].append("PDF에서 페이지를 추출하지 못했습니다.")
    document["ocr_summary"] = {
        "attempted_pages": sum(p["ocr_status"] in {"success", "failed"} for p in document["pages"]),
        "successful_pages": sum(p["ocr_status"] == "success" for p in document["pages"]),
        "failed_pages": sum(p["ocr_status"] == "failed" for p in document["pages"]),
        "blank_pages": sum(p["page_type"] == "blank" for p in document["pages"]),
        "section_divider_pages": sum(p["page_type"] == "section_divider" for p in document["pages"]),
    }
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
                    cells.append(re.sub(r"\s+", " ", _element_text(cell)).strip())
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return "\n".join(paragraphs), tables


def parse_hwpx(path: Path, metadata: dict[str, Any] | None = None,
               min_text_chars: int = 20) -> dict[str, Any]:
    document = _base_document(path, metadata or {}, "hwpx")
    try:
        with zipfile.ZipFile(path) as archive:
            section_names = [
                name for name in archive.namelist()
                if re.fullmatch(r"Contents/section\d+\.xml", name, flags=re.IGNORECASE)
            ]
            section_names.sort(
                key=lambda name: int(re.search(r"section(\d+)", name, re.IGNORECASE).group(1))
            )
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
                    "page_type": "content" if text or tables else "blank",
                    "text": text,
                    "tables": tables,
                    "char_count": len(text),
                    "extraction_method": "hwpx_xml",
                    "warnings": warnings,
                })
    except zipfile.BadZipFile as exc:
        raise ValueError(f"유효한 HWPX 압축 문서가 아닙니다: {path}") from exc

    document["section_count"] = len(document["pages"])
    document["warnings"].append(
        "HWPX 구역은 실제 인쇄 페이지와 일치하지 않을 수 있습니다. 페이지 단위 인용은 PDF 변환본과 대조하세요."
    )
    return document


def parse_html(path: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("HTML 파싱에는 beautifulsoup4가 필요합니다.") from exc

    document = _base_document(path, metadata or {}, "html")
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()

    if soup.title and not (metadata or {}).get("title"):
        document["title"] = soup.title.get_text(" ", strip=True)

    body = soup.body or soup
    blocks = [element.get_text(" ", strip=True)
              for element in body.find_all(["h1", "h2", "h3", "h4", "p", "li"])]
    blocks = [value for value in blocks if value]
    tables = []
    for table in body.find_all("table"):
        rows = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)

    text = "\n".join(blocks)
    document["pages"].append({
        "page_number": None,
        "section_number": None,
        "page_type": "content" if text or tables else "blank",
        "text": text,
        "tables": tables,
        "char_count": len(text),
        "extraction_method": "beautifulsoup",
        "warnings": [],
    })
    document["warnings"].append(
        "HTML 문서는 고정 페이지가 없으므로 페이지 대신 문서 제목·URL·문단 위치를 인용해야 합니다."
    )
    return document


def parse_document(path: Path, metadata: dict[str, Any] | None = None,
                   min_text_chars: int = 20, extract_tables: bool = True,
                   enable_ocr: bool = True, ocr_language: str = "kor+eng",
                   ocr_dpi: int = 250) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"문서 파일이 없습니다: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path, metadata, min_text_chars, extract_tables,
                         enable_ocr, ocr_language, ocr_dpi)
    if suffix == ".hwpx":
        return parse_hwpx(path, metadata, min_text_chars)
    if suffix in {".html", ".htm"}:
        return parse_html(path, metadata)
    raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix}")
