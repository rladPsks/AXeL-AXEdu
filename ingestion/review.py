"""Human-in-the-Loop 문서 검수·수정 오버레이 도구.

원본 parsed/chunks JSON은 덮어쓰지 않습니다.
제안된 수정은 human_approved=true, reviewed_by, reviewed_at을 채운 뒤
--apply-approved 옵션으로 별도 corrected_chunks 폴더에 적용합니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEGAL_ID = "LAW-TEACHER-STATUS-21350"
OFFICIAL_21655 = (
    "https://www.law.go.kr/LSW/lsInfoP.do?"
    "ancNo=21655&ancYd=20260519&efYd=20261120&lsiSeq=286085"
)
OFFICIAL_21717 = (
    "https://www.law.go.kr/LSW/lsInfoP.do?"
    "lsiSeq=286357"
)

ARTICLE_18_TRANSITION = (
    "제2조(교권보호위원회 위원 구성에 관한 경과조치) "
    "① 이 법 시행 이후 시ㆍ도교권보호위원회 또는 지역교권보호위원회의 "
    "위원을 각각 위촉 또는 임명할 당시 제18조제3항의 개정규정을 충족하지 "
    "못하는 경우에는 해당 개정규정의 요건이 충족될 때까지 관할 학교의 "
    "교사인 위원을 임명하여야 한다.\n"
    "② 시ㆍ도교권보호위원회 또는 지역교권보호위원회의 위원 구성에 관하여는 "
    "제1항에 따라 제18조제3항의 개정규정을 충족할 때까지는 종전의 규정에 따른다."
)

ARTICLE_29_TRANSITION = (
    "제2조(교육활동보호센터에 대한 경과조치) "
    "이 법 시행 당시 관할청이 설치ㆍ운영 중인 교육활동보호센터는 "
    "제29조제1항의 개정규정에 따라 설치된 교육활동보호센터로 본다."
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    path.write_text(content, encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} {line_no}행 JSON 오류: {exc}") from exc
    return rows


def _chunk_fingerprint(chunk: dict[str, Any]) -> str:
    return hashlib.sha256(
        str(chunk.get("text", "")).encode("utf-8")
    ).hexdigest()


def _priority(chunk: dict[str, Any]) -> tuple[str, str]:
    text = str(chunk.get("text", ""))
    high_terms = (
        "7일", "14일", "3회", "민원대응팀", "교원119",
        "교육지원청", "폭언", "협박", "긴급", "이관",
    )
    if chunk.get("source_type") == "law" or any(term in text for term in high_terms):
        return "high", "법적 기준·담당·기한·위험 신호이므로 원문 대조 우선"
    return "normal", "일반 내용 및 출처·쪽수 확인"


def _propose_law_overrides(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    law_chunks = [
        chunk for chunk in chunks
        if chunk.get("document_id") == LEGAL_ID
    ]
    proposals: list[dict[str, Any]] = []
    now = "2026-10-30"

    # 제18조: 개정 조문은 신설 제3항의 문구로 식별합니다.
    article18 = [c for c in law_chunks if str(c.get("article_number")) == "18"]
    future18 = [
        c for c in article18
        if "10분의 2 이상" in str(c.get("text", ""))
        or "전체 위원 정수" in str(c.get("text", ""))
    ]
    current18 = [c for c in article18 if c not in future18]

    for chunk in current18:
        proposals.append({
            "proposal_id": f"LAW18-CURRENT-{chunk['chunk_id']}",
            "operation": "update_chunk",
            "document_id": LEGAL_ID,
            "chunk_id": chunk["chunk_id"],
            "expected_text_sha256": _chunk_fingerprint(chunk),
            "human_approved": False,
            "proposed_updates": {
                "version_status": "in_force",
                "effective_from": "2026-02-19",
                "effective_to": "2026-11-19",
                "version_group": f"{LEGAL_ID}:18",
                "verification_status": "pending",
                "review_basis": "법률 제21655호 부칙 제1조 및 시행일 2026-11-20",
                "official_source_url": OFFICIAL_21655,
            },
            "review_note": "현행 제18조(신설 제3항의 교사위원 20% 요건이 없는 버전).",
        })

    for chunk in future18:
        proposals.append({
            "proposal_id": f"LAW18-FUTURE-{chunk['chunk_id']}",
            "operation": "update_chunk",
            "document_id": LEGAL_ID,
            "chunk_id": chunk["chunk_id"],
            "expected_text_sha256": _chunk_fingerprint(chunk),
            "human_approved": False,
            "proposed_updates": {
                "version_status": "scheduled",
                "effective_from": "2026-11-20",
                "effective_to": None,
                "revision_effective_from": "2026-11-20",
                "version_group": f"{LEGAL_ID}:18",
                "verification_status": "corrected",
                "review_basis": "법률 제21655호 제18조 및 부칙",
                "official_source_url": OFFICIAL_21655,
            },
            "review_note": "개정 제18조. 제3항의 관할 학교 교사위원 20% 이상 요건을 포함해야 함.",
        })

    if not future18:
        proposals.append({
            "proposal_id": "LAW18-MISSING-FUTURE",
            "operation": "manual_action_required",
            "document_id": LEGAL_ID,
            "article_number": "18",
            "human_approved": False,
            "review_note": "10분의 2 이상 요건을 포함한 개정 제18조 청크를 식별하지 못함. 원문 페이지와 파싱 텍스트를 재확인해야 하며 자동 추가 금지.",
            "official_source_url": OFFICIAL_21655,
        })

    # 제19조·제29조는 출력상 현행/시행 예정 분리가 확인됐으므로
    # 메타데이터를 공식 시행일에 맞춘 승인 후보로 제안합니다.
    for article_no, effective_from, act_no, source_url in [
        ("19", "2026-12-03", "21717", OFFICIAL_21717),
        ("29", "2026-12-03", "21717", OFFICIAL_21717),
    ]:
        for chunk in law_chunks:
            if str(chunk.get("article_number")) != article_no:
                continue
            scheduled = chunk.get("version_status") == "scheduled"
            updates = {
                "version_status": "scheduled" if scheduled else "in_force",
                "effective_from": effective_from if scheduled else "2026-02-19",
                "effective_to": None if scheduled else "2026-12-02",
                "revision_effective_from": effective_from if scheduled else None,
                "version_group": f"{LEGAL_ID}:{article_no}",
                "verification_status": "corrected",
                "review_basis": f"법률 제{act_no}호 부칙 제1조",
                "official_source_url": source_url,
            }
            proposals.append({
                "proposal_id": f"LAW{article_no}-{updates['version_status'].upper()}-{chunk['chunk_id']}",
                "operation": "update_chunk",
                "document_id": LEGAL_ID,
                "chunk_id": chunk["chunk_id"],
                "expected_text_sha256": _chunk_fingerprint(chunk),
                "human_approved": False,
                "proposed_updates": updates,
                "review_note": f"제{article_no}조 원문 대조 후 시행일 메타데이터 승인 후보.",
            })

    # 제21655호 부칙의 경과조치는 원 PDF의 원문 위치와 동일한 자료에서 확인되지 않았으므로
    # 별도 공식 원문 자료로 추가할지 사람이 승인하도록 제안만 기록합니다.
    proposals.append({
        "proposal_id": "LAW21655-ADD-TRANSITION-ARTICLE-18",
        "operation": "add_chunk",
        "document_id": "LAW-TEACHER-STATUS-AMENDMENT-21655",
        "human_approved": False,
        "proposed_chunk": {
            "document_id": "LAW-TEACHER-STATUS-AMENDMENT-21655",
            "title": "교원의 지위 향상 및 교육활동 보호를 위한 특별법 일부개정법률",
            "source_type": "law",
            "issuer": "국가법령정보센터",
            "jurisdiction": "national",
            "published_at": "2026-05-19",
            "effective_from": "2026-11-20",
            "official_url": OFFICIAL_21655,
            "chunk_type": "law_transitional_provision",
            "section_title": "제2조(교권보호위원회 위원 구성에 관한 경과조치)",
            "locator": "부칙 제2조",
            "page_start": None,
            "page_end": None,
            "text": ARTICLE_18_TRANSITION,
            "article_number": None,
            "version_status": "scheduled",
            "effective_from": "2026-11-20",
            "effective_to": None,
            "verification_status": "corrected",
            "requires_review": False,
        },
        "review_note": "원 PDF의 인쇄 쪽수·페이지와 혼동하지 않도록 별도 개정법 출처로 등록한 뒤 승인.",
    })
    proposals.append({
        "proposal_id": "LAW21717-ADD-TRANSITION-ARTICLE-29",
        "operation": "add_chunk",
        "document_id": "LAW-TEACHER-STATUS-AMENDMENT-21717",
        "human_approved": False,
        "proposed_chunk": {
            "document_id": "LAW-TEACHER-STATUS-AMENDMENT-21717",
            "title": "교원의 지위 향상 및 교육활동 보호를 위한 특별법 일부개정법률",
            "source_type": "law",
            "issuer": "국가법령정보센터",
            "jurisdiction": "national",
            "published_at": "2026-06-02",
            "effective_from": "2026-12-03",
            "official_url": OFFICIAL_21717,
            "chunk_type": "law_transitional_provision",
            "section_title": "제2조(교육활동보호센터에 대한 경과조치)",
            "locator": "부칙 제2조",
            "page_start": None,
            "page_end": None,
            "text": ARTICLE_29_TRANSITION,
            "article_number": None,
            "version_status": "scheduled",
            "effective_from": "2026-12-03",
            "effective_to": None,
            "verification_status": "pending",
            "requires_review": False,
        },
        "review_note": "법률 제21717호 부칙 제2조의 경과조치. 별도 개정법 원문 출처로 등록한 뒤 승인.",
    })

    return proposals


def build_review_package(
    parsed_dir: Path = Path("documents/parsed"),
    chunks_dir: Path = Path("documents/chunks"),
    review_dir: Path = Path("documents/review"),
) -> dict[str, Any]:
    parsed_files = sorted(parsed_dir.glob("*.parsed.json"))
    chunk_files = sorted(chunks_dir.glob("*.chunks.json"))
    if not parsed_files or not chunk_files:
        raise FileNotFoundError("parsed/chunks 산출물이 없습니다. 먼저 파싱 파이프라인을 실행하세요.")

    parsed_docs = {_read_json(path).get("document_id"): _read_json(path) for path in parsed_files}
    chunk_docs = [_read_json(path) for path in chunk_files]
    all_chunks = [chunk for doc in chunk_docs for chunk in doc.get("chunks", [])]

    queue: list[dict[str, Any]] = []
    for doc_id, document in parsed_docs.items():
        for page in document.get("pages", []):
            ocr_status = page.get("ocr_status", "not_applicable")
            if ocr_status in {"success", "failed", "disabled"} or page.get("warnings"):
                queue.append({
                    "review_id": f"PAGE-{doc_id}-{page.get('page_number')}",
                    "item_type": "page",
                    "document_id": doc_id,
                    "page_number": page.get("page_number"),
                    "page_type": page.get("page_type"),
                    "extraction_method": page.get("extraction_method"),
                    "ocr_status": ocr_status,
                    "native_char_count": page.get("native_char_count"),
                    "final_char_count": page.get("char_count"),
                    "image_coverage": page.get("image_coverage"),
                    "review_status": "pending",
                    "review_reason": "OCR 결과 및 이미지/원문 대조",
                })

    for chunk in all_chunks:
        priority, reason = _priority(chunk)
        queue.append({
            "review_id": f"CHUNK-{chunk.get('chunk_id')}",
            "item_type": "chunk",
            "document_id": chunk.get("document_id"),
            "chunk_id": chunk.get("chunk_id"),
            "locator": chunk.get("locator"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "chunk_type": chunk.get("chunk_type"),
            "priority": priority,
            "review_status": "pending",
            "review_reason": reason,
            "source_text_sha256": _chunk_fingerprint(chunk),
        })

    proposals = _propose_law_overrides(all_chunks)
    review_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(review_dir / "human_review_queue.jsonl", queue)
    _write_jsonl(review_dir / "proposed_overrides.jsonl", proposals)

    summary_docs = []
    for doc_id, document in parsed_docs.items():
        doc_chunks = [c for c in all_chunks if c.get("document_id") == doc_id]
        summary_docs.append({
            "document_id": doc_id,
            "title": document.get("title"),
            "file_name": document.get("file_name"),
            "file_sha256": document.get("file_sha256"),
            "page_count": len(document.get("pages", [])),
            "chunk_count": len(doc_chunks),
            "ocr_summary": document.get("ocr_summary", {}),
            "source_warnings": document.get("warnings", []),
        })

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_policy": "Human approval is required before overrides enter the RAG index.",
        "documents": summary_docs,
        "review_queue_count": len(queue),
        "proposed_override_count": len(proposals),
        "human_approved_override_count": 0,
        "rag_ready": False,
        "note": "파싱 성공은 사실 정확성 승인과 다릅니다. pending 항목은 RAG 인덱스에 포함하지 않습니다.",
    }
    _write_json(review_dir / "review_summary.json", summary)
    return summary


def apply_approved_overrides(
    chunks_dir: Path = Path("documents/chunks"),
    review_dir: Path = Path("documents/review"),
) -> dict[str, Any]:
    """사람이 승인하고 서명 정보를 기입한 오버라이드만 별도 파일에 적용합니다."""
    proposals = _read_jsonl(review_dir / "proposed_overrides.jsonl")
    approved = [
        row for row in proposals
        if row.get("human_approved") is True
        and row.get("reviewed_by")
        and row.get("reviewed_at")
    ]
    if not approved:
        raise ValueError(
            "승인된 오버라이드가 없습니다. proposed_overrides.jsonl에서 "
            "human_approved=true, reviewed_by, reviewed_at을 입력하세요."
        )

    files = sorted(chunks_dir.glob("*.chunks.json"))
    documents = {path: _read_json(path) for path in files}
    by_doc = {doc.get("document_id"): (path, doc) for path, doc in documents.items()}
    applied = []

    for proposal in approved:
        operation = proposal.get("operation")
        if operation == "manual_action_required":
            continue
        if operation == "update_chunk":
            match = None
            target_doc = None
            for path, doc in documents.items():
                for chunk in doc.get("chunks", []):
                    if chunk.get("chunk_id") == proposal.get("chunk_id"):
                        match, target_doc = chunk, doc
                        break
                if match:
                    break
            if match is None:
                raise KeyError(f"수정 대상 청크를 찾지 못했습니다: {proposal.get('chunk_id')}")
            if _chunk_fingerprint(match) != proposal.get("expected_text_sha256"):
                raise ValueError(f"원문 청크가 제안 이후 변경되었습니다: {proposal.get('chunk_id')}")
            match.update(proposal.get("proposed_updates", {}))
            match["verification_status"] = "corrected"
            match["human_approval"] = {
                "status": "approved",
                "reviewed_by": proposal["reviewed_by"],
                "reviewed_at": proposal["reviewed_at"],
                "review_note": proposal.get("review_note"),
                "proposal_id": proposal.get("proposal_id"),
            }
            applied.append(proposal["proposal_id"])
        elif operation == "add_chunk":
            proposed_chunk = dict(proposal["proposed_chunk"])
            digest = hashlib.sha256(
                (proposed_chunk["document_id"] + proposed_chunk["locator"] + proposed_chunk["text"]).encode("utf-8")
            ).hexdigest()[:12]
            proposed_chunk["chunk_id"] = digest
            proposed_chunk["verification_status"] = "corrected"
            proposed_chunk["human_approval"] = {
                "status": "approved",
                "reviewed_by": proposal["reviewed_by"],
                "reviewed_at": proposal["reviewed_at"],
                "review_note": proposal.get("review_note"),
                "proposal_id": proposal.get("proposal_id"),
            }
            target_path = chunks_dir / "LAW-TEACHER-STATUS-AMENDMENT-21655.chunks.human-reviewed.json"
            target_doc = by_doc.get(proposed_chunk["document_id"], (None, None))[1]
            if target_doc is None:
                target_doc = {
                    "document_id": proposed_chunk["document_id"],
                    "document_title": proposed_chunk["title"],
                    "source_type": "law",
                    "chunks": [],
                    "chunk_count": 0,
                    "human_reviewed_source": True,
                }
                documents[target_path] = target_doc
            target_doc["chunks"].append(proposed_chunk)
            target_doc["chunk_count"] = len(target_doc["chunks"])
            applied.append(proposal["proposal_id"])

    output_dir = review_dir / "corrected_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, doc in documents.items():
        if path.name.endswith(".human-reviewed.json") or any(
            c.get("human_approval", {}).get("status") == "approved"
            for c in doc.get("chunks", [])
        ):
            output_path = output_dir / path.name.replace(".chunks.json", ".human-reviewed.json")
            _write_json(output_path, doc)

    application_log = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "applied_proposal_ids": applied,
        "applied_count": len(applied),
        "output_dir": str(output_dir),
        "original_chunks_modified": False,
    }
    _write_json(review_dir / "application_log.json", application_log)
    return application_log


def main() -> None:
    parser = argparse.ArgumentParser(description="AXeL Human-in-the-Loop 문서 검수 도구")
    parser.add_argument("--apply-approved", action="store_true", help="사람이 승인한 수정만 별도 산출물에 적용")
    parser.add_argument("--parsed", type=Path, default=Path("documents/parsed"))
    parser.add_argument("--chunks", type=Path, default=Path("documents/chunks"))
    parser.add_argument("--review", type=Path, default=Path("documents/review"))
    args = parser.parse_args()

    if args.apply_approved:
        result = apply_approved_overrides(args.chunks, args.review)
    else:
        result = build_review_package(args.parsed, args.chunks, args.review)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
