"""법령·정책·매뉴얼을 출처 유형과 시행일로 구분해 검색합니다.

현재 검색은 프로토타입용 키워드 검색입니다. 실제 운영형 RAG에서는
BM25 + 임베딩 검색 + 재정렬기를 결합하되, 아래의 시행일·지역·출처 메타데이터 필터는 유지해야 합니다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from config import DATA_DIR


def _load_chunks(filename: str, key: str = "chunks") -> list[dict[str, Any]]:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get(key, [])


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text.lower()))


def _active_on(chunk: dict[str, Any], on_date: str) -> bool:
    """시행 전 개정 조문이나 폐지된 조문이 현행 근거로 검색되지 않도록 합니다."""
    status = str(chunk.get("status", "in_force"))
    if status == "scheduled":
        # 시행 예정 조문은 기준일이 시행일에 도달한 경우에만 현행 조문으로 검색합니다.
        if not start or str(start) > on_date:
            return False
    start = chunk.get("effective_from")
    end = chunk.get("effective_to")
    if start and str(start) > on_date:
        return False
    if end and str(end) < on_date:
        return False
    return True


def _all_chunks(as_of_date: str) -> list[dict[str, Any]]:
    legal = _load_chunks("legal_chunks.json")
    manual = _load_chunks("manual_chunks.json")
    policy = _load_chunks("policy_chunks.json")
    registry_payload = {}
    registry_path = DATA_DIR / "source_registry.json"
    if registry_path.exists():
        registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = {item["source_id"]: item for item in registry_payload.get("sources", [])}

    merged = []
    for item in legal + manual + policy:
        source_id = item.get("source_id")
        source = registry.get(source_id, {})
        merged_item = {**item}
        if source:
            merged_item.setdefault("source_title", source.get("title"))
            merged_item.setdefault("issuer", source.get("issuer"))
            merged_item.setdefault("official_url", source.get("official_url"))
            merged_item.setdefault("effective_from", source.get("effective_from"))
            merged_item.setdefault("effective_to", source.get("effective_to"))
            merged_item.setdefault("status", source.get("status", "in_force"))
        merged_item.setdefault("source_type", "official_manual")
        if merged_item["source_type"] in {"law", "decree", "law_amendment_scheduled"}:
            if _active_on(merged_item, as_of_date):
                merged.append(merged_item)
        else:
            merged.append(merged_item)
    return merged


def retrieve(
    query: str,
    top_k: int = 6,
    as_of_date: str | None = None,
    jurisdiction: str | None = None,
    include_policy: bool = True,
) -> list[dict[str, Any]]:
    """질의와 관련된 현행 법령 및 실무 근거를 검색합니다.

    반환값은 인용에 필요한 법령명·조문 또는 문서명·페이지·시행일을 보존합니다.
    """
    if not query.strip():
        return []

    effective_date = as_of_date or date.today().isoformat()
    query_terms = tokenize(query)
    scored: list[tuple[float, dict[str, Any]]] = []

    for chunk in _all_chunks(effective_date):
        if not include_policy and chunk.get("source_type") in {
            "policy_plan", "press_release_statistics"
        }:
            continue
        chunk_jurisdiction = chunk.get("jurisdiction")
        if jurisdiction and chunk_jurisdiction not in {None, jurisdiction, "national"}:
            continue

        searchable = " ".join([
            str(chunk.get("title", "")),
            str(chunk.get("text", "")),
            str(chunk.get("citation", "")),
            " ".join(chunk.get("tags", [])),
        ])
        doc_terms = tokenize(searchable)
        overlap = len(query_terms & doc_terms) / max(1, len(query_terms))
        if overlap <= 0:
            continue

        source_type = chunk.get("source_type", "")
        # 법령은 일반 정책 설명보다 우선하되, 검색어와의 관련성이 낮으면 상위에 고정하지 않습니다.
        multiplier = {
            "law": 1.25,
            "law_amendment_scheduled": 1.25,
            "decree": 1.18,
            "local_rule": 1.12,
            "official_manual": 1.0,
            "school_policy": 1.05,
            "policy_plan": 0.82,
            "press_release_statistics": 0.65,
        }.get(source_type, 0.9)
        scored.append((overlap * multiplier, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, chunk in scored[:top_k]:
        result = dict(chunk)
        result["score"] = round(score, 3)
        result["as_of_date"] = effective_date
        result["citation_label"] = (
            f'{chunk.get("citation")} · 시행 {chunk.get("effective_from")}'
            if chunk.get("citation")
            else f'{chunk.get("source_title", chunk.get("title"))} · p.{chunk.get("page")}'
        )
        results.append(result)
    return results
