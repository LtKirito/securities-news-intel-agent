from __future__ import annotations

from typing import Any

from .models import ResearchTask
from .query_planner import dedupe_queries
from .sector_profile import SectorProfile

SOURCE_SITES = [
    "site:stcn.com",
    "site:cls.cn",
    "site:cs.com.cn",
    "site:cnstock.com",
    "site:eastmoney.com",
    "site:cninfo.com.cn",
]


def build_retry_search_plan(task: ResearchTask, profile: SectorProfile, quality_report: dict[str, Any], previous_queries: list[str]) -> dict[str, Any]:
    failures = quality_report.get("quality_gate", {}).get("failures", [])
    failure_metrics = {item.get("metric") for item in failures}
    queries: list[str] = []

    if "kept_items" in failure_metrics:
        queries.extend(_candidate_expansion_queries(task, profile))
    if "sa_source_ratio" in failure_metrics:
        queries.extend(_source_expansion_queries(profile))
    if "company_hit_ratio" in failure_metrics:
        queries.extend(_company_expansion_queries(profile))
    if "english_or_overseas_ratio" in failure_metrics:
        queries.extend(_source_expansion_queries(profile))

    if not queries:
        queries.extend(_candidate_expansion_queries(task, profile))

    previous = set(previous_queries)
    retry_queries = [query for query in dedupe_queries(queries) if query not in previous]
    return {
        "retry_reason": failures,
        "date": task.date,
        "date_window": task.date_window,
        "sectors": task.sectors,
        "queries": retry_queries[:24],
        "profile_suggestions": build_profile_suggestions(profile, failure_metrics),
        "persist_suggestions": False,
    }


def build_profile_suggestions(profile: SectorProfile, failure_metrics: set[str]) -> dict[str, Any]:
    suggestions: dict[str, Any] = {
        "companies_to_consider": [],
        "keywords_to_consider": [],
        "aliases_to_consider": [],
        "reason": "由质量门控失败后的扩展检索发现，默认仅用于当前run；永久写入需用户确认。",
    }
    if profile.sector.upper() == "PCB":
        suggestions["companies_to_consider"] = ["兴森科技", "崇达技术", "依顿电子", "世运电路", "奥士康", "方正科技", "金安国纪", "华正新材"]
        suggestions["keywords_to_consider"] = ["高多层板", "高速板", "覆铜板", "CCL", "AI服务器PCB", "服务器PCB", "IC载板", "HDI"]
    if "company_hit_ratio" in failure_metrics:
        suggestions["reason"] = "公司命中不足，建议补充板块上市公司和常用简称/英文别名。"
    return suggestions


def _candidate_expansion_queries(task: ResearchTask, profile: SectorProfile) -> list[str]:
    sector = profile.sector
    queries: list[str] = []
    for company in profile.companies[:12]:
        for keyword in profile.keywords[:4]:
            queries.append(f"{company} {keyword} 订单 业绩 公告")
        for event in profile.event_types[:4]:
            queries.append(f"{company} {sector} {event} 最新")
    for node in profile.supply_chain_nodes[:8]:
        for event in profile.event_types[:4]:
            queries.append(f"{sector} {node} {event} 上市公司")
    for keyword in profile.keywords[:10]:
        queries.append(f"{keyword} 上市公司 订单 扩产 业绩")
        queries.append(f"{keyword} 财联社 证券时报 东方财富")
    return queries


def _source_expansion_queries(profile: SectorProfile) -> list[str]:
    sector = profile.sector
    queries: list[str] = []
    for site in SOURCE_SITES:
        queries.append(f"{site} {sector} 上市公司 订单")
        queries.append(f"{site} {sector} 公告 扩产")
        queries.append(f"{site} {sector} 业绩 涨价")
    for company in profile.companies[:10]:
        for site in SOURCE_SITES[:4]:
            queries.append(f"{site} {company} {sector} 最新")
    return queries


def _company_expansion_queries(profile: SectorProfile) -> list[str]:
    queries: list[str] = []
    for company in profile.companies[:16]:
        queries.append(f"{company} 公告 订单 量产")
        queries.append(f"{company} 投资者关系 互动易")
        queries.append(f"{company} 财联社 证券时报")
    return queries
