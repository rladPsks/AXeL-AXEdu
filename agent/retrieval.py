"""검수 상태·시행일·출처 우선순위를 고려하는 AXeL 1차 RAG 검색 엔진.

외부 벡터 DB 없이도 동작하는 문자 bigram BM25 검색기입니다.
HITL 수정본이 있으면 원본보다 우선하여 읽고, 같은 청크의 중복 결과를 제거합니다.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR, ROOT_DIR

CHUNKS_DIR = ROOT_DIR / "documents" / "chunks"
CORRECTED_DIR = ROOT_DIR / "documents" / "review" / "corrected_chunks"
CONTRACTS_DIR = ROOT_DIR / "contracts"

LAW_TYPES = {"law", "decree", "law_amendment_scheduled", "ordinance", "local_rule"}
AUTHORITY = {
    "law": 1,
    "decree": 2,
    "local_rule": 3,
    "official_manual": 4,
    "school_policy": 5,
    "policy_plan": 6,
    "press_release_statistics": 6,
    "legacy_operational_guidance": 6,
    "fixture": 7,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _active_on(chunk: dict[str, Any], on_date: str) -> bool:
    start = chunk.get("effective_from")
    end = chunk.get("effective_to")
    status = str(chunk.get("version_status") or chunk.get("status") or "in_force")
    if start and str(start) > on_date:
        return False
    if end and str(end) < on_date:
        return False
    if status == "scheduled" and (not start or str(start) > on_date):
        return False
    if status == "expired":
        return False
    return True


def _char_bigrams(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    chars = [ch for ch in normalized if ch.isalnum() or "가" <= ch <= "힣"]
    if len(chars) < 2:
        return chars
    return ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]


def _registry() -> dict[str, dict[str, Any]]:
    path = DATA_DIR / "source_registry.json"
    if not path.exists():
        return {}
    registry: dict[str, dict[str, Any]] = {}
    for source in _read_json(path).get("sources", []):
        registry[source["source_id"]] = source
        for alias in source.get("source_aliases", []):
            registry[str(alias)] = source
    return registry


def _allowlist() -> dict[str, Any]:
    path = DATA_DIR / "rag_allowlist_v1.json"
    return _read_json(path) if path.exists() else {"sources": {}}


def _load_chunk_files(folder: Path) -> list[dict[str, Any]]:
    if not folder.exists():
        return []
    chunks: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            payload = _read_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        chunks.extend(payload.get("chunks", []))
    return chunks


def _legacy_chunks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    legacy_defaults = {
        "legal_chunks.json": None,
        "manual_chunks.json": "MOE-MANUAL-2026",
        "policy_chunks.json": None,
    }
    for name, default_source_id in legacy_defaults.items():
        path = DATA_DIR / name
        if not path.exists():
            continue
        for raw in _read_json(path).get("chunks", []):
            item = dict(raw)
            if default_source_id and not item.get("source_id"):
                item["source_id"] = default_source_id
            out.append(item)
    return out


def _normalize_chunk(raw: dict[str, Any], registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item = dict(raw)
    if not item.get("chunk_id") and item.get("id"):
        item["chunk_id"] = item["id"]
    source_id = item.get("source_id") or item.get("document_id")
    source = registry.get(source_id, {})
    canonical_source_id = source.get("source_id") or source_id
    item["source_id"] = canonical_source_id
    item["document_id"] = canonical_source_id
    item.setdefault("title", source.get("title") or item.get("document_title"))
    item.setdefault("issuer", source.get("issuer"))
    item.setdefault("source_type", source.get("source_type", "official_manual"))
    item.setdefault("official_url", source.get("official_url"))
    item.setdefault("effective_from", source.get("effective_from"))
    item.setdefault("effective_to", source.get("effective_to"))
    item.setdefault("scope", "national" if item.get("jurisdiction") in {None, "national"} else "local")
    item.setdefault("jurisdiction", source.get("jurisdiction", "national"))
    item.setdefault("pdf_page", item.get("page_start") or item.get("page"))
    item.setdefault("printed_page", item.get("printed_page_number"))
    item.setdefault("article", item.get("section_title") if item.get("chunk_type") == "law_article" else None)
    item.setdefault("retrieval_tags", item.get("tags") or [])
    item.setdefault("verification_status", "pending")
    item.setdefault("authority_rank", AUTHORITY.get(item.get("source_type"), 8))
    item.setdefault("canonical", True)
    return item


def load_corpus(*, production: bool = False, as_of_date: str | None = None,
                jurisdiction: str | None = None,
                allowed_source_types: set[str] | None = None) -> list[dict[str, Any]]:
    effective_date = as_of_date or date.today().isoformat()
    registry = _registry()
    allow = _allowlist().get("sources", {})

    # 원본 -> HITL 수정본 순서로 읽어 같은 chunk_id를 수정본이 덮어쓰게 합니다.
    combined = _load_chunk_files(CHUNKS_DIR) or _legacy_chunks()
    corrected = _load_chunk_files(CORRECTED_DIR)
    by_id: dict[str, dict[str, Any]] = {}
    for raw in combined + corrected:
        item = _normalize_chunk(raw, registry)
        key = str(item.get("chunk_id") or f'{item.get("source_id")}:{item.get("locator")}:{hash(item.get("text", ""))}')
        by_id[key] = item

    result = []
    for item in by_id.values():
        status = item.get("verification_status", "pending")
        if status == "rejected":
            continue
        if production and status not in {"verified", "corrected"}:
            continue
        if item.get("source_type") in LAW_TYPES and not _active_on(item, effective_date):
            continue
        if jurisdiction and item.get("jurisdiction") not in {None, "national", jurisdiction}:
            continue
        if allowed_source_types is not None and item.get("source_type") not in allowed_source_types:
            continue

        source_cfg = allow.get(item.get("source_id"), {})
        canonical_locators = source_cfg.get("canonical_locators")
        reject_locators = set(source_cfg.get("reject_locators", []))
        locator = item.get("locator")
        if locator in reject_locators:
            continue
        if canonical_locators is not None and locator not in canonical_locators:
            # 1차 RAG에서는 검수 우선 청크만 사용. production에서도 verified 청크는 허용.
            if not (production and status in {"verified", "corrected"}):
                continue

        result.append(item)

    # 파서 재실행 전 남아 있던 별칭/중복 청크까지 canonical source 기준으로 제거합니다.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in result:
        dedup_key = (
            str(item.get("source_id")),
            str(item.get("locator", "")).replace("-table1", "").replace("-table2", ""),
            re.sub(r"\s+", "", str(item.get("text", ""))),
        )
        current = unique.get(dedup_key)
        if current is None:
            unique[dedup_key] = item
            continue
        # 검수 완료본과 canonical id가 더 높은 우선순위를 가집니다.
        current_verified = current.get("verification_status") in {"verified", "corrected"}
        item_verified = item.get("verification_status") in {"verified", "corrected"}
        if item_verified and not current_verified:
            unique[dedup_key] = item
    return list(unique.values())


def retrieve(query: str, top_k: int = 6, *, production: bool = False,
             as_of_date: str | None = None, jurisdiction: str | None = None,
             include_policy: bool = True,
             allowed_source_types: set[str] | None = None) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    corpus = load_corpus(
        production=production,
        as_of_date=as_of_date,
        jurisdiction=jurisdiction,
        allowed_source_types=allowed_source_types,
    )
    if not include_policy:
        corpus = [c for c in corpus if c.get("source_type") not in {"policy_plan", "press_release_statistics", "legacy_operational_guidance"}]
    if not corpus:
        return []

    query_tokens = _char_bigrams(query)
    if not query_tokens:
        return []

    tokenized = [_char_bigrams(
        " ".join([
            str(c.get("title") or ""),
            str(c.get("section_title") or ""),
            str(c.get("text") or ""),
            " ".join(c.get("retrieval_tags", [])),
        ])
    ) for c in corpus]

    n_docs = len(corpus)
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized:
        doc_freq.update(set(tokens))

    avg_len = sum(len(x) for x in tokenized) / max(n_docs, 1)
    k1, b = 1.5, 0.75
    q_counts = Counter(query_tokens)
    scored: list[tuple[float, dict[str, Any]]] = []

    for item, tokens in zip(corpus, tokenized):
        tf = Counter(tokens)
        score = 0.0
        for term, qf in q_counts.items():
            if term not in tf:
                continue
            df = doc_freq[term]
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * len(tokens) / max(avg_len, 1))
            score += idf * (freq * (k1 + 1) / denom) * min(qf, 2)

        if score <= 0:
            continue

        # 상위 규범 근거를 같은 lexical score에서 우선합니다.
        authority_bonus = 1.0 + max(0, 7 - int(item.get("authority_rank", 8))) * 0.05
        source_type = item.get("source_type")
        source_multiplier = {
            "law": 1.18,
            "decree": 1.15,
            "official_manual": 1.12,
            "local_rule": 1.08,
            "school_policy": 1.05,
            "policy_plan": 0.98,
            "press_release_statistics": 0.88,
            "legacy_operational_guidance": 0.72,
        }.get(source_type, 1.0)
        if item.get("verification_status") in {"verified", "corrected"}:
            authority_bonus *= 1.08
        scored.append((score * authority_bonus * source_multiplier, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    # 같은 source/locator/text가 body/table로 중복된 경우 하나만 반환합니다.
    seen: set[tuple[str, str, str]] = set()
    per_source_count: Counter[str] = Counter()
    results = []
    effective_date = as_of_date or date.today().isoformat()
    for score, item in scored:
        dedup = (
            str(item.get("source_id")),
            str(item.get("locator", "")).replace("-table1", "").replace("-table2", ""),
            re.sub(r"\s+", "", str(item.get("text", "")))[:160],
        )
        if dedup in seen:
            continue

        source_id = str(item.get("source_id"))
        source_type = item.get("source_type")
        source_cap = 1 if source_type == "legacy_operational_guidance" else 2
        if per_source_count[source_id] >= source_cap:
            continue

        seen.add(dedup)
        per_source_count[source_id] += 1
        result = dict(item)
        result["score"] = round(score, 4)
        result["as_of_date"] = effective_date
        result["requires_human_review"] = result.get("verification_status") not in {"verified", "corrected"}
        result["citation"] = {
            "source_id": result.get("source_id"),
            "title": result.get("title"),
            "article": result.get("article"),
            "pdf_page": result.get("pdf_page"),
            "printed_page": result.get("printed_page"),
            "effective_from": result.get("effective_from"),
            "official_url": result.get("official_url"),
        }
        results.append(result)
        if len(results) >= top_k:
            break
    return results
