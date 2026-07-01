from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from .models import Candidate, ResearchTask, SearchResult
from .sector_profile import SectorProfile

TIER_HINTS = [
    ("cninfo.com.cn", "S", "巨潮资讯"),
    ("www.cninfo.com.cn", "S", "巨潮资讯"),
    ("sse.com.cn", "S", "上交所"),
    ("szse.cn", "S", "深交所"),
    ("irm.cninfo.com.cn", "S", "互动易"),
    ("sns.sseinfo.com", "S", "上证e互动"),
    ("eastmoney.com", "A", "东方财富"),
    ("stcn.com", "A", "证券时报"),
    ("cs.com.cn", "A", "中国证券报"),
    ("cnstock.com", "A", "上海证券报"),
    ("cls.cn", "A", "财联社"),
    ("10jqka.com.cn", "A", "同花顺"),
    ("sina.com.cn", "A", "新浪财经"),
    ("yicai.com", "A", "第一财经"),
    ("21jingji.com", "A", "21世纪经济报道"),
    ("21caijing.com", "A", "21财经"),
    ("cnr.cn", "A", "央广网"),
    ("jrj.com.cn", "B", "金融界"),
    ("hexun.com", "B", "和讯网"),
    ("thepaper.cn", "B", "澎湃新闻"),
    ("xueqiu.com", "C", "雪球"),
    ("guba", "X", "股吧"),
]

NOISE_HINTS = ["股吧", "论坛", "贴吧", "博彩", "下载", "百科", "招聘", "广告", "课程", "目标价", "荐股"]
PDF_HINTS = [".pdf", "研报", "研究报告", "招股说明书"]
MARKET_SIGNAL_TERMS = ["上市", "a股", "公告", "订单", "量产", "定点", "扩产", "业绩", "投资者关系", "互动易", "供应链", "产能"]
GENERIC_CORE_SECTOR_TERMS = ["机器人", "人形机器人", "工业机器人", "具身智能", "协作机器人", "机器视觉", "灵巧手", "关节模组", "Orbbec", "Lingyi", "Leaderdrive"]
WEAK_EVENT_TERMS = {"价格", "合作", "产能", "订单", "量产", "扩产", "业绩"}
INDUSTRY_SIGNAL_TERMS = ["订单", "量产", "扩产", "产能", "稼动率", "产能利用率", "涨价", "价格上调", "业绩预告", "客户验证", "客户认证", "交期", "良率", "AI服务器", "AI算力", "高多层板", "HDI", "IC载板", "覆铜板", "铜箔", "玻纤布", "高频高速", "低损耗材料", "需求增长"]
LOW_VALUE_MARKET_DISCLOSURE_TERMS = ["股价异动", "股票交易异常", "交易异常", "异常波动", "问询函", "审核问询", "再融资", "向特定对象发行", "权益变动", "减持", "股份质押", "现金管理", "理财产品", "股权激励", "员工持股", "H股上市", "挂牌上市"]


def prefilter_results(task: ResearchTask, results: list[SearchResult], profile: SectorProfile, limit: int) -> list[SearchResult]:
    scored: list[tuple[tuple[int, float], SearchResult]] = []
    for result in results:
        title = clean_text(result.title)[:160]
        summary = clean_text(result.summary or result.raw_content[:220])[:300]
        if not title or not result.url:
            continue
        if not within_date_window(result.published_at, task.date, task.date_window):
            continue
        primary_text = f"{title} {summary}"
        related_companies = match_companies(profile, primary_text, result.raw_content[:500])
        matched_keywords = match_keywords(profile, primary_text)
        if not matched_keywords and is_sector_relevant(task, profile, primary_text):
            matched_keywords = ["板块相关"]
        relevance_reason = relevance_reject_reason(profile, primary_text, matched_keywords, related_companies)
        tier, source_name = source_tier(result.source_name, result.url)
        if relevance_reason and tier not in {"S", "A"}:
            continue
        if noise_reason_for(profile, title, summary, result.url, result.raw_content):
            continue
        tier_score = {"S": 70, "A": 55, "B": 35, "C": 10}.get(tier, 0)
        company_score = 30 if related_companies else 0
        keyword_score = len(matched_keywords) * 8
        source_score = 12 if source_name in {"财联社", "证券时报", "巨潮资讯", "第一财经", "东方财富", "中国证券报", "上海证券报"} else 0
        industry_score = industry_signal_score(primary_text)
        low_value_penalty = low_value_market_disclosure_penalty(primary_text)
        scored.append(((tier_score + company_score + keyword_score + source_score + industry_score - low_value_penalty, result.score), result))
    selected = [result for _, result in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]
    return selected or results[:limit]


