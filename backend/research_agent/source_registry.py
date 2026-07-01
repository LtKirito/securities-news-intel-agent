from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode, urljoin, urlparse

import httpx

from app.core.config import PROJECT_ROOT

from .models import ResearchTask, SearchResult
from .query_planner import dedupe_queries
from .sector_profile import SectorProfile

REGISTRY_PATH = PROJECT_ROOT / "config" / "source_registry.json"


@dataclass
class RegistrySource:
    name: str
    tier: str
    type: str
    search_url_template: str
    url_allow_patterns: list[str]
    index_urls: list[str]
    enabled: bool = True


class SourceRegistryProvider:
    def __init__(self, registry_path: Path = REGISTRY_PATH):
        self.registry = load_registry(registry_path)
        self.sources = load_sources(self.registry)
        self.debug_events: list[dict[str, Any]] = []

    async def search(self, task: ResearchTask, profile: SectorProfile, max_results: int) -> list[SearchResult]:
        queries = build_registry_queries(task, profile, self.registry)
        results: list[SearchResult] = []
        limit = max_results * max(len(self.sources), 1) * 6
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
            results.extend(await self._fetch_cninfo_announcements(client, task, profile))
            for source in self.sources:
                for index_url in source.index_urls:
                    results.extend(await self._fetch_index(client, source, index_url, task, profile))
                    if len(results) >= limit:
                        return unique_results(results)
                if source.search_url_template:
                    for query in queries:
                        search_url = source.search_url_template.format(query=quote_plus(query))
                        results.extend(await self._fetch_search_page(client, source, search_url, query))
                        if len(results) >= limit:
                            return unique_results(results)
        return unique_results(results)


    async def _fetch_cninfo_announcements(self, client: httpx.AsyncClient, task: ResearchTask, profile: SectorProfile) -> list[SearchResult]:
        results: list[SearchResult] = []
        for company in profile.companies:
            url = "http://www.cninfo.com.cn/new/fulltextSearch/full?" + urlencode({
                "searchkey": company,
                "sortName": "pubdate",
                "sortType": "desc",
                "pageNum": "1",
            })
            try:
                response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 ResearchAgent/0.1"})
                response.raise_for_status()
                payload = response.json()
            except Exception as error:
                self.debug_events.append({
                    "source": "巨潮资讯",
                    "mode": "cninfo_notice",
                    "query": company,
                    "search_url": url,
                    "error_type": type(error).__name__,
                    "error": str(error),
                })
                continue
            announcements = payload.get("announcements") or []
            matched = []
            for item in announcements[:8]:
                title = clean_html(str(item.get("announcementTitle") or item.get("shortTitle") or ""))
                adjunct_url = str(item.get("adjunctUrl") or "")
                if not title or not adjunct_url:
                    continue
                if not notice_matches_profile(title, company, task, profile):
                    continue
                published_at = timestamp_ms_to_iso(item.get("announcementTime"))
                full_url = urljoin("http://static.cninfo.com.cn/", adjunct_url)
                matched.append(SearchResult(
                    provider="source_registry",
                    query=company,
                    title=title,
                    url=full_url,
                    source_name="巨潮资讯",
                    summary=title,
                    published_at=published_at,
                    raw_content=title,
                    score=0.0,
                ))
            self.debug_events.append({
                "source": "巨潮资讯",
                "mode": "cninfo_notice",
                "query": company,
                "search_url": url,
                "status_code": response.status_code,
                "announcement_count": len(announcements),
                "matched_link_count": len(matched),
            })
            results.extend(matched)
        return results

    async def _fetch_index(self, client: httpx.AsyncClient, source: RegistrySource, index_url: str, task: ResearchTask, profile: SectorProfile) -> list[SearchResult]:
        try:
            response = await client.get(index_url, headers={"User-Agent": "Mozilla/5.0 ResearchAgent/0.1"})
            response.raise_for_status()
        except Exception as error:
            self.debug_events.append({
                "source": source.name,
                "mode": "index_page",
                "index_url": index_url,
                "error_type": type(error).__name__,
                "error": str(error),
            })
            return []
        links = extract_links(response.text, str(response.url), source.url_allow_patterns)
        matched_links = [(url, title) for url, title in links if matches_profile(title, url, task, profile)]
        self.debug_events.append({
            "source": source.name,
            "mode": "index_page",
            "index_url": index_url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "html_length": len(response.text),
            "link_count": len(links),
            "matched_link_count": len(matched_links),
        })
        return [
            SearchResult(
                provider="source_registry",
                query="index_page",
                title=title or url,
                url=url,
                source_name=source.name,
                summary=title or url,
                published_at="",
                raw_content="",
                score=0.0,
            )
            for url, title in matched_links
        ]

    async def _fetch_search_page(self, client: httpx.AsyncClient, source: RegistrySource, search_url: str, query: str) -> list[SearchResult]:
        try:
            response = await client.get(search_url, headers={"User-Agent": "Mozilla/5.0 ResearchAgent/0.1"})
            response.raise_for_status()
        except Exception as error:
            self.debug_events.append({
                "source": source.name,
                "mode": "search_page",
                "query": query,
                "search_url": search_url,
                "error_type": type(error).__name__,
                "error": str(error),
            })
            return []
        links = extract_links(response.text, str(response.url), source.url_allow_patterns)
        self.debug_events.append({
            "source": source.name,
            "mode": "search_page",
            "query": query,
            "search_url": search_url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "html_length": len(response.text),
            "link_count": len(links),
        })
        return [
            SearchResult(
                provider="source_registry",
                query=query,
                title=title or query,
                url=url,
                source_name=source.name,
                summary=query,
                published_at="",
                raw_content="",
                score=0.0,
            )
            for url, title in links
        ]


