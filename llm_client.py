"""OpenAI-compatible 최소 LLM 어댑터.

OpenAI Responses API를 사용합니다. schema가 주어지면 Structured Outputs(JSON Schema)를
강제합니다. 환경변수가 없거나 호출에 실패하면 상위 레이어가 fallback을 처리합니다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config import llm_settings


class LLMUnavailable(RuntimeError):
    pass


def configured() -> bool:
    return all(llm_settings())


def _extract_output_text(body: dict[str, Any]) -> str:
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise LLMUnavailable("LLM 응답에서 output_text를 찾지 못했습니다.")


def _parse_json_text(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("LLM 응답을 구조화 JSON으로 해석하지 못했습니다.") from exc
    if not isinstance(parsed, dict):
        raise LLMUnavailable("LLM 응답 JSON은 객체여야 합니다.")
    return parsed


def chat_json(
    *,
    system: str,
    user: str,
    schema: dict[str, Any] | None = None,
    schema_name: str = "structured_response",
    temperature: float = 0.0,
    timeout: int = 30,
) -> dict[str, Any]:
    del temperature
    key, model, base_url = llm_settings()
    if not all((key, model, base_url)):
        raise LLMUnavailable("LLM 환경변수가 설정되지 않았습니다.")

    url = base_url.rstrip("/") + "/responses"
    payload: dict[str, Any] = {
        "model": model,
        "instructions": system,
        "input": user,
    }
    if schema is not None:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
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
