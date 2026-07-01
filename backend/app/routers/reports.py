import asyncio
import html
import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent_runtime.workflow import WorkflowRunner
from app.core.mock_llm_client import MockSenseAudioClient
from app.core.security import decrypt_text
from app.core.senseaudio_client import SenseAudioError
from app.db.database import SessionLocal, get_db
from app.db.models import Report, SectorConfig, User, UserApiKey
from app.db.schemas import ReportGenerateRequest
from app.routers.deps import get_current_user
from app.services.report_storage import ReportStorage
from app.services.sector_templates import get_sector_template
from research_agent.models import ResearchTask
from research_agent.runner import ResearchRunner

router = APIRouter()
CN_TZ = timezone(timedelta(hours=8))


def to_cn_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CN_TZ).isoformat()


def to_research_sector_config(config: dict) -> dict:
    return {
        "name": config.get("name", ""),
        "keywords": as_list(config.get("keywords")) + as_list(config.get("expanded_keywords")),
        "companies": as_list(config.get("companies") or config.get("related_companies")),
        "supply_chain_nodes": as_list(config.get("supply_chain_nodes") or config.get("chain_nodes")),
        "event_types": as_list(config.get("event_types") or config.get("verification_metrics")),
        "preferred_sources": as_list(config.get("preferred_sources")),
        "exclude_terms": as_list(config.get("exclude_terms") or config.get("exclude_keywords")),
        "profile_status": config.get("profile_status", "curated"),
        "profile_warnings": as_list(config.get("profile_warnings")),
    }


def as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def merge_unique(*groups: list[str]) -> list[str]:
    result = []
    for group in groups:
        for item in group:
            if item and item not in result:
                result.append(item)
    return result


@router.post("/generate")
async def generate_report(payload: ReportGenerateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    sector_name = payload.sectors[0] if payload.sectors else "未命名板块"
    
    if payload.use_mock:
        # Mock mode: synchronous (fast, no background needed)
        sector_configs = _build_sector_configs(payload, current_user, db)
        llm_client = MockSenseAudioClient()
        try:
            result = await WorkflowRunner(llm_client).run(current_user.id, payload.model_dump(), sector_configs)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"日报生成结果校验未通过：{exc}") from exc
        report = Report(
            run_id=result["run_id"],
            user_id=current_user.id,
            date=payload.date,
            sector=result["sector"],
            title=f"证券产业新闻情报日报｜{payload.date}",
            html_path=result.get("report_html_path", ""),
            json_path=result.get("report_json_path", ""),
            run_meta_path=result.get("run_meta_path", ""),
        )
        db.add(report)
        db.commit()
        result["report_id"] = report.id
        return result

    # Real mode: return immediately, then generate in background.
    try:
        key = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).first()
        if not key:
            raise HTTPException(status_code=400, detail="API key not configured")
        api_key = decrypt_text(key.encrypted_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"API key decryption failed: {exc}") from exc

    sector_configs = _build_sector_configs(payload, current_user, db)
    task = build_research_task_with_sector(payload, current_user.id, sector_configs)
    run_id = uuid.uuid4().hex
    report = Report(
        run_id=run_id,
        user_id=current_user.id,
        date=payload.date,
        sector=sector_name,
        title=f"证券产业新闻情报日报｜{payload.date}",
        html_path="",
        json_path="pending",
        run_meta_path="",
    )
    db.add(report)
    db.commit()
    report_id = report.id

    asyncio.create_task(_run_generation_in_bg(report_id, run_id, task, api_key, payload.allow_commercial_fallback))
    return {
        "run_id": run_id,
        "report_id": report_id,
        "sector": sector_name,
        "status": "generating",
    }


async def _run_generation_in_bg(report_id: int, run_id: str, task: ResearchTask, api_key: str, allow_commercial_fallback: bool) -> None:
    db = SessionLocal()
    try:
        runner = ResearchRunner(
            senseaudio_api_key=api_key,
            use_commercial_search=allow_commercial_fallback,
        )
        run_meta = await runner.run_task(task, run_id=run_id)
        row = db.get(Report, report_id)
        if row:
            _sync_completed_report_artifacts(row, run_meta)
            db.commit()
    except SenseAudioError as exc:
        row = db.get(Report, report_id)
        if row:
            row.json_path = f"error:真实模型调用未完成：{exc}"
            db.commit()
    except ValueError as exc:
        row = db.get(Report, report_id)
        if row:
            row.json_path = f"error:日报生成结果校验未通过：{exc}"
            db.commit()
    except Exception as exc:
        row = db.get(Report, report_id)
        if row:
            row.json_path = f"error:日报生成任务异常：{exc}"
            db.commit()
    finally:
        db.close()