def load_registry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_sources(registry: dict[str, Any]) -> list[RegistrySource]:
    sources = []
    for item in registry.get("sources", []):
        if not item.get("enabled", True):
            continue
        if item.get("type") not in {"search_page", "hybrid", "index_page"}:
            continue
        sources.append(RegistrySource(
            name=str(item.get("name", "")),
            tier=str(item.get("tier", "B")),
            type=str(item.get("type", "search_page")),
            search_url_template=str(item.get("search_url_template", "")),
            url_allow_patterns=[str(pattern) for pattern in item.get("url_allow_patterns", [])],
            index_urls=[str(url) for url in item.get("index_urls", []) if str(url).strip()],
        ))
    return [source for source in sources if source.name and (source.search_url_template or source.index_urls)]


def notice_matches_profile(title: str, company: str, task: ResearchTask, profile: SectorProfile) -> bool:
    haystack = title.lower()
    weak_notice_terms = ["异动", "异常波动", "股票交易", "问询函", "问询回复", "审核问询", "再融资", "向特定对象发行", "权益变动", "减持", "质押", "现金管理", "理财", "股权激励", "员工持股"]
    if any(term.lower() in haystack for term in weak_notice_terms):
        return False
    strong_terms = profile.aliases + profile.supply_chain_nodes + [term for term in profile.keywords if term not in {"涨价", "订单", "扩产", "业绩", "稼动率", "汽车电子"}]
    operating_event_terms = ["业绩", "投资者关系", "调研", "日常经营", "重大合同", "订单", "产能", "扩产", "涨价", "价格", "稼动率", "客户", "认证", "验证", "良率", "交期"]
    if any(term and term.lower() in haystack for term in strong_terms) and any(term.lower() in haystack for term in operating_event_terms):
        return True
    return company.lower() in haystack and any(term.lower() in haystack for term in operating_event_terms)


def timestamp_ms_to_iso(value: Any) -> str:
    try:
        timestamp = int(value) / 1000
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def matches_profile(title: str, url: str, task: ResearchTask, profile: SectorProfile) -> bool:
    haystack = f"{title} {url}".lower()
    terms = []
    terms.extend(task.sectors)
    terms.extend(profile.aliases)
    terms.extend(profile.companies)
    terms.extend(profile.supply_chain_nodes)
    for aliases in profile.company_aliases.values():
        terms.extend(aliases)
    return any(term and term.lower() in haystack for term in terms)


def build_registry_queries(task: ResearchTask, profile: SectorProfile, registry: dict[str, Any]) -> list[str]:
    rules = registry.get("query_terms", {})
    templates = rules.get("templates", []) or ["{sector}", "{company}", "{keyword} 上市公司"]
    companies = profile.companies[: int(rules.get("max_companies", 8))]
    keywords = profile.keywords[: int(rules.get("max_keywords", 8))]
    values = []
    for template in templates:
        if "{company}" in template and "{keyword}" in template:
            for company in companies:
                for keyword in keywords[:4]:
                    values.append(template.format(sector=profile.sector, company=company, keyword=keyword))
        elif "{company}" in template:
            for company in companies:
                values.append(template.format(sector=profile.sector, company=company, keyword=keywords[0] if keywords else profile.sector))
        elif "{keyword}" in template:
            for keyword in keywords:
                values.append(template.format(sector=profile.sector, company=companies[0] if companies else profile.sector, keyword=keyword))
        else:
            values.append(template.format(sector=profile.sector, company=companies[0] if companies else profile.sector, keyword=keywords[0] if keywords else profile.sector))
    return dedupe_queries(values)[:24]


def extract_links(html: str, base_url: str, allow_patterns: list[str]) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    anchor_pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for match in anchor_pattern.finditer(html):
        href = match.group(1).strip()
        if not href or href.startswith(("javascript:", "#")):
            continue
        url = urljoin(base_url, href)
        if not is_allowed_url(url, allow_patterns):
            continue
        title = clean_html(match.group(2))
        links.append((url, title))

    url_pattern = re.compile(r'https?://[^\s"\'<>\\]+|/(?:a|detail)/\d+[^\s"\'<>\\]*', re.I)
    for match in url_pattern.finditer(html):
        raw_url = match.group(0).rstrip(".,);]")
        url = urljoin(base_url, raw_url)
        if not is_allowed_url(url, allow_patterns):
            continue
        links.append((url, ""))
    return unique_link_pairs(links)


def is_allowed_url(url: str, allow_patterns: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    haystack = url.lower()
    return any(pattern.lower() in haystack for pattern in allow_patterns)


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"&nbsp;|&#160;", " ", value)
    value = re.sub(r"&amp;", "&", value)
    return re.sub(r"\s+", " ", value).strip()


def unique_link_pairs(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = set()
    unique = []
    for url, title in links:
        key = url.split("?", 1)[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        unique.append((url, title))
    return unique


def unique_results(results: list[SearchResult]) -> list[SearchResult]:
    seen = set()
    unique = []
    for result in results:
        key = result.url.split("?", 1)[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique
