from app.debate.scoring import score_round


def test_score_round_returns_winner_ready_scores():
    score = score_round(
        1,
        "AI automates repetitive tasks and improves delivery.",
        "Humans remain needed for judgment and accountability.",
        [{"speaker": "Pro Agent", "verdict": "True", "confidence": 90}],
    )
    assert score["pro_score"] > 0
    assert score["con_score"] > 0
    assert "logic" in score["pro_breakdown"]
