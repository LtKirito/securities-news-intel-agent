from __future__ import annotations

from collections import Counter
from typing import Any

SA_TIERS = {"S", "A"}
P0_EVENT_TERMS = ["订单", "量产", "定点", "扩产", "涨价", "降价", "业绩", "中标", "客户", "产能", "公告"]
CHINA_SIGNALS = ["A股", "上市公司", "公告", "巨潮", "互动易", "上证e互动", "财联社", "证券时报", "东方财富", "中国", "深圳", "上海"]
ENGLISH_MARKERS = ["robotics", "humanoid", "automation", "wall street", "spac", "nasdaq", "cnbc", "wsj"]


def candidate_quality(item: dict[str, Any]) -> dict[str, Any]:
    text = _joined(item)
    source_tier = item.get("source_tier", "B")
    related_companies = item.get("related_companies", []) or []
    matched_keywords = item.get("matched_keywords", []) or []
    has_event = any(term in text for term in P0_EVENT_TERMS)
    has_china_signal = any(term.lower() in text.lower() for term in CHINA_SIGNALS)
    has_company = bool(related_companies)
    source_score = {"S": 40, "A": 32, "B": 22, "C": 10, "X": 0}.get(source_tier, 15)
    score = source_score + min(len(matched_keywords), 5) * 4
    if has_company:
        score += 16
    if has_event:
        score += 12
    if has_china_signal:
        score += 10
    if len(item.get("raw_text_excerpt", "")) >= 300:
        score += 6
    if source_tier in {"C", "X"}:
        score -= 20
    score = max(0, min(score, 100))
    gates = []
    if source_tier not in SA_TIERS:
        gates.append("非S/A来源，不能单独支撑P0")
    if not has_company:
        gates.append("未命中板块公司，默认不支撑P0")
    if not has_event:
        gates.append("未命中订单/量产/公告等强事件，默认不支撑P0")
    if not has_china_signal:
        gates.append("缺少中国A股/公告/主流财经信号")
    return {
        "score": score,
        "grade": "high" if score >= 72 else "medium" if score >= 50 else "low",
        "has_company": has_company,
        "has_event": has_event,
        "has_china_signal": has_china_signal,
        "p0_eligible": source_tier in SA_TIERS and has_company and has_event and has_china_signal,
        "p0_gate_notes": gates,
    }


