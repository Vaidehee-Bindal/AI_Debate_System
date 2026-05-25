import json
import re
from typing import Any

import httpx

from ..config import get_settings
from ..guardrails import NO_EMOJI_RULE, strip_emojis


class GroqClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def complete(self, system: str, user: str, temperature: float = 0.35) -> str:
        if not self.settings.groq_api_key:
            return self._fallback(system, user)

        payload = {
            "model": self.settings.groq_model,
            "messages": [
                {"role": "system", "content": f"{NO_EMOJI_RULE}\n{system}"},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return strip_emojis(content)
        except httpx.HTTPError:
            return self._fallback(system, user)

    async def complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.groq_api_key:
            return self._fallback_json(system, user, fallback)

        text = await self.complete(f"{system}\nReturn valid compact JSON only.", user, temperature=0.1)
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception:
            return self._fallback_json(system, user, fallback)

    def _fallback(self, system: str, user: str) -> str:
        lowered = system.lower()
        if "pro debater" in lowered:
            return self._fallback_debater("pro", user)
        if "con debater" in lowered:
            return self._fallback_debater("con", user)
        if "moderator" in lowered:
            round_number = self._round_number(user)
            topic = self._topic(user)
            messages = [
                f"Round {round_number} opens on the topic: {topic}. Pro Agent should establish the strongest affirmative case with clear reasoning and checkable claims, then Con Agent should answer the core assumption rather than repeat general objections.",
                f"Round {round_number} now moves from opening claims to clash. Pro Agent should respond to the previous Con critique and add a more concrete mechanism, while Con Agent should test whether that mechanism proves replacement or only transformation.",
                f"Round {round_number} is the closing comparison round. Each side should weigh its best evidence, expose the weakest unsupported claim from the opponent, and explain why its conclusion follows more reliably from the debate record.",
            ]
            return messages[min(round_number - 1, len(messages) - 1)]
        if "summary" in lowered:
            return self._fallback_summary(user)
        return "The available evidence is mixed, so the safest conclusion is to state the claim with limits and avoid overstating certainty."

    def _fallback_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        lowered = system.lower()
        if "extract" in lowered and "claim" in lowered:
            return {"claims": self._fallback_claims(user)}
        if "fact checker" in lowered:
            return self._fallback_fact_check(user)
        return fallback

    def _fallback_debater(self, side: str, user: str) -> str:
        topic = self._topic(user)
        round_number = self._round_number(user)
        subject = self._subject_label(topic)
        if "ai" not in topic.lower():
            return self._fallback_generic_debater(side, topic, round_number)

        pro_rounds = [
            [
                f"The affirmative case is that {subject} is already moving from assistance toward substitution in repeatable parts of professional work. The key point is not that every role disappears at once, but that employers redesign teams when software can produce acceptable first drafts, tests, analysis, or plans at very low marginal cost. Once that happens, fewer people are needed for the same baseline output.",
                "The evidence pattern supports task displacement first: coding assistants, document generation, automated research, customer support tools, and workflow agents all target work that used to require junior or mid-level labor. Even if a human remains in the loop, the human is increasingly supervising, sampling, and integrating rather than doing every step manually. That changes hiring demand because one skilled person can coordinate more output than before.",
                "The strongest Con objection is that judgment and accountability still matter, and that is true. But it does not remove the replacement pressure; it narrows where replacement begins. A role can be partially replaced in a way that still reduces headcount, especially when the remaining human responsibility is review, exception handling, and stakeholder communication.",
                f"So the Pro side should be judged on labor-market direction, not science-fiction total automation. If {subject} keeps improving in reliability and integration cost keeps falling, organizations have a rational incentive to substitute AI for routine execution while reserving people for the smaller set of tasks where human judgment is essential.",
            ],
            [
                "The previous Con argument correctly says that task automation is not identical to full job automation, but that distinction can understate the economic effect. Jobs are bundles of tasks, and if the most time-consuming tasks in the bundle shrink dramatically, the number of workers needed can still fall. A company does not need perfect automation to reduce hiring; it needs automation that is good enough to change staffing ratios.",
                f"For {subject}, the practical replacement pathway is gradual: AI handles drafts, routine implementation, comparison of alternatives, documentation, test generation, and first-pass troubleshooting. Human experts then validate and direct the work. That may sound collaborative, but collaboration at a ten-to-one output ratio still means fewer people doing the old version of the job.",
                "The Con side also claims that demand may expand as productivity rises. That is possible in some markets, but it is not guaranteed to protect every profession or every skill level. If new demand concentrates around senior reviewers and product thinkers, entry-level roles can still be squeezed, weakening the pipeline that used to train future experts.",
                "The Pro case therefore rests on a realistic middle claim: AI can replace enough of the work to replace many positions, even while some people become more valuable. The debate is not humans versus machines in the abstract; it is whether the average organization will buy fewer hours of human execution once machine execution becomes cheap, fast, and broadly available.",
            ],
            [
                "At this point the central question is burden of proof. The Con side has shown that humans remain necessary for accountability and ambiguous decisions, but it has not shown that those responsibilities preserve the same number of roles. A smaller expert layer can coexist with broad replacement of routine work underneath it.",
                f"The stronger Pro evidence is the direction of adoption: tools are being embedded directly into workflows, not kept as side experiments. When {subject} becomes part of daily production systems, the productivity gain is no longer a novelty; it becomes a management expectation. Teams are then measured against a new output baseline that assumes AI assistance.",
                "The Con side is right to warn against exaggerated claims, so the Pro side should avoid saying total replacement is imminent. The more defensible claim is that replacement will be uneven, hitting repeatable tasks, junior work, and standardized production first. That still matters because those categories support a large share of employment and training.",
                "The final Pro position is that transformation and replacement are not opposites. A transformed role can require fewer people, different skills, and a smaller entry path. If the opposing side cannot explain why firms would maintain old staffing models after reliable automation changes output economics, the replacement thesis remains stronger.",
            ],
        ]

        con_rounds = [
            [
                f"The negative case is that {subject} should be understood as role transformation, not wholesale replacement. Producing a plausible answer is very different from owning a decision, understanding an institution's constraints, and being accountable when something fails. Real work includes context, negotiation, risk, and judgment that are not captured by output alone.",
                "The Pro side is strongest when it talks about routine task automation, and that should be conceded. AI can draft, summarize, generate code, search documents, and accelerate repetitive production. But those gains do not prove that the full professional function disappears; they often shift the human role toward problem framing, validation, integration, and responsibility.",
                "A major weakness in the replacement argument is that it treats labor demand as fixed. When a capability becomes cheaper, organizations often do more of it: more prototypes, more analysis, more personalized service, more software, or more experiments. The result can be a change in job content rather than a simple reduction in jobs.",
                "The Con side should therefore be judged on whether the Pro side proves durable full-role substitution. So far, the more reliable conclusion is that AI compresses some tasks while increasing the premium on people who can decide what should be built, whether the output is correct, and how it fits real human needs.",
            ],
            [
                "The Pro side argues that partial task replacement is enough to reduce headcount, but that skips over coordination costs and risk. When work becomes easier to generate, the bottleneck often moves to deciding which work is worth doing and checking whether it is safe, coherent, and useful. Those bottlenecks are human-heavy, especially in high-stakes domains.",
                f"In the case of {subject}, the most valuable work is rarely just producing artifacts. It includes understanding unclear requirements, balancing tradeoffs, communicating with stakeholders, maintaining systems over time, and making decisions under uncertainty. AI can support those activities, but support is not the same as accountable ownership.",
                "The Pro side is also vulnerable on training pipelines, because it assumes fewer junior roles without explaining how organizations will create future senior experts. If firms eliminate too much entry-level work, they may create a long-term talent shortage and quality problem. That gives organizations a reason to redesign training rather than simply remove humans.",
                "The better conclusion is selective displacement plus professional adaptation. Some tasks and some weakly differentiated roles will shrink, but the broad claim that AI will replace the profession overstates what the evidence proves. The Con side wins if the standard is full replacement rather than meaningful change.",
            ],
            [
                "The closing Con argument is that the Pro side has shown pressure, not inevitability. Economic incentives matter, but organizations also face liability, trust, customer expectations, regulation, security, and maintenance costs. Those constraints slow simple substitution and preserve demand for human judgment.",
                f"For {subject}, the strongest future is likely a hybrid operating model. AI expands what a smaller team can attempt, but people remain necessary to choose goals, interpret context, validate outputs, and handle exceptions. That means the job changes shape rather than vanishing as a category.",
                "The Pro side is right that some routine work will be automated and that some roles will be reduced. The Con side does not need to deny that. It only needs to show that the phrase 'replace' is too broad when the remaining human responsibilities are central to success rather than decorative.",
                "The final Con position is that replacement claims should be reserved for cases where AI can perform the whole responsibility chain reliably. Until then, the most accurate forecast is disruption, reskilling, and selective displacement. That is a serious change, but it is not the same as replacing the profession.",
            ],
        ]

        rounds = pro_rounds if side == "pro" else con_rounds
        return "\n\n".join(rounds[min(round_number - 1, len(rounds) - 1)])

    def _fallback_generic_debater(self, side: str, topic: str, round_number: int) -> str:
        pro_rounds = [
            [
                f"The affirmative case for '{topic}' begins with the practical benefits it can create if implemented carefully. A strong Pro argument should not pretend there are no tradeoffs; it should show that the expected gains are important enough to justify managing those tradeoffs. The central claim is that the proposal solves a real problem better than the current default.",
                "The first reason to support the topic is that it can improve outcomes for the people or institutions most affected by the issue. When a policy, behavior, or idea creates clearer incentives and reduces avoidable friction, it can produce benefits beyond the immediate case. That makes the Pro side stronger when it explains the mechanism, not just the desired result.",
                "The strongest Con objection is usually that the proposal may create unintended consequences, unfair costs, or implementation problems. That concern deserves attention, but it does not automatically defeat the idea. The better response is to compare the risk of action with the risk of leaving the current problem unsolved.",
                f"So the Pro side should be judged on comparative impact. If '{topic}' can produce meaningful benefits while its risks are limited through design, oversight, or gradual adoption, then supporting it is more reasonable than rejecting it because it is imperfect.",
            ],
            [
                "The previous Con position raises a useful caution: good intentions do not guarantee good results. But that caution can become too conservative if it treats every implementation challenge as a reason for inaction. Many worthwhile changes require refinement, safeguards, and feedback rather than abandonment.",
                f"For '{topic}', the practical question is whether the benefits can be made concrete and the risks can be contained. The Pro side should emphasize measurable outcomes, pilot programs, clear standards, or accountability mechanisms depending on the topic. That makes the argument more credible than a broad appeal to optimism.",
                "A fair concession is that the proposal may not help everyone equally at first. However, unequal early impact is not the same as failure if the direction of improvement is clear and the design can be adjusted. The Con side needs to show that the harms are structural and unavoidable, not merely possible.",
                "The Pro case therefore rests on disciplined reform rather than blind enthusiasm. A proposal can be worth supporting when it improves the status quo, creates learning opportunities, and gives decision-makers tools to correct mistakes as evidence develops.",
            ],
            [
                f"The closing Pro argument is that '{topic}' should be evaluated against realistic alternatives, not against perfection. If the current situation has persistent costs, then refusing change also carries consequences. The Pro side wins when it shows that action is more responsible than passive acceptance.",
                "The strongest evidence in favor is the logic of targeted benefit: identify the problem, explain why the proposal addresses it, and show how risks can be monitored. That framework is stronger than making exaggerated promises. It also gives the audience a practical way to support the idea without ignoring uncertainty.",
                "The Con side is right to demand limits, but limits can be built into the proposal. Oversight, transparency, staged rollout, and review can reduce the chance that the idea becomes harmful in practice. A manageable risk should not be treated like a decisive refutation.",
                "The final Pro position is that the topic deserves support if it offers a better path than the status quo and if its weaknesses can be handled through responsible design. The burden on the Con side is to show that rejection produces better outcomes, not merely that support requires care.",
            ],
        ]

        con_rounds = [
            [
                f"The negative case against '{topic}' is that attractive proposals often look stronger in principle than in practice. The Con side should focus on what can go wrong when incentives, costs, enforcement, or human behavior are considered. A good debate must ask whether the promised benefit survives contact with real-world constraints.",
                "The first reason to oppose the topic is that its benefits may be uneven, uncertain, or dependent on assumptions that are hard to guarantee. If the proposal shifts costs onto people with less power, creates perverse incentives, or requires institutions to behave unrealistically well, then the Pro case becomes weaker. Practical feasibility matters as much as intention.",
                "The strongest Pro point is that the current system may have real problems, and that should be conceded. But identifying a problem does not prove that this specific solution is the best answer. The Con side can support reform while rejecting a proposal that is too broad, too risky, or insufficiently evidenced.",
                f"So the Con side should be judged on whether it exposes a gap between aspiration and execution. If '{topic}' depends on optimistic assumptions while underestimating tradeoffs, the safer conclusion is to reject or significantly narrow it.",
            ],
            [
                "The Pro side argues that risks can be managed, but that claim needs more than reassurance. Some risks are not accidental; they are built into the incentives created by the proposal. If the design rewards the wrong behavior or lacks enforceable limits, oversight after the fact may arrive too late.",
                f"For '{topic}', the Con side should press for evidence that the proposal works outside ideal conditions. Who pays, who benefits, who monitors abuse, and what happens when results disappoint are not side questions. They are central to whether the proposal deserves support.",
                "A reasonable concession is that doing nothing may also be costly. Still, the choice is not limited to this proposal or no change at all. A narrower alternative may solve the same problem with fewer side effects and less institutional burden.",
                "The better Con conclusion is that caution is not the same as obstruction. It is rational to oppose a broad claim when the implementation path is unclear, the evidence is incomplete, or the harms would be difficult to reverse.",
            ],
            [
                f"The closing Con argument is that '{topic}' has not met the burden required for confident support. The Pro side has described possible benefits, but possibility is not enough when the costs and tradeoffs may be significant. Responsible judgment requires evidence that the proposal works reliably and fairly.",
                "The strongest negative evidence is the risk of overgeneralization. A claim can be true in some settings and still fail as a broad rule. If the topic affects diverse people, institutions, or contexts, then the debate should resist one-size-fits-all conclusions.",
                "The Pro side is right that imperfection alone does not defeat an idea. But unresolved structural weaknesses do. If the proposal cannot clearly explain accountability, fairness, cost, and failure recovery, then its attractive goal may become a poor guide to action.",
                "The final Con position is that the topic should be rejected, narrowed, or delayed until stronger evidence and safeguards exist. The burden remains on the Pro side to prove not only that the goal is desirable, but that this approach is the right way to pursue it.",
            ],
        ]

        rounds = pro_rounds if side == "pro" else con_rounds
        return "\n\n".join(rounds[min(round_number - 1, len(rounds) - 1)])

    def _fallback_claims(self, user: str) -> list[dict[str, str]]:
        claims: list[dict[str, str]] = []
        sections = self._speaker_sections(user)
        for speaker, text in sections.items():
            sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
            checkable = [
                sentence
                for sentence in sentences
                if any(term in sentence.lower() for term in ["can", "will", "when", "if", "already", "often", "usually", "demand", "roles", "tasks"])
            ]
            chosen = checkable[:2] or sentences[:1]
            for sentence in chosen:
                claims.append({"speaker": speaker, "claim": sentence[:260]})
        return claims[:4]

    def _fallback_fact_check(self, user: str) -> dict[str, Any]:
        claim_match = re.search(r"Claim:\s*(.+?)(?:\nEvidence:|\Z)", user, flags=re.S)
        claim = claim_match.group(1).strip() if claim_match else user[:240]
        lowered = claim.lower()
        evidence = user.lower()
        source_titles = self._source_titles(user)
        source_count = max(1, len(source_titles))
        is_local = "local evidence brief" in evidence or "local://" in evidence
        has_qualifier = any(word in lowered for word in ["can", "may", "might", "some", "often", "could", "partial", "selective"])
        has_absolute = any(word in lowered for word in ["always", "never", "all", "every", "guarantee", "inevitable", "must"])
        has_causal = any(word in lowered for word in ["because", "therefore", "leads to", "results in", "creates", "reduces", "improves"])
        has_weak_evidence_flag = any(term in evidence for term in ["verification limits", "unavailable", "offline", "stronger sources"])
        variance = (sum(ord(char) for char in claim) % 13) - 6

        if has_absolute:
            confidence = self._clamp(54 + (source_count * 3) + variance, 48, 68)
            return {
                "verdict": "Misleading",
                "confidence": confidence,
                "rationale": self._fact_rationale(
                    "The claim uses absolute language that the available references do not fully support.",
                    source_titles,
                    is_local,
                ),
            }

        if "no tavily api key" in evidence or "local fallback" in evidence:
            if has_qualifier:
                confidence = self._clamp(59 + (source_count * 2) + variance, 55, 72)
                return {
                    "verdict": "Partially True",
                    "confidence": confidence,
                    "rationale": self._fact_rationale(
                        "The claim is limited and plausible, but the local references are not enough for high-confidence verification.",
                        source_titles,
                        is_local,
                    ),
                }
            return {
                "verdict": "Needs Evidence",
                "confidence": self._clamp(45 + (source_count * 2) + variance, 42, 58),
                "rationale": self._fact_rationale(
                    "The claim is debatable, but the available local references do not directly verify it.",
                    source_titles,
                    is_local,
                ),
            }

        if has_weak_evidence_flag and not has_qualifier:
            return {
                "verdict": "Needs Evidence",
                "confidence": self._clamp(48 + (source_count * 3) + variance, 45, 63),
                "rationale": self._fact_rationale(
                    "The references provide context but do not directly establish the claim.",
                    source_titles,
                    is_local,
                ),
            }
        if has_qualifier and has_causal:
            verdict = "Partially True"
            base = 67
        elif has_qualifier:
            verdict = "Partially True"
            base = 63
        elif has_causal:
            verdict = "Needs Evidence"
            base = 58
        else:
            verdict = "Needs Evidence"
            base = 52

        confidence = self._clamp(base + (source_count * 4) + variance - (8 if is_local else 0), 45, 88)
        return {
            "verdict": verdict,
            "confidence": confidence,
            "rationale": self._fact_rationale(
                "The references support part of the reasoning, but the claim should remain qualified unless a source directly proves it.",
                source_titles,
                is_local,
            ),
        }

    def _source_titles(self, user: str) -> list[str]:
        # Extract source title lines like: "Source 1: Title" and corresponding URL lines like "URL: https://..."
        titles = re.findall(r"Source\s+\d+:\s*(.+)", user)
        urls = re.findall(r"URL:\s*(\S+)", user)
        if not titles:
            titles = re.findall(r"-\s*(.+?):\s", user)
        cleaned: list[str] = []
        # Pair titles and urls by order when possible
        for idx, title in enumerate(titles):
            t = title.strip()
            url = urls[idx].strip() if idx < len(urls) else ""
            if t:
                if url:
                    entry = f"{t} — {url}"
                else:
                    entry = t
                if entry not in cleaned:
                    cleaned.append(entry)
        # If no structured titles found, fall back to any standalone URLs
        if not cleaned and urls:
            for u in urls[:4]:
                cleaned.append(u)
        return cleaned[:4]

    def _fact_rationale(self, reason: str, source_titles: list[str], is_local: bool) -> str:
        if not source_titles:
            return reason
        # Include exact links when available in the extracted source entries
        citation = "; ".join(source_titles[:3])
        prefix = "Local references considered" if is_local else "References considered"
        return f"{reason} {prefix}: {citation}."

    def _clamp(self, value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))

    def _fallback_summary(self, user: str) -> str:
        winner_match = re.search(r"Winner:\s*(.+)", user)
        winner = winner_match.group(1).strip() if winner_match else "the stronger-scoring side"
        topic = self._topic(user)
        return (
            f"{winner} wins on the current scoring because its argument better balanced claim strength, rebuttal quality, and accuracy. "
            f"The Pro side was strongest when it explained why '{topic}' could improve on the status quo. "
            "The Con side was strongest when it challenged feasibility, tradeoffs, and overbroad claims.\n\n"
            "The verified-facts layer treated broad claims cautiously and rewarded qualified claims more than sweeping ones. "
            "When live source access is available, external evidence should carry more weight than the local fallback analysis."
        )

    def _speaker_sections(self, user: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        pro = re.search(r"Pro:\s*(.+?)(?:\nCon:|\Z)", user, flags=re.S)
        con = re.search(r"Con:\s*(.+)", user, flags=re.S)
        if pro:
            sections["Pro Agent"] = pro.group(1).strip()
        if con:
            sections["Con Agent"] = con.group(1).strip()
        return sections

    def _topic(self, user: str) -> str:
        match = re.search(r"Topic:\s*(.+)", user)
        return match.group(1).strip() if match else "the debate topic"

    def _round_number(self, user: str) -> int:
        match = re.search(r"Round:\s*(\d+)", user)
        return int(match.group(1)) if match else 1

    def _subject_label(self, topic: str) -> str:
        if "ai" in topic.lower():
            return "AI"
        return topic.lower()
