import re
from html.parser import HTMLParser

import httpx

from .base import Tool, ToolResult

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Sage/0.1)"}
_SKIP_TAGS = {"script", "style", "nav", "footer", "head", "noscript", "aside"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and (text := data.strip()):
            self.parts.append(text)


def _extract_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    text = " ".join(p.parts)
    return re.sub(r" {2,}", " ", text).strip()


def _web_fetch(inp: dict) -> ToolResult:
    url = inp["url"]
    try:
        with httpx.Client(follow_redirects=True, timeout=15, headers=_HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            text = _extract_text(r.text) if "html" in ct else r.text
            if len(text) > 12000:
                text = text[:12000] + f"\n\n[truncated — {len(text) - 12000} more chars]"
            return ToolResult(content=text)
    except httpx.HTTPStatusError as e:
        return ToolResult(content=f"HTTP {e.response.status_code}: {url}", is_error=True)
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


def _web_search(inp: dict) -> ToolResult:
    query = inp["query"]
    num = inp.get("num_results", 6)

    try:
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        with httpx.Client(follow_redirects=True, timeout=10, headers=_HEADERS) as client:
            r = client.get("https://api.duckduckgo.com/", params=params)
            data = r.json()

        results: list[str] = []

        if abstract := data.get("Abstract"):
            src = data.get("AbstractURL", "")
            results.append(f"**{data.get('Heading', 'Summary')}**\n{abstract}" + (f"\n{src}" if src else ""))

        for topic in data.get("RelatedTopics", [])[:num]:
            if not isinstance(topic, dict):
                continue
            text = topic.get("Text", "")
            url = topic.get("FirstURL", "")
            if text:
                results.append(f"• {text}" + (f"\n  {url}" if url else ""))

        if not results:
            return ToolResult(content=f"No results for: {query}")
        return ToolResult(content="\n\n".join(results))
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


web_fetch_tool = Tool(
    name="web_fetch",
    description="Fetch a URL and return its text content. Strips HTML tags automatically.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
        },
        "required": ["url"],
    },
    execute=_web_fetch,
)

web_search_tool = Tool(
    name="web_search",
    description="Search the web via DuckDuckGo and return summaries with links.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Results to return (default: 6)"},
        },
        "required": ["query"],
    },
    execute=_web_search,
)