def normalize_candidates(task: ResearchTask, results: list[SearchResult], pages: list[dict], profile: SectorProfile) -> tuple[list[Candidate], list[dict]]:
    text_by_url = {page["url"]: page.get("text", "") for page in pages}
    candidates: list[Candidate] = []
    noise_items: list[dict] = []

    for result in results:
        text = text_by_url.get(result.url) or result.raw_content or result.summary
        title = clean_text(result.title)[:160]
        summary = clean_text(result.summary or text[:220])[:300]
        if not title or not result.url:
            continue
        if not within_date_window(result.published_at, task.date, task.date_window):
            noise_items.append({"item": {"title": title, "url": result.url}, "reason": "发布时间超出任务时间窗口"})
            continue
        noise_reason = noise_reason_for(profile, title, summary, result.url, text)
        primary_text = f"{title} {summary}"
        matched_sector = match_sector(task, primary_text, text)
        matched_keywords = match_keywords(profile, primary_text)
        related_companies = match_companies(profile, primary_text, text[:1200])
        if related_companies and not matched_keywords:
            matched_keywords = ["公司映射"]
        if not matched_keywords and is_sector_relevant(task, profile, primary_text):
            matched_keywords = ["板块相关"]
        relevance_reason = relevance_reject_reason(profile, primary_text, matched_keywords, related_companies)
        if noise_reason or relevance_reason:
            noise_items.append({"item": {"title": title, "url": result.url}, "reason": noise_reason or relevance_reason})
            continue
        tier, source_name = source_tier(result.source_name, result.url)
        excerpt = clean_text(text)[:500]
        if len(excerpt) < 80:
            tier = downgrade(tier)
        candidates.append(Candidate(
            title=title,
            summary=summary or title,
            source_name=source_name or result.source_name,
            source_tier=tier,
            url=result.url,
            collection_mode="automatic_search",
            matched_sector=matched_sector,
            matched_keywords=matched_keywords,
            published_at=result.published_at,
            is_primary_source=tier == "S",
            related_companies=related_companies,
            raw_text_excerpt=excerpt,
            provider=result.provider,
        ))

    return sorted(candidates, key=rank_sort_key)[: task.max_candidates], noise_items


def dedupe_candidates(candidates: list[Candidate], noise_items: list[dict]) -> dict:
    seen_urls: set[str] = set()
    seen_titles: dict[str, Candidate] = {}
    kept = []
    removed = []

    for candidate in sorted(candidates, key=rank_sort_key):
        url_key = canonical_url(candidate.url)
        title_key = title_fingerprint(candidate.title)
        if url_key in seen_urls:
            removed.append({"item": candidate.to_schema_item(), "reason": "URL 重复"})
            continue
        if title_key in seen_titles:
            previous = seen_titles[title_key]
            previous_item = previous.to_schema_item()
            previous_item.setdefault("merged_sources", []).append({"name": candidate.source_name, "url": candidate.url, "source_tier": candidate.source_tier})
            removed.append({"item": candidate.to_schema_item(), "reason": "标题相似，合并到更高优先级来源"})
            continue
        seen_urls.add(url_key)
        seen_titles[title_key] = candidate
        item = candidate.to_schema_item()
        item.update({
            "dedup_status": "kept",
            "dedup_reason": "按 URL 和标题指纹保留，来源优先级和正文完整度通过",
            "merged_sources": [],
            "verified": candidate.source_tier in {"S", "A"},
            "credibility_adjustment": "none" if candidate.source_tier in {"S", "A", "B"} else "down",
        })
        kept.append(item)
    return {"kept_items": kept, "removed_items": removed, "noise_items": noise_items}


