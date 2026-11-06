"""Appel Groq : paramètres de raisonnement pour gpt-oss, réponse vide gérée."""

import pytest

from app import config, llm


class Resp:
    def __init__(self, content, finish="stop"):
        self.status_code, self.headers = 200, {}
        self._data = {"choices": [{"message": {"content": content}, "finish_reason": finish}],
                      "usage": {"completion_tokens": 2048}}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "k")
    sent = []
    monkeypatch.setattr(llm, "time", type("T", (), {"sleep": staticmethod(lambda s: None)}))
    return sent


def test_gpt_oss_gets_low_reasoning(groq, monkeypatch):
    monkeypatch.setattr(config, "GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(llm.requests, "post", lambda url, **kw: groq.append(kw["json"]) or Resp("ok"))
    assert llm.chat("sys", [{"role": "user", "content": "q"}]) == "ok"
    body = groq[-1]
    assert body["reasoning_effort"] == "low" and body["include_reasoning"] is False
    assert body["max_completion_tokens"] == config.LLM_MAX_TOKENS >= 2048


def test_other_models_have_no_reasoning_params(groq, monkeypatch):
    monkeypatch.setattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(llm.requests, "post", lambda url, **kw: groq.append(kw["json"]) or Resp("ok"))
    llm.chat("sys", [{"role": "user", "content": "q"}])
    assert "reasoning_effort" not in groq[-1]


def test_empty_reply_gives_friendly_error(groq, monkeypatch):
    monkeypatch.setattr(config, "GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(llm.requests, "post", lambda url, **kw: Resp("", finish="length"))
    with pytest.raises(llm.LLMError, match="reformulez"):
        llm.chat("sys", [{"role": "user", "content": "q"}])
