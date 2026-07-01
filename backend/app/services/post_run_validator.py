from dataclasses import dataclass
from urllib.parse import urlparse

INVESTMENT_ADVICE_KEYWORDS = [
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "满仓",
    "清仓",
    "目标价",
    "止盈",
    "止损",
    "收益保证",
    "稳赚",
]

COMMUNITY_SOURCE_HINTS = ["雪球", "股吧", "论坛", "社区", "贴吧", "自媒体"]


@dataclass
class BusinessValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


class PostRunValidator:
    def validate_report(self, report: dict, user_id: str | int, max_p0_per_sector: int = 5) -> BusinessValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        signals = report.get("signals", [])

        errors.extend(self._validate_no_investment_advice(report))
        errors.extend(self._validate_sources(signals))
        errors.extend(self._validate_p0(signals, max_p0_per_sector))
        errors.extend(self._validate_p1(signals))
        errors.extend(self._validate_user_scope(report, user_id))

        return BusinessValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def _validate_no_investment_advice(self, report: dict) -> list[str]:
        text = str(report)
        return [f"包含疑似投资建议关键词：{word}" for word in INVESTMENT_ADVICE_KEYWORDS if word in text]

    def _validate_sources(self, signals: list[dict]) -> list[str]:
        errors: list[str] = []
        for index, signal in enumerate(signals):
            if signal.get("rank") == "Noise":
                continue
            sources = signal.get("sources") or []
            if not sources:
                errors.append(f"signals[{index}] 缺少 sources")
                continue
            for source_index, source in enumerate(sources):
                url = source.get("url", "")
                if not url:
                    errors.append(f"signals[{index}].sources[{source_index}] 缺少 url")
                    continue
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"}:
                    errors.append(f"signals[{index}].sources[{source_index}] URL 协议不允许：{url}")
        return errors

    def _validate_p0(self, signals: list[dict], max_p0_per_sector: int) -> list[str]:
        errors: list[str] = []
        p0_by_sector: dict[str, int] = {}
        for index, signal in enumerate(signals):
            if signal.get("rank") != "P0":
                continue
            sector = signal.get("sector", "unknown")
            p0_by_sector[sector] = p0_by_sector.get(sector, 0) + 1
            required = ["fact", "impact_chain", "trend_direction", "impact_trend_explanation", "p0_score_explanation", "follow_up", "sources"]
            for field in required:
                if not signal.get(field):
                    errors.append(f"P0 signals[{index}] 缺少 {field}")
            if len(signal.get("impact_chain") or []) < 3:
                errors.append(f"P0 signals[{index}] impact_chain 少于 3 个节点")
            trend = signal.get("trend_direction") or {}
            for field in ["short_term", "mid_term", "verification"]:
                if not trend.get(field):
                    errors.append(f"P0 signals[{index}] trend_direction 缺少 {field}")
            sources = signal.get("sources") or []
            if sources and all(any(hint in source.get("name", "") for hint in COMMUNITY_SOURCE_HINTS) for source in sources):
                errors.append(f"P0 signals[{index}] 仅由社区/自媒体来源支撑")
        for sector, count in p0_by_sector.items():
            if count > max_p0_per_sector:
                errors.append(f"板块 {sector} P0 数量 {count} 超过上限 {max_p0_per_sector}")
        return errors

    def _validate_p1(self, signals: list[dict]) -> list[str]:
        errors: list[str] = []
        for index, signal in enumerate(signals):
            if signal.get("rank") != "P1":
                continue
            view = signal.get("watch_signal_view") or {}
            for field in ["signal_type", "impact_direction", "current_strength", "upgrade_condition", "judgement_explanation"]:
                if not view.get(field):
                    errors.append(f"P1 signals[{index}] watch_signal_view 缺少 {field}")
            if len(view.get("impact_direction") or []) < 2:
                errors.append(f"P1 signals[{index}] impact_direction 少于 2 个节点")
        return errors

    def _validate_user_scope(self, report: dict, user_id: str | int) -> list[str]:
        expected = str(user_id)
        actual = str(report.get("user_id", ""))
        if actual and actual != expected:
            return [f"report.user_id={actual} 与当前用户 {expected} 不一致"]
        return []