def source_counts(candidates: list[Candidate]) -> list[dict]:
    counter = Counter((item.source_name, item.source_tier) for item in candidates)
    return [{"name": name, "tier": tier, "count": count} for (name, tier), count in counter.most_common()]


def industry_signal_score(text: str) -> int:
    return min(sum(1 for term in INDUSTRY_SIGNAL_TERMS if term.lower() in text.lower()) * 10, 60)


def low_value_market_disclosure_penalty(text: str) -> int:
    return min(sum(1 for term in LOW_VALUE_MARKET_DISCLOSURE_TERMS if term.lower() in text.lower()) * 35, 90)


def within_date_window(published_at: str, task_date: str, date_window: str) -> bool:
    published = parse_datetime(published_at)
    if not published:
        return True
    end = parse_datetime(task_date) or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    window_delta = extract_window_delta(date_window)
    start = end - window_delta
    return start <= published <= end + timedelta(hours=1)


def parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_window_delta(date_window: str) -> timedelta:
    text = date_window or ""
    match = re.search(r"(\d+)", text)
    if not match:
        return timedelta(hours=24)
    value = max(int(match.group(1)), 1)
    lowered = text.lower()
    if "hour" in lowered or "小时" in text:
        return timedelta(hours=value)
    if "day" in lowered or "日" in text or "天" in text:
        return timedelta(days=value)
    return timedelta(hours=24)


def source_tier(source_name: str, url: str) -> tuple[str, str]:
    haystack = f"{source_name} {url}".lower()
    for hint, tier, name in TIER_HINTS:
        if hint.lower() in haystack:
            return tier, name
    if any(item in haystack for item in ["pdf", "report", "research"]):
        return "B", source_name
    return "B", source_name


def downgrade(tier: str) -> str:
    order = ["S", "A", "B", "C", "X"]
    index = min(order.index(tier) + 1, len(order) - 1) if tier in order else 2
    return order[index]


def noise_reason_for(profile: SectorProfile, title: str, summary: str, url: str, text: str) -> str:
    haystack = f"{title} {summary} {url}".lower()
    exclude_terms = NOISE_HINTS + profile.exclude_terms
    if any(hint.lower() in haystack for hint in exclude_terms):
        return "命中低质量或板块排除词提示"
    if "from=guba" in haystack or "gubaurl" in haystack:
        return "股吧或财富号分发链接，阶段1默认降噪"
    if any(hint.lower() in haystack for hint in PDF_HINTS) and "cninfo.com.cn" not in haystack:
        return "PDF或研报类材料，阶段1默认降噪不入主线"
    if is_news_digest(title):
        return "早报或合集类内容，主题不够聚焦"
    if is_extraction_boilerplate(text):
        return "正文抽取疑似站点版权页或导航页"
    if len(clean_text(text or summary)) < 40:
        return "正文过短，无法核验"
    return ""


def relevance_reject_reason(profile: SectorProfile, primary_text: str, matched_keywords: list[str], related_companies: list[str]) -> str:
    if not (matched_keywords or related_companies):
        return "未匹配任务关键词、行业画像或公司映射"
    if related_companies:
        return ""
    strong_terms = [keyword for keyword in matched_keywords if keyword not in WEAK_EVENT_TERMS]
    if not strong_terms:
        return "仅匹配订单/价格/产能等弱事件词，缺少板块主题"
    if not any(term.lower() in primary_text.lower() for term in core_sector_terms(profile)):
        return "缺少核心板块主题词"
    return ""


