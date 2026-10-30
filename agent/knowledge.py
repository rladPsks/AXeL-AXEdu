"""법령·정책·매뉴얼의 출처 유형과 시행일을 고려하는 초기 검색기."""
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
    """시행일 기준으로 현행 조문인지 확인합니다."""
    start = chunk.get("effective_from")
    end = chunk.get("effective_to")
    status = str(chunk.get("status", "in_force"))
    if start and str(start) > on_date:
        return False
    if end and str(end) < on_date:
        return False
    if status == "scheduled" and (not start or str(start) > on_date):
        return False
    return True


def _all_chunks(as_of_date: str) -> list[dict[str, Any]]:
    legal = _load_chunks("legal_chunks.json")
    manual = _load_chunks("manual_chunks.json")
    policy = _load_chunks("policy_chunks.json")
    registry_path = DATA_DIR / "source_registry.json"
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    registry = {item["source_id"]: item for item in registry_payload.get("sources", [])}

    merged = []
    for item in legal + manual + policy:
        source = registry.get(item.get("source_id"), {})
        merged_item = {**item}
        for key in ("source_title", "issuer", "official_url", "effective_from", "effective_to", "status"):
            if merged_item.get(key) is None and source.get(key) is not None:
                merged_item[key] = source[key]
        merged_item.setdefault("source_type", source.get("source_type", "official_manual"))

        if merged_item["source_type"] in {"law", "decree", "law_amendment_scheduled", "ordinance", "local_rule"}:
            if _active_on(merged_item, as_of_date):
                merged.append(merged_item)
        else:
            merged.append(merged_item)
    return merged


def retrieve(query: str, top_k: int = 6, as_of_date: str | None = None,
             jurisdiction: str | None = None, include_policy: bool = True) -> list[dict[str, Any]]:
    """현행 법령 및 실무 근거를 검색합니다. 검색 결과는 반드시 원문과 대조해야 합니다."""
    if not query.strip():
        return []

    effective_date = as_of_date or date.today().isoformat()
    query_terms = tokenize(query)
    scored = []

    for chunk in _all_chunks(effective_date):
        if not include_policy and chunk.get("source_type") in {"policy_plan", "press_release_statistics"}:
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

        multiplier = {
            "law": 1.25,
            "law_amendment_scheduled": 1.25,
            "decree": 1.18,
            "local_rule": 1.12,
            "official_manual": 1.0,
            "school_policy": 1.05,
            "policy_plan": 0.82,
            "press_release_statistics": 0.65,
        }.get(chunk.get("source_type", ""), 0.9)
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
