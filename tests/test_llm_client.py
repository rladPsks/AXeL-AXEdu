import json

import llm_client


class _FakeResponse:
    def __init__(self, body):
        self._body = json.dumps(body, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def test_structured_schema_is_sent_to_responses_api(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
            }]
        })

    monkeypatch.setattr(llm_client, "configured", lambda: True)
    monkeypatch.setattr(llm_client, "LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setattr(llm_client, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_client, "LLM_API_KEY", "secret")
    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    assert llm_client.chat_json(system="s", user="u", schema=schema) == {"ok": True}
    fmt = captured["payload"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["schema"] == schema
