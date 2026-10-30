from __future__ import annotations

import json
import re
from typing import Any

from llm_client import LLMUnavailable, chat_json


TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translated_text": {"type": "string"},
    },
    "required": ["translated_text"],
}


def detect_language_hint(text: str) -> str:
    text = str(text or "")
    if not text.strip():
        return "unknown"
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    kana = len(re.findall(r"[ぁ-んァ-ン]", text))
    cjk = len(re.findall(r"[一-龥]", text))
    total = max(1, hangul + latin + kana + cjk)
    if hangul / total >= 0.35:
        return "ko"
    if kana:
        return "ja"
    if cjk:
        return "zh"
    if latin / total >= 0.5:
        return "en"
    return "unknown"


def translate_to_korean(text: str) -> dict[str, str]:
    language = detect_language_hint(text)
    if language in {"ko", "unknown"}:
        return {
            "detected_language": language,
            "translated_text_ko": text,
            "translation_mode": "NOT_NEEDED",
        }
    try:
        result = chat_json(
            system=(
                "학교 민원 원문을 내부 처리를 위해 한국어로 정확히 번역하세요. "
                "의미를 추가·삭제하거나 위협·욕설을 완화하지 말고 원문의 강도와 요구를 보존하세요."
            ),
            user=json.dumps({"source_language": language, "text": text}, ensure_ascii=False),
            schema=TRANSLATION_SCHEMA,
            schema_name="complaint_translation_to_korean",
        )
        return {
            "detected_language": language,
            "translated_text_ko": result["translated_text"],
            "translation_mode": "LLM",
        }
    except (LLMUnavailable, ValueError, TypeError):
        return {
            "detected_language": language,
            "translated_text_ko": text,
            "translation_mode": "FALLBACK_ORIGINAL",
        }


def translate_from_korean(text: str, target_language: str) -> dict[str, str] | None:
    if not text or target_language in {"ko", "unknown", ""}:
        return None
    try:
        result = chat_json(
            system=(
                "학교의 검토용 한국어 민원 답변을 지정 언어로 정확히 번역하세요. "
                "법적 의미나 책임 범위를 바꾸지 말고, 원문에 없는 약속을 추가하지 마세요."
            ),
            user=json.dumps({"target_language": target_language, "text": text}, ensure_ascii=False),
            schema=TRANSLATION_SCHEMA,
            schema_name="complaint_response_translation",
        )
        return {
            "target_language": target_language,
            "translated_text": result["translated_text"],
            "translation_mode": "LLM",
        }
    except (LLMUnavailable, ValueError, TypeError):
        return None
