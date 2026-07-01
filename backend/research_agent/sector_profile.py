from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import CONFIG_DIR

from .models import ResearchTask


@dataclass
class SectorProfile:
    sector: str
    aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    company_aliases: dict[str, list[str]] = field(default_factory=dict)
    supply_chain_nodes: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    preferred_sources: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    p0_rules: list[str] = field(default_factory=list)
    p1_rules: list[str] = field(default_factory=list)
    profile_status: str = "curated"
    profile_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "aliases": self.aliases,
            "keywords": self.keywords,
            "companies": self.companies,
            "company_aliases": self.company_aliases,
            "supply_chain_nodes": self.supply_chain_nodes,
            "event_types": self.event_types,
            "preferred_sources": self.preferred_sources,
            "exclude_terms": self.exclude_terms,
            "p0_rules": self.p0_rules,
            "p1_rules": self.p1_rules,
            "profile_status": self.profile_status,
            "profile_warnings": self.profile_warnings,
        }


def build_sector_profile(task: ResearchTask) -> SectorProfile:
    sector = task.sectors[0]
    builtin = _load_builtin_profile(sector)
    profile = builtin or _temporary_profile(sector, task)
    profile.sector = sector
    profile.aliases = _merge_unique(profile.aliases, task.sectors)
    profile.keywords = _merge_unique(profile.keywords, task.keywords)

    for config in task.runtime_sector_config:
        profile.keywords = _merge_unique(profile.keywords, _as_list(config.get("keywords")))
        profile.companies = _merge_unique(profile.companies, _as_list(config.get("companies")))
        profile.company_aliases = _merge_aliases(profile.company_aliases, config.get("company_aliases"))
        profile.supply_chain_nodes = _merge_unique(profile.supply_chain_nodes, _as_list(config.get("supply_chain_nodes") or config.get("nodes")))
        profile.event_types = _merge_unique(profile.event_types, _as_list(config.get("event_types")))
        profile.preferred_sources = _merge_unique(profile.preferred_sources, _as_list(config.get("preferred_sources")))
        profile.exclude_terms = _merge_unique(profile.exclude_terms, _as_list(config.get("exclude_terms")))

    if not profile.event_types:
        profile.event_types = ["订单", "量产", "扩产", "定点", "业绩", "价格", "政策", "合作"]
    if not profile.preferred_sources:
        profile.preferred_sources = ["巨潮资讯", "互动易", "财联社", "证券时报", "东方财富"]
    if not profile.p0_rules:
        profile.p0_rules = ["公告或S/A来源验证的订单、量产、扩产、定点、价格或业绩变化"]
    if not profile.p1_rules:
        profile.p1_rules = ["机构预测、融资、新品、展会、单源媒体报道或缺少订单验证的趋势信息"]
    return profile


def _load_builtin_profile(sector: str) -> SectorProfile | None:
    profiles_dir = CONFIG_DIR / "sector_profiles"
    for path in profiles_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        aliases = _as_list(data.get("aliases"))
        if sector == path.stem or sector in aliases or any(alias in sector or sector in alias for alias in aliases):
            return SectorProfile(
                sector=sector,
                aliases=aliases,
                keywords=_as_list(data.get("keywords")),
                companies=_as_list(data.get("companies")),
                company_aliases=_normalize_aliases(data.get("company_aliases")),
                supply_chain_nodes=_as_list(data.get("supply_chain_nodes")),
                event_types=_as_list(data.get("event_types")),
                preferred_sources=_as_list(data.get("preferred_sources")),
                exclude_terms=_as_list(data.get("exclude_terms")),
                p0_rules=_as_list(data.get("p0_rules")),
                p1_rules=_as_list(data.get("p1_rules")),
                profile_status="curated",
                profile_warnings=[],
            )
    return None


def _temporary_profile(sector: str, task: ResearchTask) -> SectorProfile:
    base_keywords = [
        sector,
        "公告",
        "投资者关系",
        "互动易",
        "订单",
        "量产",
        "扩产",
        "业绩",
        "涨价",
        "风险提示",
        "异动",
    ]
    return SectorProfile(
        sector=sector,
        aliases=[sector],
        keywords=_merge_unique(task.keywords, base_keywords),
        companies=[],
        company_aliases={},
        supply_chain_nodes=[sector],
        event_types=["订单", "量产", "扩产", "涨价", "业绩", "客户验证", "产能", "风险提示", "异动"],
        preferred_sources=["巨潮资讯", "互动易", "上证e互动", "财联社", "证券时报", "东方财富", "第一财经", "21财经"],
        exclude_terms=["股吧", "论坛", "百科", "课程", "广告", "二手", "下载"],
        p0_rules=["公告或S/A来源验证的订单、量产、扩产、价格、业绩或风险提示变化"],
        p1_rules=["机构预测、单源媒体报道、无公司映射的行业趋势或缺少公告验证的信息"],
        profile_status="temporary",
        profile_warnings=["该板块暂无成熟画像，系统已使用临时画像采集。建议补充 5-15 家代表上市公司以提升准确率。"],
    )


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            normalized = str(item).strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


def _normalize_aliases(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    aliases: dict[str, list[str]] = {}
    for key, items in value.items():
        company = str(key).strip()
        if company:
            aliases[company] = _as_list(items)
    return aliases


def _merge_aliases(base: dict[str, list[str]], overlay: Any) -> dict[str, list[str]]:
    merged = {key: list(value) for key, value in base.items()}
    for company, aliases in _normalize_aliases(overlay).items():
        merged[company] = _merge_unique(merged.get(company, []), aliases)
    return merged
