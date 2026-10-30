"""OpenAI-compatible 최소 LLM 어댑터.

OpenAI Responses API를 사용합니다. 환경변수가 없거나 호출에 실패하면
상위 레이어가 규칙 기반 fallback으로 처리합니다.
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


def _extract_output_text(body: dict[str, Any]) -> str:
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise LLMUnavailable("LLM 응답에서 output_text를 찾지 못했습니다.")


def _parse_json_text(text: str) -> dict[str, Any]:
    value = text.strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("LLM 응답을 구조화 JSON으로 해석하지 못했습니다.") from exc
    if not isinstance(parsed, dict):
        raise LLMUnavailable("LLM 응답 JSON은 객체여야 합니다.")
    return parsed


def chat_json(*, system: str, user: str, temperature: float = 0.0, timeout: int = 30) -> dict[str, Any]:
    del temperature
    if not configured():
        raise LLMUnavailable("LLM 환경변수가 설정되지 않았습니다.")

    url = LLM_BASE_URL.rstrip("/") + "/responses"
    payload = {
        "model": LLM_MODEL,
        "instructions": system,
        "input": user,
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
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        suffix = f" | {detail}" if detail else ""
        raise LLMUnavailable(f"LLM 호출 실패: HTTP {exc.code} {exc.reason}{suffix}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(f"LLM 호출 실패: {type(exc).__name__}: {exc}") from exc

    return _parse_json_text(_extract_output_text(body))
