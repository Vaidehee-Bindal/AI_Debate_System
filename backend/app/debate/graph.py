import asyncio
import json
from collections.abc import AsyncIterator
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .. import db
from ..clients.groq import GroqClient
from ..clients.tavily import TavilyClient
from ..guardrails import NO_EMOJI_RULE, strip_emojis
from .scoring import score_round


class DebateState(TypedDict, total=False):
    debate_id: str
    device_id: str
    topic: str
    rounds: int
    stance_style: str
    current_round: int
    previous: str
    moderator: str
    pro_text: str
    con_text: str
    pro_evidence: str
    con_evidence: str
    claims: list[dict[str, Any]]
    fact_checks: list[dict[str, Any]]
    score: dict[str, Any]
    final_summary: str


class DebateGraphRunner:
    def __init__(self) -> None:
        self.groq = GroqClient()
        self.tavily = TavilyClient()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(DebateState)
        graph.add_node("moderator_node", self._moderator)
        graph.add_node("pro_agent_node", self._pro_agent)
        graph.add_node("con_agent_node", self._con_agent)
        graph.add_node("claim_extractor_node", self._claim_extractor)
        graph.add_node("fact_checker_node", self._fact_checker)
        graph.add_node("scorer_node", self._scorer)
        graph.add_node("summarizer_node", self._summarizer)
        graph.set_entry_point("moderator_node")
        graph.add_edge("moderator_node", "pro_agent_node")
        graph.add_edge("pro_agent_node", "con_agent_node")
        graph.add_edge("con_agent_node", "claim_extractor_node")
        graph.add_edge("claim_extractor_node", "fact_checker_node")
        graph.add_edge("fact_checker_node", "scorer_node")
        graph.add_conditional_edges("scorer_node", self._next_step, {"moderator_node": "moderator_node", "summarizer_node": "summarizer_node"})
        graph.add_edge("summarizer_node", END)
        return graph.compile()

    async def stream(self, debate: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        state: DebateState = {
            "debate_id": debate["id"],
            "device_id": debate.get("device_id", ""),
            "topic": debate["topic"],
            "rounds": debate["rounds"],
            "stance_style": debate["stance_style"],
            "current_round": 0,
            "previous": "",
            "claims": [],
            "fact_checks": [],
        }
        try:
            while state.get("current_round", 0) < state["rounds"]:
                state = await self._moderator(state)
                yield {"event": "moderator_message", "data": self._message_payload(state, "Moderator", state["moderator"])}

                state = await self._pro_agent(state)
                pro_message = db.add_message(state["debate_id"], state["current_round"], "Pro Agent", state["pro_text"])
                yield {"event": "agent_message", "data": pro_message}

                state = await self._con_agent(state)
                con_message = db.add_message(state["debate_id"], state["current_round"], "Con Agent", state["con_text"])
                yield {"event": "agent_message", "data": con_message}

                state = await self._claim_extractor(state)
                for claim in state["claims"]:
                    message_id = pro_message["id"] if claim["speaker"] == "Pro Agent" else con_message["id"]
                    saved = db.add_claim(state["debate_id"], message_id, claim["speaker"], claim["claim"])
                    claim["id"] = saved["id"]
                    yield {"event": "claim_extracted", "data": saved}

                state = await self._fact_checker(state)
                for check in state["fact_checks"]:
                    saved = db.add_fact_check(
                        state["debate_id"],
                        check["claim_id"],
                        check["verdict"],
                        check["confidence"],
                        check["rationale"],
                        check["sources"],
                    )
                    saved["speaker"] = check["speaker"]
                    saved["claim"] = check["claim"]
                    yield {"event": "fact_check_result", "data": saved}

                state = await self._scorer(state)
                score = state["score"]
                saved_score = db.add_score(
                    state["debate_id"],
                    state["current_round"],
                    score["pro_score"],
                    score["con_score"],
                    {"pro": score["pro_breakdown"], "con": score["con_breakdown"]},
                )
                yield {"event": "score_update", "data": saved_score}
                yield {"event": "round_complete", "data": {"round": state["current_round"]}}
                state["previous"] = f"Pro: {state['pro_text']}\nCon: {state['con_text']}"

            state = await self._summarizer(state)
            winner = "Pro Agent" if state["score"]["pro_score"] >= state["score"]["con_score"] else "Con Agent"
            db.finish_debate(state["debate_id"], winner, state["final_summary"])
            yield {
                "event": "debate_complete",
                "data": {"winner": winner, "final_summary": state["final_summary"], "score": state["score"]},
            }
        except Exception as exc:
            db.mark_error(debate["id"])
            yield {"event": "error", "data": {"message": strip_emojis(str(exc))}}

    async def _moderator(self, state: DebateState) -> DebateState:
        round_number = state.get("current_round", 0) + 1
        content = await self.groq.complete(
            "You are a strict debate moderator. Keep turns fair and structured. " + NO_EMOJI_RULE,
            f"Topic: {state['topic']}\nRound: {round_number} of {state['rounds']}\nPrevious exchange:\n{state.get('previous', '')}",
        )
        state["current_round"] = round_number
        state["moderator"] = strip_emojis(content)
        db.add_message(state["debate_id"], round_number, "Moderator", state["moderator"])
        return state

    async def _pro_agent(self, state: DebateState) -> DebateState:
        evidence = await self._evidence_brief(state["topic"], "supporting")
        state["pro_evidence"] = evidence
        content = await self.groq.complete(
            (
                "You are the Pro debater. Argue in favor of the topic with rigorous reasoning, respectful rebuttals, "
                "and careful evidence use. Acknowledge the strongest opposing point before challenging it. "
                "Use only the supplied evidence for factual claims; if the evidence is weak, say so instead of inventing facts. "
                "Write exactly 3 or 4 paragraphs. Each paragraph must have 2 to 4 sentences. Do not use headings or bullet points. "
                + NO_EMOJI_RULE
            ),
            (
                f"Topic: {state['topic']}\n"
                f"Round: {state['current_round']} of {state['rounds']}\n"
                f"Previous exchange:\n{state.get('previous', '')}\n\n"
                f"Evidence brief for the Pro side:\n{evidence}\n\n"
                "Structure your answer as: position, evidence-backed argument, rebuttal or concession, and closing pressure point."
            ),
            temperature=0.28,
        )
        state["pro_text"] = strip_emojis(content)
        return state

    async def _con_agent(self, state: DebateState) -> DebateState:
        evidence = await self._evidence_brief(state["topic"], "opposing")
        state["con_evidence"] = evidence
        content = await self.groq.complete(
            (
                "You are the Con debater. Argue against the topic with rigorous reasoning, respectful rebuttals, "
                "and careful evidence use. Directly address the Pro Agent's strongest claim before adding your own case. "
                "Use only the supplied evidence for factual claims; if the evidence is weak, say so instead of inventing facts. "
                "Write exactly 3 or 4 paragraphs. Each paragraph must have 2 to 4 sentences. Do not use headings or bullet points. "
                + NO_EMOJI_RULE
            ),
            (
                f"Topic: {state['topic']}\n"
                f"Round: {state['current_round']} of {state['rounds']}\n"
                f"Pro argument to rebut:\n{state['pro_text']}\n\n"
                f"Previous exchange:\n{state.get('previous', '')}\n\n"
                f"Evidence brief for the Con side:\n{evidence}\n\n"
                "Structure your answer as: direct rebuttal, evidence-backed counterargument, concession or limit, and closing pressure point."
            ),
            temperature=0.28,
        )
        state["con_text"] = strip_emojis(content)
        return state

    async def _claim_extractor(self, state: DebateState) -> DebateState:
        fallback = {
            "claims": [
                {"speaker": "Pro Agent", "claim": state["pro_text"].split(".")[0][:220]},
                {"speaker": "Con Agent", "claim": state["con_text"].split(".")[0][:220]},
            ]
        }
        data = await self.groq.complete_json(
            "Extract up to two checkable factual claims from each debater. Ignore opinions.",
            f"Return JSON as {{\"claims\":[{{\"speaker\":\"Pro Agent\",\"claim\":\"...\"}}]}}.\nPro:\n{state['pro_text']}\nCon:\n{state['con_text']}",
            fallback,
        )
        claims = []
        for item in data.get("claims", [])[:4]:
            speaker = item.get("speaker")
            claim = strip_emojis(str(item.get("claim", ""))).strip()
            if speaker in {"Pro Agent", "Con Agent"} and claim:
                claims.append({"speaker": speaker, "claim": claim})
        state["claims"] = claims or fallback["claims"]
        return state

    async def _fact_checker(self, state: DebateState) -> DebateState:
        checks = []
        for claim in state.get("claims", []):
            sources = await self.tavily.search(claim["claim"])
            evidence = "\n".join(
                f"Source {index}: {s['title']}\nSnippet: {s['snippet']}\nURL: {s['url']}"
                for index, s in enumerate(sources, start=1)
            )
            fallback = {
                "verdict": "Needs Evidence",
                "confidence": 45,
                "rationale": "The available evidence is insufficient for a confident verdict.",
            }
            data = await self.groq.complete_json(
                "You are a source-grounded fact checker. Use only supplied evidence. Valid verdicts: True, False, Partially True, Misleading, Needs Evidence. Return a concise rationale focused on the claim itself. Do not include source titles, URLs, or citation lists in the rationale.",
                f"Claim: {claim['claim']}\nEvidence:\n{evidence}\nReturn JSON with verdict, confidence integer 0-100, and a concise rationale that explains why the claim is supported, challenged, or needs evidence.",
                fallback,
            )
            rationale = self._build_fact_rationale(
                claim["claim"],
                str(data.get("verdict", fallback["verdict"])),
                str(data.get("rationale", fallback["rationale"])),
                sources,
            )
            checks.append(
                {
                    "speaker": claim["speaker"],
                    "claim_id": claim.get("id", ""),
                    "claim": claim["claim"],
                    "verdict": data.get("verdict", "Needs Evidence"),
                    "confidence": int(data.get("confidence", 45)),
                    "rationale": rationale,
                    "sources": sources,
                }
            )
            await asyncio.sleep(0)
        state["fact_checks"] = checks
        return state

    def _build_fact_rationale(self, claim: str, verdict: str, rationale: str, sources: list[dict[str, str]]) -> str:
        claim_text = self._claim_focus(claim)
        verdict_text = verdict.strip() or "Needs Evidence"
        reason_text = self._clean_rationale(rationale)
        source_titles = [source.get("title", "") for source in sources if source.get("title")]

        if verdict_text == "Misleading":
            lead = f"For the claim that {claim_text}, the evidence makes the statement too broad."
        elif verdict_text == "Partially True":
            lead = f"For the claim that {claim_text}, the evidence supports the direction but not the full wording."
        elif verdict_text == "True":
            lead = f"For the claim that {claim_text}, the evidence supports the statement."
        elif verdict_text == "False":
            lead = f"For the claim that {claim_text}, the evidence contradicts the statement."
        else:
            lead = f"For the claim that {claim_text}, the evidence is not strong enough for a confident verdict."

        if reason_text and reason_text.lower() not in lead.lower():
            lead = f"{lead} {reason_text}"

        if source_titles:
            return lead
        return reason_text or lead

    def _clean_rationale(self, rationale: str) -> str:
        cleaned = strip_emojis(rationale)
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        cleaned = re.sub(r"\bReferences? considered\s*:\s*.*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\bLocal references considered\s*:\s*.*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .;:")
        return cleaned or "The available evidence is not enough for a confident verdict."

    def _claim_focus(self, claim: str) -> str:
        text = re.sub(r"\s+", " ", claim).strip()
        text = text.rstrip(".")
        if len(text) <= 140:
            return text
        comma = text.find(",")
        if 0 < comma <= 120:
            return text[:comma]
        period = text.find(".")
        if 0 < period <= 120:
            return text[:period]
        return text[:140].rsplit(" ", 1)[0]

    async def _scorer(self, state: DebateState) -> DebateState:
        state["score"] = score_round(state["current_round"], state["pro_text"], state["con_text"], state["fact_checks"])
        return state

    async def _summarizer(self, state: DebateState) -> DebateState:
        detail = db.get_debate(state["debate_id"], state.get("device_id", ""))
        messages = detail.get("messages", [])
        fact_checks = detail.get("fact_checks", [])
        scores = detail.get("scores", [])

        # Enrich fact checks with speaker/claim using claims table (DB fact_checks rows do not include these fields)
        claim_lookup: dict[str, dict[str, str]] = {
            str(item.get("id", "")): {
                "speaker": str(item.get("speaker", "")),
                "claim": str(item.get("claim", "")),
            }
            for item in detail.get("claims", [])
        }
        enriched_checks: list[dict[str, Any]] = []
        for item in fact_checks:
            claim_meta = claim_lookup.get(str(item.get("claim_id", "")), {})
            copy = dict(item)
            if "speaker" not in copy:
                copy["speaker"] = claim_meta.get("speaker", "")
            if "claim" not in copy:
                copy["claim"] = claim_meta.get("claim", "")
            enriched_checks.append(copy)
        fact_checks = enriched_checks

        pro_messages = [m for m in messages if m.get("speaker") == "Pro Agent"]
        con_messages = [m for m in messages if m.get("speaker") == "Con Agent"]

        winner = "Pro Agent" if state["score"]["pro_score"] >= state["score"]["con_score"] else "Con Agent"
        loser = "Con Agent" if winner == "Pro Agent" else "Pro Agent"

        pro_points = self._extract_main_points(pro_messages)
        con_points = self._extract_main_points(con_messages)

        pro_strong, pro_weak = self._strong_and_weak_claim(fact_checks, "Pro Agent")
        con_strong, con_weak = self._strong_and_weak_claim(fact_checks, "Con Agent")

        verdict_counts: dict[str, int] = {"True": 0, "Partially True": 0, "Needs Evidence": 0, "Misleading": 0, "False": 0}
        for item in fact_checks:
            verdict = str(item.get("verdict", "Needs Evidence"))
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        latest_score = scores[-1] if scores else {
            "pro_score": state["score"]["pro_score"],
            "con_score": state["score"]["con_score"],
            "breakdown": {"pro": state["score"]["pro_breakdown"], "con": state["score"]["con_breakdown"]},
        }

        pro_breakdown = latest_score.get("breakdown", {}).get("pro", state["score"].get("pro_breakdown", {}))
        con_breakdown = latest_score.get("breakdown", {}).get("con", state["score"].get("con_breakdown", {}))

        turning_points = self._turning_points(scores, winner)
        winner_reason = self._winner_reason(winner, loser, pro_breakdown, con_breakdown, verdict_counts)

        summary = "\n".join(
            [
                f"1. Debate Topic\n{state['topic']}",
                (
                    "2. Pro Agent Main Arguments\n"
                    f"- Main points: {pro_points}\n"
                    f"- Strongest point: {pro_strong}\n"
                    f"- Weak argument: {pro_weak}"
                ),
                (
                    "3. Con Agent Main Arguments\n"
                    f"- Main points: {con_points}\n"
                    f"- Strongest point: {con_strong}\n"
                    f"- Weak argument: {con_weak}"
                ),
                (
                    "4. Fact Check Results\n"
                    f"True: {verdict_counts.get('True', 0)}, Partially True: {verdict_counts.get('Partially True', 0)}, "
                    f"Needs Evidence: {verdict_counts.get('Needs Evidence', 0)}, Misleading: {verdict_counts.get('Misleading', 0)}, False: {verdict_counts.get('False', 0)}."
                ),
                f"5. Key Turning Points\n{turning_points}",
                (
                    "6. Final Scores\n"
                    f"Pro Agent: {latest_score.get('pro_score', 0)} | Con Agent: {latest_score.get('con_score', 0)}\n"
                    f"Logic (Pro {pro_breakdown.get('logic', 0)} / Con {con_breakdown.get('logic', 0)}), "
                    f"Evidence (Pro {pro_breakdown.get('evidence', 0)} / Con {con_breakdown.get('evidence', 0)}), "
                    f"Rebuttal (Pro {pro_breakdown.get('rebuttal', 0)} / Con {con_breakdown.get('rebuttal', 0)}), "
                    f"Clarity (Pro {pro_breakdown.get('clarity', 0)} / Con {con_breakdown.get('clarity', 0)}), "
                    f"Accuracy (Pro {pro_breakdown.get('accuracy', 0)} / Con {con_breakdown.get('accuracy', 0)})."
                ),
                f"7. Winner\n{winner}",
                f"8. Final Conclusion\n{winner_reason}",
            ]
        )

        state["final_summary"] = strip_emojis(summary)
        return state

    def _extract_main_points(self, messages: list[dict[str, Any]]) -> str:
        points: list[str] = []
        for item in messages:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            sentence = content.split(".")[0].strip()
            if sentence and sentence not in points:
                points.append(sentence)
            if len(points) >= 2:
                break
        return "; ".join(points) if points else "No clear arguments recorded."

    def _strong_and_weak_claim(self, fact_checks: list[dict[str, Any]], speaker: str) -> tuple[str, str]:
        speaker_checks = [item for item in fact_checks if item.get("speaker") == speaker]
        if not speaker_checks:
            return ("No verified strong claim.", "No weak claim identified.")

        rank = {"True": 5, "Partially True": 4, "Needs Evidence": 3, "Misleading": 2, "False": 1}

        def score_key(item: dict[str, Any]) -> tuple[int, int]:
            verdict = str(item.get("verdict", "Needs Evidence"))
            confidence = int(item.get("confidence", 0))
            return (rank.get(verdict, 3), confidence)

        strong = max(speaker_checks, key=score_key)
        weak = min(speaker_checks, key=score_key)

        strong_text = f"{strong.get('claim', 'N/A')} ({strong.get('verdict', 'Needs Evidence')}, {strong.get('confidence', 0)}%)"
        weak_text = f"{weak.get('claim', 'N/A')} ({weak.get('verdict', 'Needs Evidence')}, {weak.get('confidence', 0)}%)"
        return strong_text, weak_text

    def _turning_points(self, scores: list[dict[str, Any]], winner: str) -> str:
        if not scores:
            return "No round-by-round score data available."

        leads: list[tuple[int, int]] = []
        for s in scores:
            round_number = int(s.get("round", 0))
            lead = int(s.get("pro_score", 0)) - int(s.get("con_score", 0))
            leads.append((round_number, lead))

        biggest_shift_round = leads[0][0]
        biggest_shift_value = 0
        for i in range(1, len(leads)):
            shift = abs(leads[i][1] - leads[i - 1][1])
            if shift > biggest_shift_value:
                biggest_shift_value = shift
                biggest_shift_round = leads[i][0]

        final_round, final_lead = leads[-1]
        leader_text = "Pro Agent" if final_lead > 0 else "Con Agent"
        if final_lead == 0:
            leader_text = winner

        return (
            f"Biggest momentum change happened in Round {biggest_shift_round}. "
            f"By Round {final_round}, {leader_text} held the final lead."
        )

    def _winner_reason(
        self,
        winner: str,
        loser: str,
        pro_breakdown: dict[str, Any],
        con_breakdown: dict[str, Any],
        verdict_counts: dict[str, int],
    ) -> str:
        winner_breakdown = pro_breakdown if winner == "Pro Agent" else con_breakdown
        loser_breakdown = con_breakdown if winner == "Pro Agent" else pro_breakdown

        diffs = {
            "logic": int(winner_breakdown.get("logic", 0)) - int(loser_breakdown.get("logic", 0)),
            "evidence": int(winner_breakdown.get("evidence", 0)) - int(loser_breakdown.get("evidence", 0)),
            "rebuttal": int(winner_breakdown.get("rebuttal", 0)) - int(loser_breakdown.get("rebuttal", 0)),
            "clarity": int(winner_breakdown.get("clarity", 0)) - int(loser_breakdown.get("clarity", 0)),
            "accuracy": int(winner_breakdown.get("accuracy", 0)) - int(loser_breakdown.get("accuracy", 0)),
        }

        best_components = [name for name, delta in sorted(diffs.items(), key=lambda item: item[1], reverse=True) if delta > 0][:2]
        comp_text = ", ".join(best_components) if best_components else "overall consistency"

        return (
            f"{winner} performed better than {loser} due to stronger {comp_text}. "
            f"Fact-check outcomes also mattered: {verdict_counts.get('True', 0)} True and {verdict_counts.get('Partially True', 0)} Partially True claims carried more weight than weaker or unsupported claims."
        )

    async def _evidence_brief(self, topic: str, stance: str) -> str:
        query = f"{topic} evidence arguments {stance} current research statistics"
        sources = await self.tavily.search(query)
        if not sources:
            return "No external sources were found. Avoid specific factual claims and rely on clearly labeled reasoning."
        lines = []
        for index, source in enumerate(sources[:4], start=1):
            title = source.get("title") or "Source"
            snippet = source.get("snippet") or "No snippet available."
            url = source.get("url") or ""
            lines.append(f"{index}. {title}: {snippet} Source: {url}")
        return "\n".join(lines)

    def _next_step(self, state: DebateState) -> str:
        return "summarizer_node" if state.get("current_round", 0) >= state["rounds"] else "moderator_node"

    def _message_payload(self, state: DebateState, speaker: str, content: str) -> dict[str, Any]:
        return {"debate_id": state["debate_id"], "round": state["current_round"], "speaker": speaker, "content": content}
