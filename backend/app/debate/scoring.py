from typing import Any


def score_round(round_number: int, pro_text: str, con_text: str, fact_checks: list[dict[str, Any]]) -> dict[str, Any]:
    pro_accuracy = _accuracy_for("Pro Agent", fact_checks)
    con_accuracy = _accuracy_for("Con Agent", fact_checks)
    pro_rebuttal = _rebuttal_score(pro_text)
    con_rebuttal = _rebuttal_score(con_text)
    pro = {
        "logic": _logic_score(pro_text),
        "evidence": _evidence_score("Pro Agent", fact_checks),
        "rebuttal": min(20, pro_rebuttal),
        "clarity": _clarity_score(pro_text),
        # Map accuracy (0-100) into 8-20 range deterministically
        "accuracy": max(8, min(20, int(round((pro_accuracy / 100.0) * 12)) + 8)),
    }
    con = {
        "logic": _logic_score(con_text),
        "evidence": _evidence_score("Con Agent", fact_checks),
        "rebuttal": min(20, con_rebuttal),
        "clarity": _clarity_score(con_text),
        "accuracy": max(8, min(20, int(round((con_accuracy / 100.0) * 12)) + 8)),
    }
    pro_score = sum(pro.values())
    con_score = sum(con.values())

    # Deterministic tiebreaker: ensure scores are never equal.
    # Prefer the side with higher evidence score, then higher accuracy, then higher logic, then longer text.
    if pro_score == con_score:
        tie_winner = None
        if pro["evidence"] != con["evidence"]:
            tie_winner = "pro" if pro["evidence"] > con["evidence"] else "con"
        elif pro["accuracy"] != con["accuracy"]:
            tie_winner = "pro" if pro["accuracy"] > con["accuracy"] else "con"
        elif pro["logic"] != con["logic"]:
            tie_winner = "pro" if pro["logic"] > con["logic"] else "con"
        else:
            # final deterministic check: longer combined text length wins
            if len(pro_text) != len(con_text):
                tie_winner = "pro" if len(pro_text) > len(con_text) else "con"
            else:
                tie_winner = "pro"

        if tie_winner == "pro":
            pro_score += 1
        else:
            con_score += 1

    return {
        "pro_breakdown": pro,
        "con_breakdown": con,
        "pro_score": pro_score,
        "con_score": con_score,
    }


def _accuracy_for(speaker: str, fact_checks: list[dict[str, Any]]) -> int:
    relevant = [item for item in fact_checks if item.get("speaker") == speaker]
    if not relevant:
        return 55
    values = []
    for item in relevant:
        verdict = item.get("verdict")
        confidence = int(item.get("confidence", 50))
        if verdict == "True":
            values.append(confidence)
        elif verdict == "Partially True":
            values.append(max(45, confidence - 15))
        elif verdict == "Needs Evidence":
            values.append(45)
        elif verdict == "Misleading":
            values.append(30)
        else:
            values.append(20)
    return int(sum(values) / len(values))


def _logic_score(text: str) -> int:
    lowered = text.lower()
    markers = ["because", "therefore", "if", "when", "however", "so", "but"]
    score = 11 + min(5, sum(1 for marker in markers if marker in lowered))
    score += min(4, len(set(lowered.split())) // 55)
    return max(8, min(20, score))


def _evidence_score(speaker: str, fact_checks: list[dict[str, Any]]) -> int:
    relevant = [item for item in fact_checks if item.get("speaker") == speaker]
    if not relevant:
        return 9
    score = 8
    for item in relevant:
        verdict = item.get("verdict")
        confidence = int(item.get("confidence", 50))
        if verdict == "True":
            score += 4
        elif verdict == "Partially True":
            score += 3
        elif verdict == "Needs Evidence":
            score += 1
        elif verdict == "Misleading":
            score -= 1
        else:
            score -= 2
        if confidence >= 70:
            score += 1
    return max(5, min(20, score))


def _rebuttal_score(text: str) -> int:
    lowered = text.lower()
    markers = ["concession", "objection", "weakness", "strongest", "pro side", "con side", "however", "but", "direct"]
    return max(8, min(20, 10 + sum(1 for marker in markers if marker in lowered)))


def _clarity_score(text: str) -> int:
    paragraphs = [part for part in text.split("\n\n") if part.strip()]
    words = text.split()
    if not words:
        return 5
    avg_sentence_len = len(words) / max(1, text.count(".") + text.count("?") + text.count("!"))
    score = 12
    if 3 <= len(paragraphs) <= 4:
        score += 3
    if 14 <= avg_sentence_len <= 32:
        score += 3
    if len(words) >= 180:
        score += 2
    return max(8, min(20, score))