def core_sector_terms(profile: SectorProfile) -> list[str]:
    return profile.aliases + profile.keywords + profile.supply_chain_nodes + company_alias_terms(profile) + GENERIC_CORE_SECTOR_TERMS


def is_news_digest(title: str) -> bool:
    digest_terms = ["早报", "午报", "晚报", "盘中宝", "公告精选", "电报", "要闻", "一周", "汇总"]
    return any(term in title for term in digest_terms)


def is_extraction_boilerplate(text: str) -> bool:
    cleaned = clean_text(text)
    boilerplate_terms = ["未经本报书面授权", "联系我们 电话", "互联网新闻信息服务许可证"]
    return len(cleaned) < 900 and sum(1 for term in boilerplate_terms if term in cleaned) >= 2


def match_sector(task: ResearchTask, *texts: str) -> str:
    haystack = " ".join(texts)
    for sector in task.sectors:
        if sector in haystack:
            return sector
    return task.sectors[0]


def match_keywords(profile: SectorProfile, *texts: str) -> list[str]:
    haystack = " ".join(texts)
    haystack_lower = haystack.lower()
    terms = profile.keywords + profile.supply_chain_nodes + profile.event_types + profile.aliases + company_alias_terms(profile)
    matched = [term for term in terms if term and term.lower() in haystack_lower]
    return matched[:8]


def match_companies(profile: SectorProfile, *texts: str) -> list[str]:
    haystack = " ".join(texts)
    haystack_lower = haystack.lower()
    companies: list[str] = []
    for company in profile.companies:
        company_name = str(company).strip()
        aliases = profile.company_aliases.get(company_name, [])
        alias_hit = any(alias.lower() in haystack_lower for alias in aliases)
        if company_name and (company_name in haystack or alias_hit) and company_name not in companies:
            companies.append(company_name)
    return companies[:8]


def is_sector_relevant(task: ResearchTask, profile: SectorProfile, *texts: str) -> bool:
    haystack = " ".join(texts).lower()
    sector_hit = any(sector.lower() in haystack for sector in task.sectors + profile.aliases)
    keyword_hit = any(keyword.lower() in haystack for keyword in profile.keywords + profile.supply_chain_nodes + company_alias_terms(profile))
    market_hit = any(keyword.lower() in haystack for keyword in MARKET_SIGNAL_TERMS)
    return sector_hit or (keyword_hit and market_hit)


def company_alias_terms(profile: SectorProfile) -> list[str]:
    terms: list[str] = []
    for company, aliases in profile.company_aliases.items():
        if company:
            terms.append(company)
        terms.extend(alias for alias in aliases if alias)
    return terms


def rank_sort_key(candidate: Candidate) -> tuple[int, int, int, int, int]:
    tier_score = {"S": 0, "A": 1, "B": 2, "C": 3, "X": 4}.get(candidate.source_tier, 3)
    company_score = 0 if candidate.related_companies else 1
    china_score = 0 if has_china_market_signal(candidate) else 1
    keyword_score = -len(candidate.matched_keywords)
    return tier_score, company_score, china_score, keyword_score, -len(candidate.raw_text_excerpt)


def has_china_market_signal(candidate: Candidate) -> bool:
    text = f"{candidate.title} {candidate.summary} {candidate.source_name} {candidate.url} {candidate.raw_text_excerpt}".lower()
    signals = ["a股", "上市公司", "公告", "财联社", "证券时报", "东方财富", "巨潮", "互动易", "中国", "深圳", "上海"]
    return any(signal.lower() in text for signal in signals)


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc.lower()}{parsed.path}".rstrip("/")


def title_fingerprint(title: str) -> str:
    cleaned = re.sub(r"[\W_]+", "", title.lower())
    return cleaned[:40]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
