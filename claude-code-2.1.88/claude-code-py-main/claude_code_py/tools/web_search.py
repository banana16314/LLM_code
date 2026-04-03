"""Web search tool — uses LLM's built-in search or Tavily API."""

from __future__ import annotations

import os
from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult


class WebSearchTool(BaseTool):
    name = "WebSearch"
    description = (
        "Search the web for current information. "
        "Returns search results with links. "
        "Use for accessing information beyond the knowledge cutoff."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
                "minLength": 2,
            },
            "allowed_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results from these domains",
            },
            "blocked_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results from these domains",
            },
        },
        "required": ["query"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        return f"Search: {args.get('query', '')}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(error="query is required", is_error=True)

        # Strategy 1: Tavily API (if key available)
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            return await self._search_tavily(query, args, tavily_key)

        # Strategy 2: Use the LLM itself with enable_search (DashScope Qwen supports this)
        return await self._search_via_llm(query, context)

    async def _search_tavily(self, query: str, args: dict, api_key: str) -> ToolResult:
        """Search using Tavily API."""
        try:
            import httpx
        except ImportError:
            return ToolResult(error="httpx required. pip install httpx", is_error=True)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                payload = {
                    "query": query,
                    "api_key": api_key,
                    "search_depth": "basic",
                    "max_results": 5,
                }
                if args.get("allowed_domains"):
                    payload["include_domains"] = args["allowed_domains"]
                if args.get("blocked_domains"):
                    payload["exclude_domains"] = args["blocked_domains"]

                resp = await client.post("https://api.tavily.com/search", json=payload)
                data = resp.json()

            results = data.get("results", [])
            if not results:
                return ToolResult(output="No results found.")

            lines = []
            for r in results[:8]:
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("content", "")[:200]
                lines.append(f"**{title}**\n{url}\n{snippet}\n")

            return ToolResult(output="\n".join(lines))

        except Exception as e:
            return ToolResult(error=f"Tavily search failed: {e}", is_error=True)

    async def _search_via_llm(self, query: str, context: ToolContext) -> ToolResult:
        """Fallback: ask the LLM to search (Qwen supports enable_search).

        This mirrors the source Claude Code approach — use the model's built-in
        web search capability rather than calling an external search API.
        """
        from ..llm.client import LLMClient
        from ..config import config

        try:
            client = LLMClient()

            # DashScope Qwen supports enable_search parameter
            # Use a lightweight call to perform the search
            from openai import AsyncOpenAI
            raw_client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )

            response = await raw_client.chat.completions.create(
                model=config.model,
                messages=[
                    {"role": "system", "content": "You are a web search assistant. Return search results with titles and URLs. Be concise."},
                    {"role": "user", "content": f"Search the web for: {query}"},
                ],
                max_tokens=2048,
                # DashScope Qwen supports this parameter for web search
                extra_body={"enable_search": True},
            )

            content = response.choices[0].message.content or ""
            if not content.strip():
                return ToolResult(output="No search results returned.")

            return ToolResult(output=content)

        except Exception as e:
            return ToolResult(
                error=f"Search failed: {e}. Set TAVILY_API_KEY for reliable search.",
                is_error=True,
            )
