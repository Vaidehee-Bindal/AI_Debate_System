import httpx

from ..config import get_settings


class TavilyClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str) -> list[dict[str, str]]:
        if not self.settings.tavily_api_key:
            return self._local_sources(query)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.settings.tavily_api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": 4,
                        "include_answer": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return self._local_sources(query)
        results = data.get("results", [])
        if not results:
            return self._local_sources(query)
        return [
            {
                "title": item.get("title") or "Source",
                "url": item.get("url") or "",
                "snippet": item.get("content") or "",
            }
            for item in results[:4]
        ]

    def _local_sources(self, query: str) -> list[dict[str, str]]:
        lowered = query.lower()
        if "ai" in lowered and ("software" in lowered or "engineer" in lowered or "coding" in lowered):
            return [
                {
                    "title": "Local evidence brief: task automation",
                    "url": "local://ai-software-task-automation",
                    "snippet": "AI coding tools are commonly used for drafting code, generating tests, explaining code, documentation, and first-pass troubleshooting. This supports claims about task-level automation more than total job replacement.",
                },
                {
                    "title": "Local evidence brief: human accountability",
                    "url": "local://ai-software-human-accountability",
                    "snippet": "Software engineering work also includes requirements analysis, architecture, security, maintenance, stakeholder tradeoffs, and accountability. This supports claims that full-role replacement is harder than automating isolated tasks.",
                },
                {
                    "title": "Local evidence brief: labor-market uncertainty",
                    "url": "local://ai-labor-market-uncertainty",
                    "snippet": "Productivity tools can reduce demand for some tasks while increasing demand for higher-level supervision, validation, and new projects. Claims about exact job-loss scale require live external evidence.",
                },
            ]
        return [
            *self._generic_sources(query),
        ]

    def _generic_sources(self, query: str) -> list[dict[str, str]]:
        pro_source = {
                "title": "Local evidence brief: pro considerations",
                "url": "local://generic-pro-considerations",
                "snippet": f"Supportive arguments for this topic should identify the problem being solved, the expected benefits, and the mechanism that connects the proposal to better outcomes. Query: {query[:120]}",
        }
        con_source = {
                "title": "Local evidence brief: con considerations",
                "url": "local://generic-con-considerations",
                "snippet": "Opposing arguments should test feasibility, unintended consequences, fairness, implementation cost, and whether a narrower alternative would solve the problem with less risk.",
        }
        limit_source = {
                "title": "Local evidence brief: verification limits",
                "url": "local://offline-verification-limits",
                "snippet": "Live Tavily search was unavailable from the running process, so factual claims should be treated as lower-confidence unless supported by external sources.",
        }
        lowered = query.lower()
        con_terms = ["cost", "tradeoff", "risk", "harm", "oppose", "against", "burden", "unfair", "not enough"]
        if any(term in lowered for term in con_terms):
            return [con_source, pro_source, limit_source]
        return [pro_source, con_source, limit_source]
