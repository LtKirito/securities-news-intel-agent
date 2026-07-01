from __future__ import annotations

from .models import ResearchTask
from .sector_profile import SectorProfile


CHINA_MARKET_TERMS = ["财联社", "证券时报", "中国证券报", "上海证券报", "第一财经", "21财经", "东方财富", "巨潮资讯"]
ANNOUNCEMENT_TERMS = ["公告", "投资者关系", "调研纪要", "互动易", "业绩说明会"]


def build_search_plan(task: ResearchTask, profile: SectorProfile) -> dict:
    queries: list[str] = []
    sector = profile.sector

    queries.extend([
        f"site:cninfo.com.cn {sector} 公告 订单 量产",
        f"site:cninfo.com.cn {sector} 投资者关系 互动易",
        f"site:cls.cn {sector} 上市公司 订单 量产",
        f"site:stcn.com {sector} 上市公司 公告",
        f"site:cs.com.cn {sector} 上市公司 最新",
        f"site:cnstock.com {sector} 上市公司 最新",
        f"site:eastmoney.com {sector} 互动易 投资者关系",
        f"{sector} A股 上市公司 订单 量产 最新",
        f"{sector} 产业链 上市公司 公告 最新",
        f"{sector} 财联社 证券时报 最新 新闻",
        f"{sector} 东方财富 互动易 投资者关系",
    ])
    if sector.upper() == "PCB" or "印制电路板" in profile.aliases:
        queries.extend([
            "AI服务器 PCB 订单 扩产 最新",
            "AI服务器 高多层板 HDI 需求 最新",
            "PCB 覆铜板 涨价 稼动率 最新",
            "PCB 铜箔 玻纤布 涨价 供需 最新",
            "沪电股份 胜宏科技 深南电路 AI服务器 订单",
            "生益科技 覆铜板 涨价 稼动率",
            "PCB 产业链 客户认证 业绩预告 最新",
            "高速PCB 高频高速材料 需求增长 最新",
        ])
    for market_term in profile.preferred_sources[:8] or CHINA_MARKET_TERMS[:6]:
        queries.append(f"{sector} {market_term} 上市公司 最新")
    for announcement_term in ANNOUNCEMENT_TERMS:
        queries.append(f"{sector} 上市公司 {announcement_term}")
    for company in profile.companies[:8]:
        queries.append(f"{company} {sector} 订单 量产 公告")
        queries.append(f"{company} 投资者关系 互动易 公告")
    for keyword in profile.keywords[:6]:
        queries.append(f"{keyword} A股 上市公司 订单 量产")
        queries.append(f"{keyword} 产业链 财联社 证券时报")
    for node in profile.supply_chain_nodes[:5]:
        queries.append(f"{sector} {node} 上市公司 最新")
    for event_type in profile.event_types[:5]:
        queries.append(f"{sector} {event_type} {task.date_window} A股 上市公司")

    unique_queries = dedupe_queries(queries)
    return {
        "date": task.date,
        "date_window": task.date_window,
        "sectors": task.sectors,
        "sector_profile": profile.to_dict(),
        "keywords": profile.keywords,
        "companies": profile.companies,
        "queries": unique_queries[:32],
    }


def dedupe_queries(queries: list[str]) -> list[str]:
    seen = set()
    unique_queries = []
    for query in queries:
        normalized = " ".join(query.split())
        if normalized not in seen:
            seen.add(normalized)
            unique_queries.append(normalized)
    return unique_queries
