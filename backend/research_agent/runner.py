from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pathlib import Path
from typing import Any

from app.core.senseaudio_client import SenseAudioClient

from .credentials import load_user_senseaudio_key
from .extractor import enrich_pages
from .llm_stages import ResearchLLMStages
from .models import ResearchTask, SearchResult

MAX_RESULTS_TO_EXTRACT = 60
MAX_LLM_KEPT_ITEMS = 8
from .processing import dedupe_candidates, industry_signal_score, low_value_market_disclosure_penalty, normalize_candidates, prefilter_results, source_counts
from .providers import GNewsProvider, SearXNGProvider, TavilyProvider
from .quality import attach_candidate_quality, build_quality_report
from .query_expander import build_retry_search_plan
from .query_planner import build_search_plan
from .sector_profile import build_sector_profile
from .source_registry import SourceRegistryProvider
from .storage import create_run_dir, read_json, write_json


def sanitize_error(error: Exception) -> str:
    message = str(error)
    for key in ("apikey", "api_key", "token"):
        message = redact_query_param(message, key)
    return message


def redact_query_param(message: str, param_name: str) -> str:
    parts = message.split("'")
    for index, part in enumerate(parts):
        if not part.startswith(("http://", "https://")):
            continue
        split_url = urlsplit(part)
        query = urlencode([
            (key, "***" if key.lower() == param_name.lower() else value)
            for key, value in parse_qsl(split_url.query, keep_blank_values=True)
        ])
        parts[index] = urlunsplit((split_url.scheme, split_url.netloc, split_url.path, query, split_url.fragment))
    return "'".join(parts)


