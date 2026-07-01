import json
from copy import deepcopy
from typing import Any


class MockSenseAudioClient:
    def __init__(self) -> None:
        self.context: dict[str, Any] = {}

    async def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        schema_title, context = self._detect_request(messages)
        if context:
            self.context = context
        stage_map = {
            "Securities Daily Workflow Plan": self._workflow_plan,
            "Securities Source Candidates": self._candidates,
            "Securities Deduped News": self._deduped_news,
            "Securities Rated Signals": self._rated_signals,
            "Securities Trends": self._trends,
            "Securities Daily Report": self._report,
        }
        factory = stage_map.get(schema_title, self._report)
        return factory()

    def _detect_request(self, messages: list[dict]) -> tuple[str, dict[str, Any]]:
        for msg in messages:
            if msg.get("role") != "user":
                continue
            try:
                payload = json.loads(msg["content"])
            except (json.JSONDecodeError, TypeError):
                continue
            runtime_context = payload.get("runtime_context") or {}
            if "output_schema" in payload and isinstance(payload["output_schema"], dict):
                return payload["output_schema"].get("title", ""), runtime_context
            if "report_schema" in payload and isinstance(payload["report_schema"], dict):
                return payload["report_schema"].get("title", ""), runtime_context
            if "stage" in payload and "schema" in payload:
                stage_to_title = {
                    "workflow_plan": "Securities Daily Workflow Plan",
                    "source_research": "Securities Source Candidates",
                    "news_dedup": "Securities Deduped News",
                    "priority_rating": "Securities Rated Signals",
                    "trend_analysis": "Securities Trends",
                    "report_format": "Securities Daily Report",
                }
                return stage_to_title.get(payload["stage"], ""), self.context
        return "", self.context

    async def test_connection(self) -> bool:
        return True

    def _request(self) -> dict[str, Any]:
        return self.context.get("request", {}) if isinstance(self.context, dict) else {}

    def _sector_configs(self) -> list[dict[str, Any]]:
        configs = self.context.get("sector_configs", []) if isinstance(self.context, dict) else []
        return configs if isinstance(configs, list) else []

    def _sector(self) -> str:
        request = self._request()
        sectors = request.get("sectors") or []
        if sectors:
            return str(sectors[0])
        configs = self._sector_configs()
        if configs:
            return str(configs[0].get("name") or "存储芯片")
        return "存储芯片"

    def _date(self) -> str:
        return str(self._request().get("date") or self.context.get("date") or "2026-06-27")

    def _user_id(self) -> str:
        return str(self.context.get("user_id") or "1")

    def _run_id(self) -> str:
        return str(self.context.get("run_id") or "mock-run")

    def _keywords(self) -> list[str]:
        sector = self._sector()
        for config in self._sector_configs():
            if config.get("name") == sector:
                keywords = config.get("keywords") or []
                if keywords:
                    return [str(item) for item in keywords[:5]]
        return [sector, "产业链", "订单", "价格", "需求"]

    def _companies(self) -> list[str]:
        sector = self._sector()
        for config in self._sector_configs():
            if config.get("name") == sector:
                companies = config.get("related_companies") or []
                if companies:
                    return [str(item) for item in companies[:4]]
        return ["示例公司"]

    def _signal_title(self) -> str:
        return f"{self._sector()}出现需求改善观察信号"

    def _chain_nodes(self) -> list[str]:
        sector = self._sector()
        for config in self._sector_configs():
            if config.get("name") == sector:
                nodes = config.get("chain_nodes") or []
                if nodes:
                    return [str(item) for item in nodes[:4]]
        return ["需求端", sector, "产业链公司", "业绩验证"]

    def _workflow_plan(self) -> dict:
        sector = self._sector()
        return {
            "run_id": self._run_id(),
            "user_id": self._user_id(),
            "date": self._date(),
            "date_window": "本地 mock 覆盖窗口",
            "start_stage": "source_research",
            "enabled_sectors": [sector],
            "collection_modes": self._request().get("collection_modes") or ["manual_links"],
            "required_artifacts": ["workflow_plan.json", "candidates.json", "deduped_news.json", "rated_signals.json", "trends.json", "report.json", "report.html", "run_meta.json"],
            "quality_gates": ["schema_valid", "source_urls_present", "no_investment_advice", "p0_sparse_checked"],
            "notes": ["mock workflow plan"]
        }

    def _candidate_item(self) -> dict:
        sector = self._sector()
        title = self._signal_title()
        keywords = self._keywords()
        return {
            "title": title,
            "summary": f"{sector}出现需求、订单或价格维度的观察信号，仍需更多公开信息验证。",
            "published_at": f"{self._date()}T15:00:00+08:00",
            "source_name": "示例财经源",
            "source_tier": "A",
            "url": f"https://example.com/news/{sector}-mock-signal",
            "collection_mode": "manual_links",
            "matched_sector": sector,
            "matched_keywords": keywords,
            "is_primary_source": False,
            "related_companies": self._companies(),
            "is_follow_up": False,
            "follow_up_item": "",
            "follow_up_update": "",
            "access_issue": "",
            "raw_text_excerpt": "示例正文摘录"
        }

    def _candidates(self) -> dict:
        return {
            "run_id": self._run_id(),
            "user_id": self._user_id(),
            "date": self._date(),
            "date_window": "本地 mock 覆盖窗口",
            "sectors": [self._sector()],
            "candidates": [self._candidate_item()],
            "source_counts": [{"name": "示例财经源", "tier": "A", "count": 1}]
        }

    def _deduped_news(self) -> dict:
        item = deepcopy(self._candidate_item())
        item.update({
            "dedup_status": "kept",
            "dedup_reason": "示例新闻保留用于端到端测试",
            "merged_sources": [],
            "verified": False,
            "credibility_adjustment": "none",
            "cross_sector_relevance": []
        })
        item.pop("collection_mode", None)
        item.pop("is_primary_source", None)
        item.pop("raw_text_excerpt", None)
        return {
            "run_id": self._run_id(),
            "user_id": self._user_id(),
            "date": self._date(),
            "date_window": "本地 mock 覆盖窗口",
            "kept_items": [item],
            "removed_items": [],
            "noise_items": []
        }

    def _rated_signals(self) -> dict:
        sector = self._sector()
        title = self._signal_title()
        chain = self._chain_nodes()
        return {
            "run_id": self._run_id(),
            "user_id": self._user_id(),
            "date": self._date(),
            "signals": [{
                "rank": "P1",
                "sentiment": "利好",
                "title": title,
                "summary": f"{sector}出现产业链观察信号，当前强度适合列入跟踪清单。",
                "sector": sector,
                "related_companies": self._companies(),
                "score": {"sector_impact": 4, "supply_chain_relevance": 5, "credibility": 4, "timeliness": 5, "trend_value": 4, "total": 22},
                "fact": f"示例财经源报道，{sector}相关需求、订单或价格变量出现积极变化。",
                "judgement": "该信息属于中期产业链信号，仍需公告、订单或价格数据验证。",
                "why_it_matters": f"该变量可能影响{sector}板块预期和产业链传导节奏。",
                "impact_chain": [],
                "trend_direction": {},
                "impact_trend_explanation": "",
                "p0_score_explanation": "",
                "watch_signal_view": {
                    "signal_type": "中期产业链观察信号",
                    "impact_direction": chain,
                    "current_strength": "产业链逻辑清晰，但仍处于公开信息积累阶段，暂定 P1。",
                    "upgrade_condition": "若后续出现公司公告、多来源共振或关键价格/订单数据确认，可进入 P0 候选。",
                    "judgement_explanation": "当前强在方向和产业链传导，仍需进一步公开来源验证。"
                },
                "follow_up": "跟踪公告、订单、价格、库存或业绩预告等验证指标。",
                "sources": [{"name": "示例财经源", "url": f"https://example.com/news/{sector}-mock-signal", "source_tier": "A"}],
                "verified": False,
                "uncertainty_note": "示例数据仅用于端到端测试。",
                "noise_reason": ""
            }],
            "noise_items": []
        }

    def _trends(self) -> dict:
        sector = self._sector()
        title = self._signal_title()
        return {
            "run_id": self._run_id(),
            "user_id": self._user_id(),
            "date": self._date(),
            "trends": {
                "by_sector": {
                    sector: {
                        "direction": "待验证",
                        "summary": f"{sector}出现观察信号，趋势判断仍需后续公开来源和关键指标确认。",
                        "positive_changes": ["需求或订单变量出现积极变化"],
                        "negative_changes_or_risks": ["公开信息仍在积累"],
                        "change_vs_previous": "无历史可比",
                        "new_variables": self._keywords()[:3],
                        "verification_metrics": ["公告", "订单", "价格", "库存"],
                        "key_signals": [title],
                        "cross_sector_links": []
                    }
                },
                "resonance_points": [],
                "divergence_points": []
            },
            "tracking_items": [{
                "sector": sector,
                "item": f"{sector}观察信号是否获得公开来源验证",
                "priority": "中",
                "reason": "决定 P1 信号是否具备升级条件。",
                "status": "new",
                "verification_metrics": ["公告", "订单", "价格", "业绩预告"],
                "related_signal_titles": [title]
            }]
        }

    def _report(self) -> dict:
        sector = self._sector()
        date = self._date()
        return {
            "run_id": self._run_id(),
            "user_id": self._user_id(),
            "date": date,
            "title": f"证券产业新闻情报日报｜{date}｜{sector}",
            "coverage": "本地 mock 覆盖窗口",
            "sectors": [sector],
            "conclusions": [f"{sector}出现 P1 级观察信号，后续重点看公开来源验证。"],
            "summary": "本报告用于本地端到端测试，展示完整日报阅读与问答流程。",
            "signals": self._rated_signals()["signals"],
            "noise_items": [],
            "trends": self._trends()["trends"],
            "tracking_items": self._trends()["tracking_items"],
            "source_counts": [{"name": "示例财经源", "tier": "A", "count": 1}],
            "disclaimer": "本日报仅基于公开信息整理，不构成任何投资建议。"
        }
