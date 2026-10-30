import json
import zipfile
from pathlib import Path

from ingestion.chunker import chunk_document
from ingestion.parsers import parse_document


def test_law_chunker_keeps_article_text_and_location():
    document = {
        "document_id": "TEST-LAW",
        "title": "테스트 법령",
        "source_type": "law",
        "pages": [
            {"page_number": 1, "text": "제1조(목적) 이 법은 목적을 정한다.\\n① 첫 번째 항이다."},
            {"page_number": 2, "text": "제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다."},
        ],
        "warnings": [],
    }
    result = chunk_document(document)
    assert result["chunk_count"] == 2
    assert result["chunks"][0]["section_title"].startswith("제1조")
    assert "첫 번째 항" in result["chunks"][0]["text"]
    assert result["chunks"][1]["page_start"] == 2


def test_html_parser_extracts_text_and_tables(tmp_path: Path):
    path = tmp_path / "sample.html"
    path.write_text(
        "<html><head><title>샘플</title></head><body>"
        "<h1>학교 안내</h1><p>신청 기한은 5일입니다.</p>"
        "<table><tr><th>항목</th><th>기한</th></tr><tr><td>신청</td><td>5일</td></tr></table>"
        "<script>불필요한 스크립트</script></body></html>",
        encoding="utf-8",
    )
    parsed = parse_document(path)
    assert parsed["title"] == "샘플"
    assert "신청 기한은 5일입니다." in parsed["pages"][0]["text"]
    assert parsed["pages"][0]["tables"][0][1] == ["신청", "5일"]


def test_hwpx_parser_extracts_section_text_and_table(tmp_path: Path):
    path = tmp_path / "sample.hwpx"
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
            xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
      <hp:p><hp:run><hp:t>제1조 목적</hp:t></hp:run></hp:p>
      <hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>부서</hp:t></hp:run></hp:p></hp:tc>
      <hp:tc><hp:p><hp:run><hp:t>교무부</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>
    </hs:sec>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)
    parsed = parse_document(path)
    assert "제1조 목적" in parsed["pages"][0]["text"]
    assert parsed["pages"][0]["tables"][0][0] == ["부서", "교무부"]


def test_sidecar_metadata_is_applied(tmp_path: Path):
    path = tmp_path / "source.html"
    path.write_text("<p>내용</p>", encoding="utf-8")
    sidecar = tmp_path / "source.html.meta.json"
    sidecar.write_text(json.dumps({"source_id": "DOC-01", "source_type": "school_policy"}), encoding="utf-8")
    from ingestion.parsers import load_sidecar_metadata
    from ingestion.parsers import parse_document
    parsed = parse_document(path, load_sidecar_metadata(path))
    assert parsed["document_id"] == "DOC-01"
    assert parsed["source_type"] == "school_policy"