def _needs_history_artifact_sync(row: Report) -> bool:
    if not row.json_path or row.json_path == "pending" or row.json_path.startswith("error:"):
        return False
    if not Path(row.json_path).exists():
        return False
    return "data\\research_runs" in row.json_path or "data/research_runs" in row.json_path or not row.html_path


def _sync_completed_report_artifacts(row: Report, run_meta: dict) -> None:
    report_path = Path(run_meta.get("artifacts", {}).get("report", ""))
    run_meta_path = Path(run_meta.get("run_dir", "")) / "run_meta.json" if run_meta.get("run_dir") else Path("")
    if not report_path.exists():
        row.json_path = "error:日报文件未生成"
        row.html_path = ""
        row.run_meta_path = str(run_meta_path) if run_meta_path.exists() else ""
        row.updated_at = datetime.utcnow()
        return

    storage = ReportStorage()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    sector = row.sector or (report.get("sectors") or [""])[0]
    target_dir = storage.sector_dir(row.user_id, row.date, sector)
    target_json = target_dir / f"report_{row.run_id[:12]}.json"
    target_meta = target_dir / f"run_meta_{row.run_id[:12]}.json"
    target_html = target_dir / f"report_{row.run_id[:12]}.html"

    shutil.copyfile(report_path, target_json)
    if run_meta_path.exists():
        shutil.copyfile(run_meta_path, target_meta)
    else:
        target_meta.write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    target_html.write_text(_render_report_html(report), encoding="utf-8")

    row.json_path = str(target_json)
    row.run_meta_path = str(target_meta)
    row.html_path = str(target_html)
    row.updated_at = datetime.utcnow()


def _render_report_html(report: dict) -> str:
    title = html.escape(str(report.get("title") or "证券产业新闻情报日报"))
    summary = html.escape(str(report.get("summary") or ""))
    signals = report.get("signals") or []
    signal_blocks = []
    for signal in signals:
        rank = html.escape(str(signal.get("rank") or ""))
        signal_title = html.escape(str(signal.get("title") or "未命名信号"))
        signal_summary = html.escape(str(signal.get("summary") or ""))
        follow_up = html.escape(str(signal.get("follow_up") or ""))
        signal_blocks.append(f"<section><h2>{rank}｜{signal_title}</h2><p>{signal_summary}</p><p class='follow'>后续：{follow_up}</p></section>")
    return "".join([
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        "<style>body{font-family:Microsoft YaHei,Arial,sans-serif;margin:40px;line-height:1.7;color:#172033;background:#f7f4ef}main{max-width:980px;margin:auto;background:#fff;padding:32px;border-radius:16px;box-shadow:0 12px 40px #0001}h1{color:#18324c}section{border-top:1px solid #e6dccd;padding:18px 0}.follow{color:#6b5b43}</style>",
        "</head><body><main>",
        f"<h1>{title}</h1><p>{summary}</p>",
        "".join(signal_blocks),
        "</main></body></html>",
    ])


