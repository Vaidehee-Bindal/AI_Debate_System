from app.clients.groq import GroqClient
from app.guardrails import has_emoji


def _paragraph_count(text: str) -> int:
    return len([part for part in text.split("\n\n") if part.strip()])


def test_fallback_debaters_are_long_form_and_emoji_free():
    client = GroqClient()

    pro = client._fallback("You are the Pro debater.", "Topic: AI will replace software engineers")
    con = client._fallback("You are the Con debater.", "Topic: AI will replace software engineers")

    assert _paragraph_count(pro) == 4
    assert _paragraph_count(con) == 4
    assert has_emoji(pro) is False
    assert has_emoji(con) is False


def test_fallback_debaters_change_by_round():
    client = GroqClient()

    round_one = client._fallback("You are the Pro debater.", "Topic: AI will replace software engineers\nRound: 1 of 3")
    round_two = client._fallback("You are the Pro debater.", "Topic: AI will replace software engineers\nRound: 2 of 3")

    assert round_one != round_two
    assert "opening" not in round_two.lower()


def test_fallback_fact_checker_is_not_constant():
    client = GroqClient()

    limited = client._fallback_json(
        "You are a source-grounded fact checker.",
        "Claim: AI can automate some routine coding tasks.\nEvidence:\n- Local evidence brief: task automation: AI tools can draft and test code.",
        {},
    )
    broad = client._fallback_json(
        "You are a source-grounded fact checker.",
        "Claim: AI will replace every software engineer.\nEvidence:\n- Local evidence brief: task automation: AI tools can draft and test code.",
        {},
    )
    causal = client._fallback_json(
        "You are a source-grounded fact checker.",
        "Claim: School uniforms reduce classroom distractions.\nEvidence:\n- Local evidence brief: pro considerations: Supportive arguments should identify expected benefits.\n- Local evidence brief: verification limits: Live search was unavailable.",
        {},
    )

    assert limited["confidence"] != 45
    assert broad["confidence"] != 45
    assert limited["verdict"] != broad["verdict"]
    assert len({limited["confidence"], broad["confidence"], causal["confidence"]}) == 3
    assert "Local evidence brief" in limited["rationale"]


def test_fallback_supports_generic_topics():
    client = GroqClient()

    pro = client._fallback("You are the Pro debater.", "Topic: School uniforms should be mandatory\nRound: 1 of 3")
    con = client._fallback("You are the Con debater.", "Topic: School uniforms should be mandatory\nRound: 1 of 3")

    assert "School uniforms should be mandatory" in pro
    assert "School uniforms should be mandatory" in con
    assert "AI" not in pro
    assert _paragraph_count(pro) == 4
    assert _paragraph_count(con) == 4