def attach_report_quality(report: dict[str, Any], quality_report: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(report)
    enriched["generation_mode"] = quality_report.get("generation_mode", {})
    enriched["quality_gate"] = quality_report.get("quality_gate", {})
    enriched["quality_warnings"] = quality_report.get("quality_warnings", [])
    enriched["suggested_fixes"] = quality_report.get("suggested_fixes", [])
    if enriched.get("quality_warnings"):
        prefix = "；".join(enriched["quality_warnings"][:2])
        disclaimer = enriched.get("disclaimer", "")
        enriched["disclaimer"] = f"质量提示：{prefix}。{disclaimer}".strip()
    return enriched


def gnews_queries(queries: list[str]) -> list[str]:
    cleaned = []
    for query in queries:
        terms = []
        for token in query.split():
            if token.startswith("site:"):
                host = token.removeprefix("site:")
                if "cninfo" in host:
                    terms.append("公告")
                elif "eastmoney" in host:
                    terms.append("投资者关系")
                continue
            terms.append(token)
        value = " ".join(terms).strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


class ResearchRunner:
    def __init__(self, tavily_api_key: str = "", gnews_api_key: str = "", senseaudio_api_key: str = "", searxng_url: str | None = None, use_commercial_search: bool = False):
        self.tavily_api_key = tavily_api_key
        self.gnews_api_key = gnews_api_key
        self.searxng_url = os.getenv("SEARXNG_URL", "") if searxng_url is None else searxng_url
        self.use_commercial_search = use_commercial_search
        self.senseaudio_api_key = senseaudio_api_key
        self.senseaudio_api_key_source = "cli" if senseaudio_api_key else ""
        self.search_errors: list[dict[str, Any]] = []

    async def run(self, task_path: Path, run_id: str | None = None, no_llm: bool = False) -> dict[str, Any]:
        task = ResearchTask.from_dict(read_json(task_path))
        return await self.run_task(task, task_path, run_id, no_llm)

    async def run_task(self, task: ResearchTask, task_path: Path | None = None, run_id: str | None = None, no_llm: bool = False) -> dict[str, Any]:
        run_id = run_id or uuid.uuid4().hex
        run_dir = create_run_dir(run_id)
        started_at = time.perf_counter()
        task_path = task_path or run_dir / "task.json"
        self._write_progress(run_dir, run_id, "started", "创建日报生成任务", started_at)
        write_json(run_dir / "task.json", task.to_dict())

        self._write_progress(run_dir, run_id, "sector_profile", "构建板块画像", started_at)
        sector_profile = build_sector_profile(task)
        write_json(run_dir / "sector_profile.json", sector_profile.to_dict())
        self._write_progress(run_dir, run_id, "search_plan", "生成检索计划", started_at, {"sector_profile": str(run_dir / "sector_profile.json")})
        search_plan = build_search_plan(task, sector_profile)
        write_json(run_dir / "search_plan.json", search_plan)

        self._write_progress(run_dir, run_id, "source_registry", "采集固定信息源", started_at, {"search_plan": str(run_dir / "search_plan.json")})
        registry_provider = SourceRegistryProvider()
        registry_results = await registry_provider.search(task, sector_profile, task.max_results_per_query)
        write_json(run_dir / "source_registry_results.json", [result.__dict__ for result in registry_results])
        write_json(run_dir / "source_registry_debug.json", registry_provider.debug_events)
        self._write_progress(run_dir, run_id, "web_search", "执行公开搜索补强", started_at, {"source_registry_results": str(run_dir / "source_registry_results.json")})
        api_results = await self._search_all(search_plan["queries"], task.max_results_per_query)
        raw_results = self._unique_results(registry_results + api_results)
        write_json(run_dir / "search_results_all.json", [result.__dict__ for result in raw_results])
        raw_results = prefilter_results(task, raw_results, sector_profile, MAX_RESULTS_TO_EXTRACT)
        write_json(run_dir / "search_results.json", [result.__dict__ for result in raw_results])
        write_json(run_dir / "search_errors.json", self.search_errors)

        self._write_progress(run_dir, run_id, "prefilter", "按标题摘要和来源初筛候选页面", started_at, {"selected_results": len(raw_results), "max_results": MAX_RESULTS_TO_EXTRACT})
        self._write_progress(run_dir, run_id, "extract_pages", "抽取候选新闻页面正文", started_at, {"raw_results": len(raw_results)})
        extracted_pages = await enrich_pages(raw_results)
        write_json(run_dir / "extracted_pages.json", extracted_pages)

        self._write_progress(run_dir, run_id, "normalize_candidates", "标准化候选新闻", started_at, {"extracted_pages": len(extracted_pages)})
        candidates, noise_items = normalize_candidates(task, raw_results, extracted_pages, sector_profile)
        candidates_payload = {
            "run_id": run_id,
            "user_id": task.user_id,
            "date": task.date,
            "date_window": task.date_window,
            "sectors": task.sectors,
            "candidates": [item.to_schema_item() for item in candidates],
            "source_counts": source_counts(candidates),
        }
        write_json(run_dir / "candidates.json", candidates_payload)

        self._write_progress(run_dir, run_id, "dedupe", "去重并保留有效候选", started_at, {"candidates": len(candidates)})
        deduped = dedupe_candidates(candidates, noise_items)
        deduped_payload = {
            "run_id": run_id,
            "user_id": task.user_id,
            "date": task.date,
            "date_window": task.date_window,
            "sector_profile": sector_profile.to_dict(),
            **deduped,
        }
        deduped_payload["kept_items"] = attach_candidate_quality(deduped_payload["kept_items"])
        deduped_payload["kept_items"] = self._limit_kept_items(deduped_payload["kept_items"], MAX_LLM_KEPT_ITEMS)
        write_json(run_dir / "deduped_news.json", deduped_payload)

        self._write_progress(run_dir, run_id, "quality_gate", "执行质量门控", started_at, {"kept_items": len(deduped_payload["kept_items"])})
        quality_report = build_quality_report(candidates_payload, deduped_payload)
        write_json(run_dir / "quality_report.json", quality_report)

        if not quality_report.get("quality_gate", {}).get("passed", False):
            self._write_progress(run_dir, run_id, "retry_plan", "质量不足，生成补充检索计划", started_at)
            retry_plan = build_retry_search_plan(task, sector_profile, quality_report, search_plan["queries"])
            write_json(run_dir / "search_plan_retry.json", retry_plan)
            if retry_plan["queries"]:
                self._write_progress(run_dir, run_id, "retry_search", "执行补充检索", started_at, {"retry_queries": len(retry_plan["queries"])})
                retry_results = await self._search_all(retry_plan["queries"], task.max_results_per_query)
                write_json(run_dir / "search_results_retry.json", [result.__dict__ for result in retry_results])
                write_json(run_dir / "search_errors.json", self.search_errors)
                raw_results = self._unique_results(raw_results + retry_results)
                write_json(run_dir / "search_results_all.json", [result.__dict__ for result in raw_results])
                raw_results = prefilter_results(task, raw_results, sector_profile, MAX_RESULTS_TO_EXTRACT)
                write_json(run_dir / "search_results.json", [result.__dict__ for result in raw_results])
                self._write_progress(run_dir, run_id, "retry_extract_pages", "抽取补充检索候选页面正文", started_at, {"raw_results": len(raw_results)})
                extracted_pages = await enrich_pages(raw_results)
                write_json(run_dir / "extracted_pages.json", extracted_pages)
                candidates, noise_items = normalize_candidates(task, raw_results, extracted_pages, sector_profile)
                candidates_payload = {
                    "run_id": run_id,
                    "user_id": task.user_id,
                    "date": task.date,
                    "date_window": task.date_window,
                    "sectors": task.sectors,
                    "candidates": [item.to_schema_item() for item in candidates],
                    "source_counts": source_counts(candidates),
                }
                write_json(run_dir / "candidates.json", candidates_payload)
                deduped = dedupe_candidates(candidates, noise_items)
                deduped_payload = {
                    "run_id": run_id,
                    "user_id": task.user_id,
                    "date": task.date,
                    "date_window": task.date_window,
                    "sector_profile": sector_profile.to_dict(),
                    **deduped,
                }
                deduped_payload["kept_items"] = attach_candidate_quality(deduped_payload["kept_items"])
                deduped_payload["kept_items"] = self._limit_kept_items(deduped_payload["kept_items"], MAX_LLM_KEPT_ITEMS)
                write_json(run_dir / "deduped_news.json", deduped_payload)
                quality_report = build_quality_report(candidates_payload, deduped_payload)
                quality_report["retry"] = {"attempted": True, "added_queries": len(retry_plan["queries"]), "profile_suggestions": retry_plan.get("profile_suggestions", {})}
                write_json(run_dir / "quality_report.json", quality_report)
                write_json(run_dir / "profile_suggestions.json", retry_plan.get("profile_suggestions", {}))

        if no_llm:
            self._write_progress(run_dir, run_id, "collected", "采集完成，未调用大模型", started_at)
            run_meta = self._build_run_meta(task_path, run_dir, run_id, task, raw_results, extracted_pages, candidates_payload, deduped_payload, quality_report, signals_count=0, status="collected")
            write_json(run_dir / "run_meta.json", run_meta)
            return run_meta

        generation_mode = quality_report.get("generation_mode", {})
        if not generation_mode.get("allow_llm", True):
            self._write_progress(run_dir, run_id, "blocked_by_quality_gate", "质量门控阻断大模型生成", started_at)
            run_meta = self._build_run_meta(task_path, run_dir, run_id, task, raw_results, extracted_pages, candidates_payload, deduped_payload, quality_report, signals_count=0, status="blocked_by_quality_gate")
            write_json(run_dir / "run_meta.json", run_meta)
            return run_meta

        if not self.senseaudio_api_key:
            self.senseaudio_api_key = load_user_senseaudio_key(task.user_id)
            if self.senseaudio_api_key:
                self.senseaudio_api_key_source = "database"
        if not self.senseaudio_api_key:
            self.senseaudio_api_key = os.getenv("SENSEAUDIO_API_KEY", "")
            if self.senseaudio_api_key:
                self.senseaudio_api_key_source = "env"
        if not self.senseaudio_api_key:
            raise ValueError("SenseAudio API key is required: pass --senseaudio-api-key, configure a user API key in the app, or set SENSEAUDIO_API_KEY")
        llm = ResearchLLMStages(SenseAudioClient(self.senseaudio_api_key))
        self._write_progress(run_dir, run_id, "llm_rate_trends", "SenseAudio 信号评级与趋势分析", started_at, {"kept_items": len(deduped_payload["kept_items"])})
        rated_and_trends = await llm.rate_signals(run_id, task, deduped_payload, sector_profile, quality_report)
        rated = {"signals": rated_and_trends.get("signals", []), "noise_items": rated_and_trends.get("noise_items", [])}
        trends = {"trends": rated_and_trends.get("trends", {}), "tracking_items": rated_and_trends.get("tracking_items", [])}
        write_json(run_dir / "rated_signals.json", rated)
        write_json(run_dir / "trends.json", trends)

        self._write_progress(run_dir, run_id, "llm_format_report", "SenseAudio 格式化最终日报", started_at, {"signals": len(rated.get("signals", []))})
        report = await llm.format_report(run_id, task, candidates_payload, deduped_payload, rated, trends, quality_report)
        report = attach_report_quality(report, quality_report)
        write_json(run_dir / "report.json", report)

        quality_report = build_quality_report(candidates_payload, deduped_payload, rated, report)
        write_json(run_dir / "quality_report.json", quality_report)
        self._write_progress(run_dir, run_id, "completed", "日报生成完成", started_at, {"report": str(run_dir / "report.json")})
        run_meta = self._build_run_meta(task_path, run_dir, run_id, task, raw_results, extracted_pages, candidates_payload, deduped_payload, quality_report, signals_count=len(report.get("signals", [])), status="completed")
        write_json(run_dir / "run_meta.json", run_meta)
        return run_meta

    def _prioritize_results(self, results: list[SearchResult], task: ResearchTask, limit: int) -> list[SearchResult]:
        company_terms = []
        for config in task.runtime_sector_config:
            company_terms.extend(config.get("companies", []) or config.get("related_companies", []) or [])
        keyword_terms = task.keywords + company_terms

        def score(result: SearchResult) -> tuple[int, float, str]:
            text = f"{result.title} {result.summary} {result.source_name}".lower()
            url = result.url.lower()
            tier_score = 0
            if any(host in url for host in ("cninfo", "sse.com", "szse.cn")):
                tier_score += 80
            if result.source_name in {"巨潮资讯", "上交所", "深交所"}:
                tier_score += 80
            if result.source_name in {"财联社", "证券时报", "中国证券报", "上海证券报", "第一财经", "21财经"}:
                tier_score += 50
            hit_score = sum(1 for term in keyword_terms if str(term).lower() and str(term).lower() in text)
            return (tier_score + hit_score * 5, result.score, result.title)

        return sorted(results, key=score, reverse=True)[:limit]

    def _limit_kept_items(self, items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        def score(item: dict[str, Any]) -> tuple[int, int]:
            quality = item.get("quality", {}) or {}
            source_tier = str(item.get("source_tier", ""))
            tier_score = {"S": 70, "A": 55, "B": 35, "C": 10}.get(source_tier, 0)
            company_score = 25 if quality.get("company_hit") else 0
            p0_score = 30 if quality.get("p0_eligible") else 0
            primary_score = 15 if item.get("is_primary_source") else 0
            keyword_score = len(item.get("matched_keywords", []) or [])
            text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('raw_text_excerpt', '')}"
            industry_score = industry_signal_score(text)
            low_value_penalty = low_value_market_disclosure_penalty(text)
            return (tier_score + company_score + p0_score + primary_score + keyword_score + industry_score - low_value_penalty, keyword_score)

        return sorted(items, key=score, reverse=True)[:limit]

    def _write_progress(self, run_dir: Path, run_id: str, stage: str, message: str, started_at: float, artifacts: dict[str, Any] | None = None, error: str = "") -> None:
        write_json(run_dir / "progress.json", {
            "run_id": run_id,
            "stage": stage,
            "message": message,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(time.perf_counter() - started_at, 1),
            "artifacts": artifacts or {},
            "error": error,
        })

    def _build_run_meta(
        self,
        task_path: Path,
        run_dir: Path,
        run_id: str,
        task: ResearchTask,
        raw_results: list[SearchResult],
        extracted_pages: list[dict],
        candidates_payload: dict[str, Any],
        deduped_payload: dict[str, Any],
        quality_report: dict[str, Any],
        signals_count: int,
        status: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "status": status,
            "task_path": str(task_path),
            "run_dir": str(run_dir),
            "date": task.date,
            "sectors": task.sectors,
            "model": "senseaudio-s2" if status == "completed" else "not_invoked",
            "generation_mode": quality_report.get("generation_mode", {}),
            "quality_warnings": quality_report.get("quality_warnings", []),
            "suggested_fixes": quality_report.get("suggested_fixes", []),
            "senseaudio_key_source": self.senseaudio_api_key_source or "not_used",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "counts": {
                "raw_results": len(raw_results),
                "extracted_pages": len(extracted_pages),
                "candidates": len(candidates_payload["candidates"]),
                "kept_items": len(deduped_payload["kept_items"]),
                "signals": signals_count,
                "sa_source_items": quality_report.get("summary", {}).get("sa_source_items", 0),
                "company_hit_items": quality_report.get("summary", {}).get("company_hit_items", 0),
                "p0_eligible_items": quality_report.get("summary", {}).get("p0_eligible_items", 0),
                "search_error_count": len(self.search_errors),
            },
            "artifacts": {
                "task": str(run_dir / "task.json"),
                "sector_profile": str(run_dir / "sector_profile.json"),
                "search_plan": str(run_dir / "search_plan.json"),
                "source_registry_results": str(run_dir / "source_registry_results.json"),
                "search_results": str(run_dir / "search_results.json"),
                "search_errors": str(run_dir / "search_errors.json"),
                "extracted_pages": str(run_dir / "extracted_pages.json"),
                "candidates": str(run_dir / "candidates.json"),
                "deduped_news": str(run_dir / "deduped_news.json"),
                "quality_report": str(run_dir / "quality_report.json"),
                "rated_signals": str(run_dir / "rated_signals.json"),
                "trends": str(run_dir / "trends.json"),
                "report": str(run_dir / "report.json"),
            },
        }

    async def _search_all(self, queries: list[str], max_results: int) -> list[SearchResult]:
        providers = []
        if self.searxng_url and await self._searxng_available():
            providers.append(("searxng", SearXNGProvider(self.searxng_url), queries))
        elif self.searxng_url:
            self.search_errors.append({"provider": "searxng", "query": "healthcheck", "error_type": "Unavailable", "error": "SearXNG service is not reachable"})
        if self.use_commercial_search and self.tavily_api_key:
            providers.append(("tavily", TavilyProvider(self.tavily_api_key), queries[:4]))
        if self.use_commercial_search and self.gnews_api_key:
            providers.append(("gnews", GNewsProvider(self.gnews_api_key), gnews_queries(queries)[:3]))
        if not providers:
            return []

        results: list[SearchResult] = []
        for provider_name, provider, provider_queries in providers:
            for query in provider_queries:
                try:
                    batch = await provider.search(query, max_results)
                except Exception as error:
                    self.search_errors.append({
                        "provider": provider_name,
                        "query": query,
                        "error_type": type(error).__name__,
                        "error": sanitize_error(error),
                    })
                    if provider_name in {"gnews", "tavily"}:
                        break
                    continue
                results.extend(batch)
        return self._unique_results(results)

    async def _searxng_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0), follow_redirects=True) as client:
                response = await client.get(self.searxng_url)
            return response.status_code < 500
        except Exception:
            return False

    def _unique_results(self, results: list[SearchResult]) -> list[SearchResult]:
        seen = set()
        unique = []
        for result in results:
            key = result.url.split("?", 1)[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            unique.append(result)
        return unique