def _build_sector_configs(payload: ReportGenerateRequest, current_user: User, db: Session) -> list[dict]:
    sector_configs = []
    if payload.runtime_sector_config:
        runtime_config = payload.runtime_sector_config.model_dump()
        runtime_config["companies"] = as_list(runtime_config.get("companies") or runtime_config.get("related_companies"))
        runtime_config["supply_chain_nodes"] = as_list(runtime_config.get("supply_chain_nodes") or runtime_config.get("chain_nodes"))
        runtime_config["event_types"] = as_list(runtime_config.get("event_types") or runtime_config.get("verification_metrics"))
        runtime_config["preferred_sources"] = as_list(runtime_config.get("preferred_sources"))
        runtime_config["exclude_terms"] = as_list(runtime_config.get("exclude_terms") or runtime_config.get("exclude_keywords"))
        runtime_config["source_preferences"] = payload.source_preferences
        runtime_config["rating_overlay"] = payload.rating_overlay
        sector_configs = [runtime_config]
        if payload.save_config:
            row = db.query(SectorConfig).filter(SectorConfig.user_id == current_user.id, SectorConfig.name == payload.runtime_sector_config.name).first()
            config_json = json.dumps(runtime_config, ensure_ascii=False)
            if row:
                row.enabled = payload.runtime_sector_config.enabled
                row.config_json = config_json
                row.updated_at = datetime.utcnow()
            else:
                db.add(SectorConfig(user_id=current_user.id, name=payload.runtime_sector_config.name, enabled=payload.runtime_sector_config.enabled, config_json=config_json))
            db.commit()
    else:
        rows = db.query(SectorConfig).filter(SectorConfig.user_id == current_user.id, SectorConfig.name.in_(payload.sectors)).all()
        sector_configs = [json.loads(row.config_json) for row in rows]
    if not sector_configs:
        sector_name = payload.sectors[0] if payload.sectors else "未命名板块"
        template = get_sector_template(sector_name)
        if template:
            template = dict(template)
            template["source_preferences"] = payload.source_preferences
            template["rating_overlay"] = payload.rating_overlay
            sector_configs = [template]
        else:
            sector_configs = [{
                "name": sector_name,
                "enabled": True,
                "keywords": [sector_name, "公告", "投资者关系", "订单", "量产", "扩产", "业绩", "风险提示", "异动"],
                "expanded_keywords": [],
                "exclude_keywords": ["股吧", "论坛", "百科", "课程", "广告", "二手", "下载"],
                "related_companies": [],
                "chain_nodes": [sector_name],
                "verification_metrics": ["公告", "订单", "量产", "扩产", "业绩", "风险提示"],
                "profile_status": "temporary",
                "profile_warnings": ["该板块暂无成熟画像，系统已使用临时画像采集。建议补充 5-15 家代表上市公司以提升准确率。"],
                "source_preferences": payload.source_preferences,
                "rating_overlay": payload.rating_overlay,
            }]
    return sector_configs


def build_research_task_with_sector(payload: ReportGenerateRequest, user_id: int, sector_configs: list[dict]) -> ResearchTask:
    sector_name = payload.sectors[0] if payload.sectors else sector_configs[0].get("name", "未命名板块")
    keywords = merge_unique([sector_name], *[as_list(config.get("keywords")) for config in sector_configs])
    runtime_configs = [to_research_sector_config(config) for config in sector_configs]
    return ResearchTask(
        date=payload.date,
        user_id=str(user_id),
        date_window=payload.date_window or "滚动24小时",
        sectors=[sector_name],
        keywords=keywords,
        max_results_per_query=6,
        max_candidates=30,
        runtime_sector_config=runtime_configs,
        display_preferences={
            "language": "zh-CN",
            "market_convention": "中国金融市场：涨红跌绿",
            "style": "投研工作台日报，事实和判断分离",
        },
        rating_overlay=payload.rating_overlay,
    )


@router.get("/{report_id}/status")
def get_report_status(report_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Report, report_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    if row.json_path == "pending":
        progress = {}
        run_dir = Path("data") / "research_runs" / row.run_id
        progress_path = run_dir / "progress.json"
        if progress_path.exists():
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        return {"status": "generating", "report_id": report_id, "run_id": row.run_id, "progress": progress}
    if row.json_path and row.json_path.startswith("error:"):
        return {"status": "error", "error": row.json_path[6:], "report_id": report_id, "run_id": row.run_id}
    return {"status": "done", "report_id": report_id, "run_id": row.run_id}


@router.get("")
def list_reports(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Report).filter(Report.user_id == current_user.id).order_by(Report.created_at.desc(), Report.id.desc()).all()
    changed = False
    for row in rows:
        if _needs_history_artifact_sync(row):
            run_dir = Path("data") / "research_runs" / row.run_id
            run_meta_path = run_dir / "run_meta.json"
            if run_meta_path.exists():
                _sync_completed_report_artifacts(row, json.loads(run_meta_path.read_text(encoding="utf-8")))
                changed = True
    if changed:
        db.commit()
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "date": row.date,
            "sector": row.sector,
            "title": row.title,
            "html_path": row.html_path,
            "json_path": row.json_path,
            "created_at": to_cn_iso(row.created_at),
        }
        for row in rows
    ]


@router.get("/{report_id}")
def get_report(report_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Report, report_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    if row.json_path == "pending":
        raise HTTPException(status_code=425, detail="Report is still being generated")
    if row.json_path.startswith("error:"):
        raise HTTPException(status_code=422, detail=f"Report generation failed: {row.json_path[6:]}")
    path = Path(row.json_path)
    return json.loads(path.read_text(encoding="utf-8"))
