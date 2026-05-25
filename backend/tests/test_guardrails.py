from app.guardrails import has_emoji, strip_emojis


def test_strip_emojis_removes_symbols():
    assert strip_emojis("Hello 😀 world") == "Hello  world"
    assert has_emoji("No emoji") is False
