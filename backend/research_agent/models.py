from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchTask:
    date: str
    sectors: list[str]
    keywords: list[str]
    user_id: str = "1"
    date_window: str = "滚动24小时"
    max_results_per_query: int = 8
    max_candidates: int = 30
    include_domains: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    runtime_sector_config: list[dict[str, Any]] = field(default_factory=list)
    display_preferences: dict[str, Any] = field(default_factory=dict)
    rating_overlay: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchTask":
        sectors = data.get("sectors") or ([data["sector"]] if data.get("sector") else [])
        keywords = data.get("keywords") or []
        if not sectors:
            raise ValueError("task must include sectors or sector")
        if not keywords:
            raise ValueError("task must include keywords")
        return cls(
            date=str(data["date"]),
            sectors=[str(item).strip() for item in sectors if str(item).strip()],
            keywords=[str(item).strip() for item in keywords if str(item).strip()],
            user_id=str(data.get("user_id", "1")),
            date_window=str(data.get("date_window", "滚动24小时")),
            max_results_per_query=int(data.get("max_results_per_query", 8)),
            max_candidates=int(data.get("max_candidates", 30)),
            include_domains=[str(item).strip() for item in data.get("include_domains", []) if str(item).strip()],
            exclude_domains=[str(item).strip() for item in data.get("exclude_domains", []) if str(item).strip()],
            runtime_sector_config=list(data.get("runtime_sector_config", [])),
            display_preferences=dict(data.get("display_preferences", {})),
            rating_overlay=dict(data.get("rating_overlay", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "user_id": self.user_id,
            "date_window": self.date_window,
            "sectors": self.sectors,
            "keywords": self.keywords,
            "max_results_per_query": self.max_results_per_query,
            "max_candidates": self.max_candidates,
            "include_domains": self.include_domains,
            "exclude_domains": self.exclude_domains,
            "runtime_sector_config": self.runtime_sector_config,
            "display_preferences": self.display_preferences,
            "rating_overlay": self.rating_overlay,
        }


@dataclass
class SearchResult:
    provider: str
    query: str
    title: str
    url: str
    source_name: str
    summary: str = ""
    published_at: str = ""
    raw_content: str = ""
    score: float = 0.0


@dataclass
class Candidate:
    title: str
    summary: str
    source_name: str
    source_tier: str
    url: str
    collection_mode: str
    matched_sector: str
    matched_keywords: list[str]
    published_at: str = ""
    is_primary_source: bool = False
    related_companies: list[str] = field(default_factory=list)
    raw_text_excerpt: str = ""
    provider: str = ""

    def to_schema_item(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.title,
            "summary": self.summary,
            "source_name": self.source_name,
            "source_tier": self.source_tier,
            "url": self.url,
            "collection_mode": self.collection_mode,
            "matched_sector": self.matched_sector,
            "matched_keywords": self.matched_keywords,
            "is_primary_source": self.is_primary_source,
            "related_companies": self.related_companies,
            "raw_text_excerpt": self.raw_text_excerpt,
        }
        if self.published_at:
            payload["published_at"] = self.published_at
        return payload
