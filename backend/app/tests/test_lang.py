"""Tests de la détection de langue du visiteur."""

from app.api_agent.lang import detect_language, visitor_language


def test_detect_common_languages():
    assert detect_language("What training do you offer?") == "en"
    assert detect_language("Quelles formations proposez-vous ?") == "fr"
    assert detect_language("¿Qué formaciones ofrecen?") == "es"


def test_unclear_message_returns_none():
    assert detect_language("ok") is None


def test_short_followup_uses_history():
    history = [{"role": "user", "content": "What training do you offer?"}]
    assert visitor_language("ok", history) == "en"