def build_quality_report(
    candidates_payload: dict[str, Any],
    deduped_payload: dict[str, Any],
    rated_signals: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = candidates_payload.get("candidates", [])
    kept = deduped_payload.get("kept_items", [])
    signals = (report or {}).get("signals", []) or (rated_signals or {}).get("signals", []) or []
    tier_counts = Counter(item.get("source_tier", "B") for item in kept)
    source_counts = Counter(item.get("source_name", "未知来源") for item in kept)
    company_hits = sum(1 for item in kept if item.get("related_companies"))
    p0_eligible = sum(1 for item in kept if item.get("quality", {}).get("p0_eligible"))
    english_or_overseas = sum(1 for item in kept if _looks_english_or_overseas(item))
    rank_counts = Counter(item.get("rank", "unknown") for item in signals)
    total_kept = len(kept)
    sa_sources = tier_counts.get("S", 0) + tier_counts.get("A", 0)
    ratios = {
        "sa_source_ratio": _ratio(sa_sources, total_kept),
        "company_hit_ratio": _ratio(company_hits, total_kept),
        "p0_eligible_ratio": _ratio(p0_eligible, total_kept),
        "english_or_overseas_ratio": _ratio(english_or_overseas, total_kept),
    }
    gate = build_quality_gate(total_kept, ratios)
    profile = deduped_payload.get("sector_profile", {}) or {}
    generation_mode = build_generation_mode(total_kept, gate, profile)
    warnings = quality_warnings(total_kept, ratios, gate, profile)
    fixes = suggested_fixes(gate, profile)
    return {
        "summary": {
            "raw_candidates": len(candidates),
            "kept_items": total_kept,
            "sa_source_items": sa_sources,
            "company_hit_items": company_hits,
            "p0_eligible_items": p0_eligible,
            "english_or_overseas_items": english_or_overseas,
            "signals": len(signals),
            "p0_signals": rank_counts.get("P0", 0),
            "p1_signals": rank_counts.get("P1", 0),
            "p2_signals": rank_counts.get("P2", 0),
        },
        "ratios": ratios,
        "quality_gate": gate,
        "generation_mode": generation_mode,
        "quality_warnings": warnings,
        "suggested_fixes": fixes,
        "source_tier_counts": dict(tier_counts),
        "top_sources": [{"name": name, "count": count} for name, count in source_counts.most_common(10)],
        "rank_counts": dict(rank_counts),
        "quality_notes": _quality_notes(total_kept, tier_counts, company_hits, p0_eligible, english_or_overseas),
    }


def build_generation_mode(total_kept: int, gate: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    if gate.get("passed"):
        mode = "high_confidence_report"
        label = "正式日报"
        allow_llm = True
    elif total_kept > 0:
        mode = "limited_confidence_report"
        label = "观察版日报"
        allow_llm = True
    else:
        mode = "watchlist_report"
        label = "持续跟踪日报"
        allow_llm = True
    return {
        "mode": mode,
        "label": label,
        "allow_llm": allow_llm,
        "profile_status": profile.get("profile_status", "curated"),
        "must_disclose_limitations": mode != "high_confidence_report" or profile.get("profile_status") == "temporary",
    }


def quality_warnings(total_kept: int, ratios: dict[str, float], gate: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    warnings = [item.get("reason", "") for item in gate.get("failures", []) if item.get("reason")]
    warnings.extend(profile.get("profile_warnings", []) or [])
    if profile.get("profile_status") == "temporary":
        warnings.append("该板块使用临时画像，缺少稳定公司池和产业链节点校验。")
    if total_kept == 0:
        warnings.append("本次未获得有效候选，日报只能作为持续跟踪清单。")
    if ratios.get("company_hit_ratio", 0) < 0.5:
        warnings.append("该板块缺少上市公司画像，请补充 5-15 家代表公司。")
    if ratios.get("sa_source_ratio", 0) < 0.6:
        warnings.append("高可信来源比例不足，应优先补充公告、互动平台和主流证券媒体来源。")
    return dedupe_text(warnings)


def suggested_fixes(gate: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    fixes = []
    metrics = {item.get("metric") for item in gate.get("failures", [])}
    if profile.get("profile_status") == "temporary" or "company_hit_ratio" in metrics:
        fixes.append("补充 5-15 家代表上市公司，并保存为板块画像。")
    if "kept_items" in metrics:
        fixes.append("自动扩大第一层固定源入口：巨潮、互动易、上证e互动、财联社、证券时报、东方财富、第一财经、21财经。")
    if "sa_source_ratio" in metrics:
        fixes.append("优先补充 S/A 来源，不要优先消耗 GNews/Tavily。")
    if "english_or_overseas_ratio" in metrics:
        fixes.append("降低海外/英文来源权重，增强中文证券源和公告源。")
    fixes.extend([
        "如仍不足，可选择只保存采集结果、不生成正式日报。",
        "如业务需要，可放宽本次门槛并生成观察版日报。",
        "必要时再启用 SearXNG、GNews 或 Tavily 兜底。",
    ])
    return dedupe_text(fixes)


def dedupe_text(items: list[str]) -> list[str]:
    result = []
    for item in items:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def build_quality_gate(total_kept: int, ratios: dict[str, float]) -> dict[str, Any]:
    thresholds = {
        "min_kept_items": 5,
        "min_sa_source_ratio": 0.6,
        "min_company_hit_ratio": 0.5,
        "max_english_or_overseas_ratio": 0.35,
    }
    failures = []
    if total_kept < thresholds["min_kept_items"]:
        failures.append({"metric": "kept_items", "actual": total_kept, "threshold": thresholds["min_kept_items"], "reason": "有效候选不足，生成日报会偏空"})
    if ratios["sa_source_ratio"] < thresholds["min_sa_source_ratio"]:
        failures.append({"metric": "sa_source_ratio", "actual": ratios["sa_source_ratio"], "threshold": thresholds["min_sa_source_ratio"], "reason": "S/A来源占比不足，可信度不稳"})
    if ratios["company_hit_ratio"] < thresholds["min_company_hit_ratio"]:
        failures.append({"metric": "company_hit_ratio", "actual": ratios["company_hit_ratio"], "threshold": thresholds["min_company_hit_ratio"], "reason": "公司命中不足，日报容易变成泛行业趋势"})
    if ratios["english_or_overseas_ratio"] > thresholds["max_english_or_overseas_ratio"]:
        failures.append({"metric": "english_or_overseas_ratio", "actual": ratios["english_or_overseas_ratio"], "threshold": thresholds["max_english_or_overseas_ratio"], "reason": "海外/英文来源占比偏高，国内证券视角不足"})
    return {
        "passed": not failures,
        "thresholds": thresholds,
        "failures": failures,
        "action": "allow_llm" if not failures else "allow_limited_confidence_llm",
    }


class QualityGateError(RuntimeError):
    def __init__(self, gate: dict[str, Any]):
        self.gate = gate
        reasons = "; ".join(item["reason"] for item in gate.get("failures", [])) or "quality gate failed"
        super().__init__(f"Quality gate blocked LLM: {reasons}")


def assert_quality_gate(quality_report: dict[str, Any]) -> None:
    gate = quality_report.get("quality_gate", {})
    if not gate.get("passed", False):
        raise QualityGateError(gate)


def attach_candidate_quality(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in items:
        clone = dict(item)
        clone["quality"] = candidate_quality(clone)
        enriched.append(clone)
    return enriched


def _quality_notes(total: int, tier_counts: Counter, company_hits: int, p0_eligible: int, english_or_overseas: int) -> list[str]:
    notes = []
    if total == 0:
        return ["未获得有效候选新闻"]
    if total < 5:
        notes.append("有效候选数量偏少，建议补充搜索源或放宽板块关键词后再生成")
    if tier_counts.get("S", 0) + tier_counts.get("A", 0) < 3:
        notes.append("S/A级来源偏少，需要补充公告和主流证券媒体")
    if company_hits / total < 0.35:
        notes.append("板块公司命中率偏低，日报更偏行业趋势而非证券产业链信号")
    if p0_eligible == 0:
        notes.append("暂无满足P0硬门槛的候选，P0应保持稀缺")
    if english_or_overseas / total > 0.35:
        notes.append("海外/英文来源占比较高，需要继续增强中文财经源")
    return notes or ["候选质量结构正常"]


def _looks_english_or_overseas(item: dict[str, Any]) -> bool:
    text = _joined(item).lower()
    if any(marker in text for marker in ENGLISH_MARKERS):
        return True
    source = str(item.get("source_name", "")).lower()
    return any(domain in source for domain in ["cnbc", "wsj", "robot report", "automationworld", "businessinsider"])


def _joined(item: dict[str, Any]) -> str:
    parts = [
        item.get("title", ""),
        item.get("summary", ""),
        item.get("source_name", ""),
        item.get("url", ""),
        item.get("raw_text_excerpt", ""),
    ]
    return " ".join(str(part) for part in parts)


def _ratio(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0
