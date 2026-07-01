from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .models import SearchResult


class TavilyProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "topic": "news",
            "max_results": max_results,
            "include_raw_content": True,
            "include_answer": False,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("results", []) or []:
            url = str(item.get("url") or "")
            if not url:
                continue
            results.append(SearchResult(
                provider="tavily",
                query=query,
                title=str(item.get("title") or "").strip(),
                url=url,
                source_name=host_name(url),
                summary=str(item.get("content") or "").strip(),
                published_at=str(item.get("published_date") or "").strip(),
                raw_content=str(item.get("raw_content") or "").strip(),
                score=float(item.get("score") or 0),
            ))
        return results


class SearXNGProvider:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "categories": "news,general",
            "language": "zh-CN",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=15.0), follow_redirects=True) as client:
            response = await client.get(f"{self.base_url}/search", params=params)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in (data.get("results", []) or [])[:max_results]:
            url = str(item.get("url") or "")
            if not url:
                continue
            results.append(SearchResult(
                provider="searxng",
                query=query,
                title=str(item.get("title") or "").strip(),
                url=url,
                source_name=host_name(url),
                summary=str(item.get("content") or "").strip(),
                published_at=str(item.get("publishedDate") or item.get("published_date") or "").strip(),
                raw_content="",
                score=float(item.get("score") or 0),
            ))
        return results


class GNewsProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        params = {
            "q": query,
            "lang": "zh",
            "country": "cn",
            "max": min(max_results, 10),
            "apikey": self.api_key,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=15.0)) as client:
            response = await client.get("https://gnews.io/api/v4/search", params=params)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("articles", []) or []:
            url = str(item.get("url") or "")
            if not url:
                continue
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            results.append(SearchResult(
                provider="gnews",
                query=query,
                title=str(item.get("title") or "").strip(),
                url=url,
                source_name=str(source.get("name") or host_name(url)).strip(),
                summary=str(item.get("description") or item.get("content") or "").strip(),
                published_at=str(item.get("publishedAt") or "").strip(),
                raw_content=str(item.get("content") or "").strip(),
                score=0.0,
            ))
        return results


def host_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "未知来源"
