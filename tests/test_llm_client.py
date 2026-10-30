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


def test_extracts_json_from_responses_api(monkeypatch):
    monkeypatch.setattr(llm_client, "configured", lambda: True)
    monkeypatch.setattr(llm_client, "LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setattr(llm_client, "LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_client, "LLM_API_KEY", "secret")
    monkeypatch.setattr(
        llm_client.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse({
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
            }]
        }),
    )
    assert llm_client.chat_json(system="s", user="u") == {"ok": True}
