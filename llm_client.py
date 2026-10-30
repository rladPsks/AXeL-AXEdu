"""OpenAI-compatible 최소 LLM 어댑터.

특정 SDK에 의존하지 않고 /chat/completions JSON API만 사용합니다.
환경변수가 없거나 호출에 실패하면 상위 레이어가 규칙 기반 fallback으로 처리합니다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


class LLMUnavailable(RuntimeError):
    pass


def configured() -> bool:
    return bool(LLM_API_KEY and LLM_MODEL and LLM_BASE_URL)


def chat_json(*, system: str, user: str, temperature: float = 0.0, timeout: int = 20) -> dict[str, Any]:
    if not configured():
        raise LLMUnavailable("LLM 환경변수가 설정되지 않았습니다.")

    url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(f"LLM 호출 실패: {type(exc).__name__}: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMUnavailable("LLM 응답을 구조화 JSON으로 해석하지 못했습니다.") from exc
