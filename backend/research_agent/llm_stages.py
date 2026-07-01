from __future__ import annotations

import json
from typing import Any

from app.core.senseaudio_client import SenseAudioClient
from app.services.agent_loader import AgentLoader
from app.services.post_run_validator import PostRunValidator
from app.services.schema_validator import SchemaValidator

from .models import ResearchTask
from .sector_profile import SectorProfile


class ResearchLLMStages:
    def __init__(self, client: SenseAudioClient):
        self.client = client
        self.loader = AgentLoader()
        self.validator = SchemaValidator(self.loader)
        self.post_validator = PostRunValidator()

    async def rate_signals(self, run_id: str, task: ResearchTask, deduped_news: dict[str, Any], profile: SectorProfile, quality_report: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "pipeline_skill": self.loader.load_pipeline_skill(),
            "stage_skill": self.loader.load_skill("securities-priority-rating"),
            "rating_rules": json.loads(self.loader.load_config("rating_rules.json")),
            "rated_signals_schema": json.loads(self.loader.load_schema("rated_signals.schema.json")),
            "trends_schema": json.loads(self.loader.load_schema("trends.schema.json")),
            "sector_profile": profile.to_dict(),
            "quality_context": quality_report or {},
            "general_p0_p1_rules": {
                "p0_hard_gate": [
                    "候选 item.quality.p0_eligible 必须为 true，才允许评为 P0",
                    "P0 必须有 S/A 来源、板块公司命中、订单/量产/定点/扩产/业绩/价格/公告等强事件、国内证券市场相关信号",
                    "P0 候选优先来自滚动24小时窗口；早于24小时的事件只有在窗口内出现一手公告/权威确认/订单/产能/价格/客户/政策/财报等新增验证才可进入P0候选",
                    "单一B/C/X来源、纯机构预测、融资、展会、新品发布、海外泛行业新闻不得评为 P0"
                ],
                "p1_default": [
                    "未满足P0硬门槛不等于自动降为P2；具备明确产业边际变化但缺少强公告验证时，应评为P1",
                    "机构预测、融资上市、新品发布、展会展示、单源媒体报道、无订单验证的公司表态默认评为 P1",
                    "没有公司映射的行业趋势新闻只能作为 P1/P2 或趋势背景"
                ],
                "pcb_p1_rules": [
                    "PCB板块中，AI服务器PCB、高多层板、HDI、IC载板、覆铜板、铜箔、玻纤布、低损耗材料、高频高速材料等需求或供给变化可构成P1",
                    "订单、扩产、稼动率/产能利用率、涨价/价格上调、交期、良率、客户验证/客户认证、业绩预告、AI服务器需求增长等，若来自S/A/B可识别来源且事实清楚，应至少评为P1",
                    "股价异动、股票交易异常、问询函、再融资、权益变动、减持、现金管理、股权激励等交易或资本运作事项，若未披露订单、价格、产能、客户或业绩变化，应评为P2或Noise"
                ]
            },
            "runtime_context": self._context(run_id, task, {"deduped_news": deduped_news}),
        }
        result = await self.client.chat_json([
            {"role": "system", "content": "你是证券日报评级+趋势阶段执行器。严格依据输入和 schema 输出 JSON。输出必须同时包含 signals、noise_items（按 rated_signals_schema）和 trends、tracking_items（按 trends_schema）四个字段。P0 必须满足 p0_hard_gate，否则降为 P1/P2；但达不到P0不等于P2，具备明确产业边际变化且可跟踪的信号应评为P1。PCB板块中，订单、扩产、稼动率、涨价、AI服务器PCB、高多层板、HDI、覆铜板、铜箔、客户认证、业绩预告等事实清楚时应至少评为P1；股价异动、交易异常、问询函、再融资、权益变动、现金管理、股权激励若没有经营事实，应评为P2或Noise。P2信号必须精简：只保留标题、摘要（1-2句）、后续跟踪，不要展开评分、事实、影响链条。若 quality_context.generation_mode 为观察版或持续跟踪日报，评级必须保守，并在摘要中体现证据不足。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
        validated = await self._validate_or_repair("priority_rating", "rated_signals.schema.json", {"signals": result.get("signals", []), "noise_items": result.get("noise_items", [])}, payload)
        validated["trends"] = result.get("trends", {})
        validated["tracking_items"] = result.get("tracking_items", [])
        return validated

    async def analyze_trends(self, run_id: str, task: ResearchTask, rated_signals: dict[str, Any], quality_report: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "pipeline_skill": self.loader.load_pipeline_skill(),
            "stage_skill": self.loader.load_skill("securities-trend-analysis"),
            "output_schema": json.loads(self.loader.load_schema("trends.schema.json")),
            "quality_context": quality_report or {},
            "runtime_context": self._context(run_id, task, {"rated_signals": rated_signals}),
        }
        result = await self.client.chat_json([
            {"role": "system", "content": "你是证券日报趋势分析阶段执行器。只基于 rated_signals 归纳趋势和跟踪项，只返回 JSON。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
        return await self._validate_or_repair("trend_analysis", "trends.schema.json", result, payload)

    async def format_report(
        self,
        run_id: str,
        task: ResearchTask,
        candidates: dict[str, Any],
        deduped_news: dict[str, Any],
        rated_signals: dict[str, Any],
        trends: dict[str, Any],
        quality_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        signals = self._normalize_report_signals(rated_signals.get("signals", []), task)
        noise_items = rated_signals.get("noise_items", [])[:10]
        source_counts = candidates.get("source_counts", [])
        generation_mode = (quality_report or {}).get("generation_mode", {})
        payload = {
            "quality_context": quality_report or {},
            "sectors": task.sectors,
            "signals": [
                {
                    "rank": item.get("rank"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "related_companies": item.get("related_companies", []),
                    "sources": item.get("sources", []),
                }
                for item in signals[:5]
            ],
            "trends": trends,
        }
        narrative = await self.client.chat_json([
            {"role": "system", "content": "你是证券日报轻摘要生成器。只基于输入生成 JSON：summary 字符串、conclusions 字符串数组 3-5 条。不要新增事实，不要投资建议，语言简洁。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], temperature=0)
        report = {
            "run_id": run_id,
            "user_id": task.user_id,
            "date": task.date,
            "title": "证券产业新闻情报日报" if generation_mode.get("mode") == "high_confidence_report" else "证券产业新闻情报日报（持续跟踪观察版）",
            "coverage": task.date_window,
            "sectors": task.sectors,
            "conclusions": self._safe_string_list(narrative.get("conclusions"), self._fallback_conclusions(signals, generation_mode)),
            "summary": str(narrative.get("summary") or self._fallback_summary(signals, generation_mode)),
            "signals": signals[:5],
            "noise_items": noise_items,
            "trends": self._normalize_trends(trends),
            "tracking_items": trends.get("tracking_items", []),
            "source_counts": source_counts,
            "disclaimer": self._disclaimer(generation_mode),
        }
        report = await self._validate_or_repair("report_format", "report.schema.json", report, payload)
        business = self.post_validator.validate_report(report, task.user_id)
        if not business.valid:
            report = self._local_business_repair(report)
            business = self.post_validator.validate_report(report, task.user_id)
            if not business.valid:
                raise ValueError("report business validation failed: " + "; ".join(business.errors))
        return report

    def _normalize_report_signals(self, signals: list[dict[str, Any]], task: ResearchTask) -> list[dict[str, Any]]:
        normalized = []
        for signal in signals:
            rank = signal.get("rank") if signal.get("rank") in {"P0", "P1", "P2", "Noise"} else "P2"
            sources = signal.get("sources") or []
            if not sources:
                continue
            score = signal.get("score") or {}
            total = int(score.get("total") or 0)
            if not total:
                total = sum(int(score.get(key) or 3) for key in ["sector_impact", "supply_chain_relevance", "credibility", "timeliness", "trend_value"])
            item = {
                "rank": rank,
                "sentiment": signal.get("sentiment") if signal.get("sentiment") in {"利好", "利空", "中性", "不确定"} else "中性",
                "title": str(signal.get("title") or "未命名信号"),
                "summary": str(signal.get("summary") or signal.get("judgement") or signal.get("fact") or "待持续跟踪。"),
                "sector": str(signal.get("sector") or (task.sectors[0] if task.sectors else "未命名板块")),
                "related_companies": signal.get("related_companies") or [],
                "score": {
                    "sector_impact": int(score.get("sector_impact") or 3),
                    "supply_chain_relevance": int(score.get("supply_chain_relevance") or 3),
                    "credibility": int(score.get("credibility") or 3),
                    "timeliness": int(score.get("timeliness") or 3),
                    "trend_value": int(score.get("trend_value") or 3),
                    "total": total,
                },
                "fact": str(signal.get("fact") or signal.get("summary") or "输入未提供更多事实细节。"),
                "judgement": str(signal.get("judgement") or signal.get("summary") or "作为持续跟踪信号处理。"),
                "why_it_matters": str(signal.get("why_it_matters") or "影响后续板块跟踪优先级。"),
                "impact_chain": signal.get("impact_chain") or [],
                "trend_direction": signal.get("trend_direction") or {},
                "impact_trend_explanation": str(signal.get("impact_trend_explanation") or "需结合后续公告、订单和业绩验证。"),
                "p0_score_explanation": str(signal.get("p0_score_explanation") or ""),
                "watch_signal_view": signal.get("watch_signal_view") or {},
                "follow_up": str(signal.get("follow_up") or "持续跟踪后续公告、订单、客户验证和业绩影响。"),
                "sources": sources,
                "verified": bool(signal.get("verified", True)),
                "uncertainty_note": str(signal.get("uncertainty_note") or "仍需后续交叉验证。"),
                "noise_reason": str(signal.get("noise_reason") or ""),
            }
            if rank == "P1":
                item["watch_signal_view"] = self._normalize_watch_view(item)
            if rank == "P0":
                item["impact_chain"] = item["impact_chain"] or ["事件发生", "产业链相关环节受影响", "后续订单/业绩验证"]
                item["trend_direction"] = item["trend_direction"] or {"short_term": "关注事件扩散", "mid_term": "关注兑现节奏", "verification": ["公告", "订单", "业绩"]}
                item["p0_score_explanation"] = item["p0_score_explanation"] or "满足高优先级信号的基础条件。"
            normalized.append(item)
        return normalized

    def _normalize_watch_view(self, signal: dict[str, Any]) -> dict[str, Any]:
        view = signal.get("watch_signal_view") or {}
        directions = view.get("impact_direction") or signal.get("impact_chain") or ["产业趋势", "公司映射"]
        if len(directions) < 2:
            directions = [str(directions[0]) if directions else "产业趋势", "后续验证"]
        return {
            "signal_type": str(view.get("signal_type") or "中期产业链信号"),
            "impact_direction": [str(item) for item in directions[:5]],
            "current_strength": str(view.get("current_strength") or signal.get("summary") or "当前证据具备跟踪价值。"),
            "upgrade_condition": str(view.get("upgrade_condition") or "出现公告、订单、定点、扩产或业绩验证后可上调优先级。"),
            "judgement_explanation": str(view.get("judgement_explanation") or signal.get("judgement") or "证据尚不足以评为 P0。"),
        }

    def _normalize_trends(self, trends: dict[str, Any]) -> dict[str, Any]:
        body = trends.get("trends") if "trends" in trends else trends
        if not isinstance(body, dict):
            body = {}
        return {
            "by_sector": body.get("by_sector") or {},
            "resonance_points": body.get("resonance_points") or [],
            "divergence_points": body.get("divergence_points") or [],
        }

    def _safe_string_list(self, value: Any, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                return items[:5]
        return fallback

    def _fallback_summary(self, signals: list[dict[str, Any]], generation_mode: dict[str, Any]) -> str:
        if not signals:
            return "本期未获得足够高质量信号，建议持续跟踪。"
        top = signals[0]
        prefix = "本期核心信号来自"
        return f"{prefix}{top.get('title', '重点事件')}，整体仍需结合公告、订单和业绩继续验证。"

    def _fallback_conclusions(self, signals: list[dict[str, Any]], generation_mode: dict[str, Any]) -> list[str]:
        if not signals:
            return ["本期有效信号不足。", "建议持续跟踪S/A来源。", "暂不形成高确定性判断。"]
        ranks = [item.get("rank") for item in signals]
        return [
            f"本期共保留 {len(signals)} 条有效信号。",
            "P0关键新闻较少。" if "P0" not in ranks else "存在P0级重点信号。",
            "后续重点验证订单、定点、扩产和业绩影响。",
        ]

    def _disclaimer(self, generation_mode: dict[str, Any]) -> str:
        if generation_mode.get("mode") == "high_confidence_report":
            return "本日报仅用于产业新闻跟踪和研究辅助，不构成任何投资建议。"
        return "本日报为持续跟踪观察版，证据充分性有限，仅用于产业新闻跟踪和研究辅助，不构成任何投资建议。"

    def _local_business_repair(self, report: dict[str, Any]) -> dict[str, Any]:
        text_replacements = {"买入": "关注", "卖出": "回避", "加仓": "提高关注", "减仓": "降低关注", "目标价": "估值观察"}
        payload = json.loads(json.dumps(report, ensure_ascii=False))
        raw = json.dumps(payload, ensure_ascii=False)
        for old, new in text_replacements.items():
            raw = raw.replace(old, new)
        return json.loads(raw)

    def _context(self, run_id: str, task: ResearchTask, artifacts: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "user_id": task.user_id,
            "date": task.date,
            "request": task.to_dict(),
            "sector_configs": task.runtime_sector_config or [{"name": name, "keywords": task.keywords} for name in task.sectors],
            "artifacts": artifacts,
        }

    async def _validate_or_repair(self, stage_name: str, schema_name: str, payload: dict, original_prompt: dict) -> dict:
        validation = self.validator.validate(schema_name, payload)
        if validation.valid:
            return payload
        repair_payload = {
            "stage": stage_name,
            "schema": json.loads(self.loader.load_schema(schema_name)),
            "validation_errors": validation.errors,
            "invalid_payload": payload,
            "original_prompt": original_prompt,
        }
        repaired = await self.client.chat_json([
            {"role": "system", "content": "你是 JSON 修复器。只修复 schema 错误，不新增事实，不解释，只返回 JSON。"},
            {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=False)},
        ], temperature=0)
        validation = self.validator.validate(schema_name, repaired)
        if not validation.valid:
            raise ValueError(f"{stage_name} failed schema validation: {validation.errors}")
        return repaired

    async def _repair_business(self, report: dict, errors: list[str], original_prompt: dict) -> dict:
        payload = {
            "business_errors": errors,
            "report": report,
            "original_prompt": original_prompt,
            "rules": [
                "删除疑似投资建议表达，例如买入、卖出、加仓、目标价等",
                "P0/P1 必填展示字段必须补齐，但不得新增事实",
                "单一社区或自媒体来源不得支撑 P0",
                "保留原始来源 URL",
            ],
        }
        repaired = await self.client.chat_json([
            {"role": "system", "content": "你是证券日报合规修复器。只修复业务校验问题，不新增事实，不解释，只返回 report JSON。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], temperature=0)
        validation = self.validator.validate("report.schema.json", repaired)
        if not validation.valid:
            raise ValueError(f"report failed schema validation after business repair: {validation.errors}")
        return repaired
