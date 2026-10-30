"""AXeL RAG 지식베이스용 SQLite 저장소.

원본 문서/청크를 변경하지 않고, retrieval.load_corpus()가 만든 정규화된
검색 코퍼스를 SQLite에 적재합니다. 민원 사건 DB와 분리해 추후 공용 backend DB로
마이그레이션하기 쉽게 유지합니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import ROOT_DIR

DEFAULT_DB_PATH = ROOT_DIR / "data" / "private" / "knowledge.sqlite3"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
              chunk_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              title TEXT,
              source_type TEXT,
              issuer TEXT,
              scope TEXT,
              jurisdiction TEXT,
              locator TEXT,
              pdf_page INTEGER,
              printed_page TEXT,
              article TEXT,
              effective_from TEXT,
              effective_to TEXT,
              version_status TEXT,
              verification_status TEXT NOT NULL,
              authority_rank INTEGER,
              canonical INTEGER NOT NULL DEFAULT 1,
              text TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              indexed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_source
              ON knowledge_chunks(source_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_status
              ON knowledge_chunks(verification_status);
            CREATE INDEX IF NOT EXISTS idx_knowledge_effective
              ON knowledge_chunks(effective_from, effective_to);

            CREATE TABLE IF NOT EXISTS rag_query_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              query TEXT NOT NULL,
              as_of_date TEXT,
              jurisdiction TEXT,
              production INTEGER NOT NULL DEFAULT 0,
              top_k INTEGER NOT NULL,
              result_chunk_ids_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )


def _content_hash(item: dict[str, Any]) -> str:
    return hashlib.sha256(str(item.get("text", "")).encode("utf-8")).hexdigest()


def sync_from_corpus(
    corpus: list[dict[str, Any]],
    db_path: Path | None = None,
    *,
    prune_missing: bool = False,
) -> dict[str, int]:
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0

    deleted = 0
    with connect(db_path) as conn:
        corpus_ids = {
            str(item.get("chunk_id") or "").strip()
            for item in corpus
            if str(item.get("chunk_id") or "").strip()
        }
        if prune_missing:
            existing_ids = {
                row["chunk_id"]
                for row in conn.execute("SELECT chunk_id FROM knowledge_chunks").fetchall()
            }
            stale_ids = existing_ids - corpus_ids
            if stale_ids:
                conn.executemany(
                    "DELETE FROM knowledge_chunks WHERE chunk_id = ?",
                    [(chunk_id,) for chunk_id in stale_ids],
                )
                deleted = len(stale_ids)

        for item in corpus:
            chunk_id = str(item.get("chunk_id") or "").strip()
            source_id = str(item.get("source_id") or "").strip()
            text = str(item.get("text") or "")
            if not chunk_id or not source_id or not text:
                continue

            existed = conn.execute(
                "SELECT 1 FROM knowledge_chunks WHERE chunk_id = ?",
                (chunk_id,),
            ).fetchone() is not None

            conn.execute(
                """
                INSERT INTO knowledge_chunks (
                  chunk_id, source_id, title, source_type, issuer, scope, jurisdiction,
                  locator, pdf_page, printed_page, article, effective_from, effective_to,
                  version_status, verification_status, authority_rank, canonical, text,
                  content_sha256, metadata_json, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                  source_id=excluded.source_id,
                  title=excluded.title,
                  source_type=excluded.source_type,
                  issuer=excluded.issuer,
                  scope=excluded.scope,
                  jurisdiction=excluded.jurisdiction,
                  locator=excluded.locator,
                  pdf_page=excluded.pdf_page,
                  printed_page=excluded.printed_page,
                  article=excluded.article,
                  effective_from=excluded.effective_from,
                  effective_to=excluded.effective_to,
                  version_status=excluded.version_status,
                  verification_status=excluded.verification_status,
                  authority_rank=excluded.authority_rank,
                  canonical=excluded.canonical,
                  text=excluded.text,
                  content_sha256=excluded.content_sha256,
                  metadata_json=excluded.metadata_json,
                  indexed_at=excluded.indexed_at
                """,
                (
                    chunk_id,
                    source_id,
                    item.get("title"),
                    item.get("source_type"),
                    item.get("issuer"),
                    item.get("scope"),
                    item.get("jurisdiction"),
                    item.get("locator"),
                    item.get("pdf_page"),
                    item.get("printed_page"),
                    item.get("article"),
                    item.get("effective_from"),
                    item.get("effective_to"),
                    item.get("version_status") or item.get("status"),
                    item.get("verification_status", "pending"),
                    item.get("authority_rank"),
                    1 if item.get("canonical", True) else 0,
                    text,
                    _content_hash(item),
                    json.dumps(item, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            updated += int(existed)
            inserted += int(not existed)

    return {
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "total": inserted + updated,
    }


def sync_retrieval_corpus(
    *,
    production: bool = False,
    as_of_date: str | None = None,
    jurisdiction: str | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    from agent.retrieval import load_corpus

    corpus = load_corpus(
        production=production,
        as_of_date=as_of_date,
        jurisdiction=jurisdiction,
    )
    result = sync_from_corpus(corpus, db_path, prune_missing=True)
    result["corpus_size"] = len(corpus)
    return result


def load_chunks(db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT metadata_json FROM knowledge_chunks ORDER BY source_id, pdf_page, chunk_id"
        ).fetchall()
    return [json.loads(row["metadata_json"]) for row in rows]


def log_query(
    query: str,
    result_chunk_ids: list[str],
    *,
    as_of_date: str | None,
    jurisdiction: str | None,
    production: bool,
    top_k: int,
    db_path: Path | None = None,
) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO rag_query_log
              (query, as_of_date, jurisdiction, production, top_k,
               result_chunk_ids_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                as_of_date,
                jurisdiction,
                1 if production else 0,
                top_k,
                json.dumps(result_chunk_ids, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AXeL RAG 코퍼스를 SQLite Knowledge DB에 적재")
    parser.add_argument("--production", action="store_true", help="verified/corrected 청크만 적재")
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--jurisdiction", default=None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    result = sync_retrieval_corpus(
        production=args.production,
        as_of_date=args.as_of_date,
        jurisdiction=args.jurisdiction,
        db_path=args.db,
    )
    print(json.dumps({"db": str(args.db), **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
