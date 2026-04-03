"""Web fetch tool — HTTP fetch + optional LLM processing, mirrors Claude Code WebFetchTool."""

from __future__ import annotations

import re
import time

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
MAX_MARKDOWN_LENGTH = 100_000  # chars before truncation
FETCH_TIMEOUT = 60  # seconds
CACHE_TTL = 900  # 15 minutes

# Simple in-memory LRU cache
_cache: dict[str, tuple[float, str]] = {}


class WebFetchTool(BaseTool):
    name = "WebFetch"
    description = (
        "Fetches content from a URL, converts HTML to markdown, and processes it with a prompt. "
        "Includes a 15-minute cache. HTTP URLs are auto-upgraded to HTTPS. "
        "For GitHub URLs, prefer using gh CLI via Bash instead."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
                "format": "uri",
            },
            "prompt": {
                "type": "string",
                "description": "What information to extract from the page",
            },
        },
        "required": ["url", "prompt"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        url = args.get("url", "")
        prompt = args.get("prompt", "")[:60]
        return f"Fetch: {url}\n  Prompt: {prompt}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        url = args.get("url", "")
        prompt = args.get("prompt", "")

        if not url:
            return ToolResult(error="url is required", is_error=True)
        if not prompt:
            return ToolResult(error="prompt is required", is_error=True)

        # Upgrade http to https
        if url.startswith("http://"):
            url = "https://" + url[7:]

        # Check cache
        now = time.time()
        cache_key = f"{url}:{prompt}"
        if cache_key in _cache:
            cached_time, cached_content = _cache[cache_key]
            if now - cached_time < CACHE_TTL:
                return ToolResult(output=cached_content)

        try:
            import httpx
        except ImportError:
            return ToolResult(error="httpx required. pip install httpx", is_error=True)

        start = time.monotonic()

        try:
            async with httpx.AsyncClient(
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
                max_redirects=10,
            ) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClaudeCode/1.0)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                })

            body = resp.text
            if len(body) > MAX_CONTENT_LENGTH:
                return ToolResult(error=f"Content too large: {len(body)} bytes (max {MAX_CONTENT_LENGTH})", is_error=True)

            content_type = resp.headers.get("content-type", "")
            duration_ms = int((time.monotonic() - start) * 1000)

            # Convert HTML to markdown
            if "html" in content_type:
                markdown = _html_to_markdown(body)
            else:
                markdown = body

            if len(markdown) > MAX_MARKDOWN_LENGTH:
                markdown = markdown[:MAX_MARKDOWN_LENGTH] + "\n\n... (content truncated)"

            # Process with LLM if content is large (mirrors source: applyPromptToMarkdown)
            if len(markdown) > 500 and prompt:
                processed = await self._apply_prompt(markdown, prompt)
            else:
                processed = markdown

            result = (
                f"URL: {url}\n"
                f"Status: {resp.status_code} ({duration_ms}ms, {len(body)} bytes)\n\n"
                f"{processed}"
            )

            # Update cache
            _cache[cache_key] = (now, result)
            _clean_cache(now)

            return ToolResult(output=result)

        except Exception as e:
            return ToolResult(error=f"Fetch failed: {e}", is_error=True)

    async def _apply_prompt(self, markdown: str, prompt: str) -> str:
        """Use LLM to extract/summarize based on prompt (mirrors source applyPromptToMarkdown)."""
        try:
            from ..llm.client import LLMClient
            client = LLMClient()
            content = markdown[:30_000]
            result = await client.chat(
                messages=[
                    {"role": "system", "content": "Extract the requested information from the web page content. Be concise."},
                    {"role": "user", "content": f"Web page content:\n\n{content}\n\n---\n\nRequest: {prompt}"},
                ],
                stream=False,
            )
            return result.content if result.content else markdown[:2000]
        except Exception:
            return markdown[:2000]


def _html_to_markdown(html: str) -> str:
    """Convert HTML to markdown."""
    try:
        from markdownify import markdownify
        return markdownify(html, strip=["img", "script", "style"])
    except ImportError:
        pass
    # Fallback
    text = html
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n## \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_cache(now: float):
    expired = [k for k, (t, _) in _cache.items() if now - t > CACHE_TTL]
    for k in expired:
        del _cache[k]
