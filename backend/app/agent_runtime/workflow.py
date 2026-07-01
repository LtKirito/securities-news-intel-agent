import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.senseaudio_client import SenseAudioClient
from app.services.agent_loader import AgentLoader
from app.services.post_run_validator import PostRunValidator
from app.services.report_storage import ReportStorage
from app.services.schema_validator import SchemaValidator


@dataclass
class StageSpec:
    name: str
    skill: str
    schema: str
    output_name: str


STAGES = [
    StageSpec("workflow_plan", "securities-daily-intel-pipeline", "workflow_plan.schema.json", "workflow_plan.json"),
    StageSpec("source_research", "securities-source-research", "candidates.schema.json", "candidates.json"),
    StageSpec("news_dedup", "securities-news-dedup", "deduped_news.schema.json", "deduped_news.json"),
    StageSpec("priority_rating", "securities-priority-rating", "rated_signals.schema.json", "rated_signals.json"),
    StageSpec("trend_analysis", "securities-trend-analysis", "trends.schema.json", "trends.json"),
]


def build_quality_policy(sector_configs: list[dict[str, Any]], request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request or {}
    profile_statuses = {config.get("profile_status", "curated") for config in sector_configs}
    warnings = []
    fixes = []
    allow_limited = request.get("allow_limited_confidence_report", True)
    allow_commercial = request.get("allow_commercial_fallback", False)
    relax_gate = request.get("relax_quality_gate", False)
    if "temporary" in profile_statuses:
        warnings.append("该板块暂无成熟画像，系统已使用临时画像采集。")
        warnings.append("公司池可能不足，日报精度可能低于成熟板块。")
        fixes.append("补充 5-15 家代表上市公司，并保存为板块画像。")
    for config in sector_configs:
        warnings.extend(config.get("profile_warnings", []) or [])
        if not config.get("related_companies"):
            fixes.append("该板块缺少上市公司画像，请补充 5-15 家代表公司。")
    if relax_gate:
        warnings.append("本次已选择放宽门槛，报告只应作为观察版参考。")
    if allow_commercial:
        fixes.append("本次允许在固定源不足时启用 SearXNG、GNews 或 Tavily 兜底。")
    else:
        fixes.append("固定源不足时，优先补巨潮、互动平台和主流证券媒体，不先消耗商业 API。")
    fixes.extend([
        "优先补充巨潮、互动易、上证e互动、财联社、证券时报、东方财富、第一财经、21财经等固定源。",
        "如仍不足，可选择只保存采集结果、放宽本次门槛、补充配置后重试或启用商业搜索兜底。",
    ])
    mode = "limited_confidence_report" if warnings or relax_gate else "high_confidence_report"
    if not allow_limited and mode != "high_confidence_report":
        mode = "collection_only"
        fixes.append("当前未允许低置信日报；建议先保存采集结果，补充板块配置后重试。")
    return {
        "generation_mode": mode,
        "label": "仅保存采集结果" if mode == "collection_only" else "观察版日报" if mode != "high_confidence_report" else "正式日报",
        "allow_limited_confidence_report": allow_limited,
        "allow_commercial_fallback": allow_commercial,
        "relax_quality_gate": relax_gate,
        "quality_warnings": dedupe_text(warnings),
        "suggested_fixes": dedupe_text(fixes),
        "must_disclose_limitations": bool(warnings) or relax_gate or mode == "collection_only",
    }


def attach_workflow_quality(report: dict[str, Any], policy: dict[str, Any]) -> None:
    report["generation_mode"] = {
        "mode": policy.get("generation_mode", "high_confidence_report"),
        "label": policy.get("label", "正式日报"),
        "must_disclose_limitations": policy.get("must_disclose_limitations", False),
    }
    report["quality_warnings"] = policy.get("quality_warnings", [])
    report["suggested_fixes"] = policy.get("suggested_fixes", [])
    if report["quality_warnings"]:
        prefix = "；".join(report["quality_warnings"][:2])
        disclaimer = report.get("disclaimer", "")
        report["disclaimer"] = f"质量提示：{prefix}。{disclaimer}".strip()


def dedupe_text(items: list[str]) -> list[str]:
    result = []
    for item in items:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


class WorkflowRunner:
    def __init__(
        self,
        llm_client: SenseAudioClient,
        loader: AgentLoader | None = None,
        schema_validator: SchemaValidator | None = None,
        storage: ReportStorage | None = None,
        post_validator: PostRunValidator | None = None,
    ):
        self.llm = llm_client
        self.loader = loader or AgentLoader()
        self.schema_validator = schema_validator or SchemaValidator(self.loader)
        self.storage = storage or ReportStorage()
        self.post_validator = post_validator or PostRunValidator()

    async def run(self, user_id: int, request: dict[str, Any], sector_configs: list[dict[str, Any]]) -> dict[str, Any]:
        run_id = request.get("run_id") or uuid.uuid4().hex
        date = request["date"]
        context: dict[str, Any] = {
            "run_id": run_id,
            "user_id": str(user_id),
            "date": date,
            "request": request,
            "sector_configs": sector_configs,
            "artifacts": {},
            "quality_policy": build_quality_policy(sector_configs, request),
        }

        for stage in STAGES:
            payload = await self._run_stage(stage, context)
            context["artifacts"][stage.name] = payload
            self.storage.save_artifact(user_id, date, stage.output_name, payload)

        report = await self._run_report_format(context)
        report["run_id"] = run_id
        report["user_id"] = str(user_id)
        report["date"] = date
        attach_workflow_quality(report, context.get("quality_policy", {}))
        report_validation = self.schema_validator.validate("report.schema.json", report)
        if not report_validation.valid:
            report = await self._repair_json("report_format", "report.schema.json", report, report_validation.errors, context)

        business_validation = self.post_validator.validate_report(report, user_id)
        if not business_validation.valid:
            raise ValueError("Report business validation failed: " + "; ".join(business_validation.errors))

        sector = report.get("sectors", ["default"])[0]
        report_json_path = self.storage.save_sector_json(user_id, date, sector, "report.json", report)
        html = report.get("html", self._fallback_html(report))
        report_html_path = self.storage.save_sector_html(user_id, date, sector, html)
        run_meta = self._build_run_meta(context, report, str(report_json_path), str(report_html_path))
        run_meta_path = self.storage.save_sector_json(user_id, date, sector, "run_meta.json", run_meta)
        return {"run_id": run_id, "sector": sector, "report_json_path": str(report_json_path), "report_html_path": str(report_html_path), "run_meta_path": str(run_meta_path)}

    async def _run_stage(self, stage: StageSpec, context: dict[str, Any]) -> dict[str, Any]:
        messages = self._build_stage_messages(stage, context)
        payload = await self.llm.chat_json(messages)
        validation = self.schema_validator.validate(stage.schema, payload)
        if validation.valid:
            return payload
        return await self._repair_json(stage.name, stage.schema, payload, validation.errors, context)

    async def _repair_json(self, stage_name: str, schema_name: str, invalid_payload: dict, errors: list[str], context: dict[str, Any]) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": "你是 JSON 修复器。只返回修复后的 JSON，不要解释。"},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "stage": stage_name,
                        "schema": json.loads(self.loader.load_schema(schema_name)),
                        "validation_errors": errors,
                        "invalid_payload": invalid_payload,
                        "context_keys": list(context.keys()),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        repaired = await self.llm.chat_json(messages, temperature=0)
        validation = self.schema_validator.validate(schema_name, repaired)
        if not validation.valid:
            raise ValueError(f"{stage_name} output failed schema validation after repair: {validation.errors}")
        return repaired

    def _build_stage_messages(self, stage: StageSpec, context: dict[str, Any]) -> list[dict[str, str]]:
        base_context = self.loader.load_base_context()
        payload = {
            "pipeline_skill": self.loader.load_pipeline_skill(),
            "quality_policy": context.get("quality_policy", {}),
            "stage_skill": self.loader.load_skill(stage.skill),
            "base_context": base_context,
            "output_schema": json.loads(self.loader.load_schema(stage.schema)),
            "runtime_context": context,
        }
        return [
            {"role": "system", "content": "你是证券日报 Workflow Runner 的阶段执行器。严格按技能、配置和 schema 执行。只返回 JSON。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    async def _run_report_format(self, context: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "pipeline_skill": self.loader.load_pipeline_skill(),
            "quality_policy": context.get("quality_policy", {}),
            "stage_skill": self.loader.load_skill("securities-report-format"),
            "report_schema": json.loads(self.loader.load_schema("report.schema.json")),
            "template_schema": json.loads(self.loader.load_template("daily_report.schema.json")),
            "html_template": self.loader.load_template("daily_report.html"),
            "runtime_context": context,
        }
        return await self.llm.chat_json([
            {"role": "system", "content": "你是证券日报报告格式化阶段执行器。生成 report.json 所需字段；如包含 html 字段，也必须与报告一致。只返回 JSON。若 quality_policy.generation_mode 不是 high_confidence_report，必须在摘要、结论或免责声明中标注观察版/持续跟踪、精度不足原因和补救建议，不得伪装成高置信日报。"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])

    def _build_run_meta(self, context: dict[str, Any], report: dict, report_json_path: str, report_html_path: str) -> dict:
        return {
            "run_id": context["run_id"],
            "user_id": context["user_id"],
            "date": context["date"],
            "sectors": report.get("sectors", []),
            "model": "senseaudio-s2",
            "workflow_version": "0.1.0",
            "config_snapshot": context.get("request", {}),
            "agent_skill_snapshot": self.loader.snapshot_skills(),
            "artifacts": {"report_json": report_json_path, "report_html": report_html_path},
            "quality_checks": {"schema_valid": True, "source_urls_present": True, "no_investment_advice": True, "p0_sparse_checked": True},
            "generation_mode": context.get("quality_policy", {}).get("generation_mode", "high_confidence_report"),
            "quality_warnings": context.get("quality_policy", {}).get("quality_warnings", []),
            "suggested_fixes": context.get("quality_policy", {}).get("suggested_fixes", []),
        }

    def _fallback_html(self, report: dict) -> str:
        title = report.get("title", "证券产业新闻情报日报")
        conclusions = "".join(f"<li>{item}</li>" for item in report.get("conclusions", []))
        return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{title}</title></head><body><h1>{title}</h1><ul>{conclusions}</ul></body></html>"
