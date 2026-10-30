"""하위 호환용 지식 검색 인터페이스.

신규 구현은 agent.retrieval을 사용합니다.
"""
from __future__ import annotations

from typing import Any

from .retrieval import _active_on, retrieve as _retrieve


def retrieve(
    query: str,
    top_k: int = 6,
    as_of_date: str | None = None,
    jurisdiction: str | None = None,
    include_policy: bool = True,
    production: bool = False,
    allowed_source_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    return _retrieve(
        query,
        top_k=top_k,
        as_of_date=as_of_date,
        jurisdiction=jurisdiction,
        include_policy=include_policy,
        production=production,
        allowed_source_types=allowed_source_types,
    )
