from __future__ import annotations

import asyncio

import httpx
import trafilatura

from .models import SearchResult


async def enrich_pages(results: list[SearchResult], concurrency: int = 10) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_one(result: SearchResult) -> dict:
        if len(result.raw_content) >= 800:
            return {"url": result.url, "ok": True, "provider": result.provider, "text": result.raw_content, "source": "provider_raw_content"}
        async with semaphore:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=True) as client:
                    response = await client.get(result.url, headers={"User-Agent": "Mozilla/5.0 ResearchAgent/0.1"})
                    response.raise_for_status()
                    extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False) or ""
                    return {"url": result.url, "ok": bool(extracted), "provider": result.provider, "text": extracted, "source": "trafilatura"}
            except Exception as exc:  # noqa: BLE001 - collect extraction failures as artifacts
                return {"url": result.url, "ok": False, "provider": result.provider, "text": "", "source": "trafilatura", "error": str(exc)[:300]}

    return await asyncio.gather(*(fetch_one(result) for result in results))
