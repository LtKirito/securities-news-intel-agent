import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

from app.core.security import decrypt_text
from app.db.database import SessionLocal
from app.db.models import Report, UserApiKey
from app.services.sector_templates import load_sector_template, template_to_sector_config
from research_agent.models import ResearchTask
from research_agent.runner import ResearchRunner


def merge_unique(*groups):
    out = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
    return out


def as_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def to_research_sector_config(config):
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


async def main():
    template = load_sector_template("robotics")
    config = template_to_sector_config(template)
    sector = config["name"]
    date = datetime.now().strftime("%Y-%m-%d")
    task = ResearchTask(
        date=date,
        user_id="1",
        date_window="滚动24小时",
        sectors=[sector],
        keywords=merge_unique([sector], as_list(config.get("keywords")), as_list(config.get("expanded_keywords"))),
        max_results_per_query=6,
        max_candidates=30,
        runtime_sector_config=[to_research_sector_config(config)],
        display_preferences={
            "language": "zh-CN",
            "market_convention": "中国金融市场：涨红跌绿",
            "style": "投研工作台日报，事实和判断分离",
        },
        rating_overlay={"p0_strictness": "standard"},
    )

    db = SessionLocal()
    key = db.query(UserApiKey).filter(UserApiKey.user_id == 1).first()
    if not key:
        raise RuntimeError("user 1 API key not configured")
    api_key = decrypt_text(key.encrypted_key)
    db.close()

    runner = ResearchRunner(senseaudio_api_key=api_key, use_commercial_search=False)
    t0 = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    print(json.dumps({"event": "started", "started_at": started_at, "sector": sector}, ensure_ascii=False), flush=True)
    meta = await runner.run_task(task)
    ended_at = datetime.now().isoformat(timespec="seconds")
    elapsed = time.perf_counter() - t0

    run_id = meta.get("run_id", "")
    run_dir = Path(meta.get("run_dir", ""))
    report_path = meta.get("artifacts", {}).get("report", "")
    run_meta_path = str(run_dir / "run_meta.json") if run_dir else ""

    db = SessionLocal()
    row = db.query(Report).filter(Report.run_id == run_id).first()
    created = False
    if not row:
        row = Report(
            run_id=run_id,
            user_id=1,
            date=task.date,
            sector=sector,
            title=f"证券产业新闻情报日报｜{task.date}",
            html_path="",
            json_path=report_path or "",
            run_meta_path=run_meta_path,
        )
        db.add(row)
        created = True
    else:
        row.json_path = report_path or row.json_path
        row.run_meta_path = run_meta_path or row.run_meta_path
    db.commit()
    report_id = row.id
    db.close()

    report = json.loads(Path(report_path).read_text(encoding="utf-8")) if report_path else {}
    result = {
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": round(elapsed, 1),
        "run_id": run_id,
        "report_id": report_id,
        "db_created": created,
        "run_dir": str(run_dir),
        "report_path": report_path,
        "run_meta_path": run_meta_path,
        "status": meta.get("status"),
        "model": meta.get("model"),
        "generation_mode": meta.get("generation_mode", {}),
        "counts": meta.get("counts", {}),
        "title": report.get("title"),
        "summary": report.get("summary"),
        "conclusions": report.get("conclusions", []),
        "signals": [
            {
                "rank": s.get("rank"),
                "title": s.get("title"),
                "summary": s.get("summary"),
                "sources": [src.get("name") for src in s.get("sources", [])],
            }
            for s in report.get("signals", [])
        ],
    }
    out = PROJECT / "data" / "real_generation_timing_latest.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"event": "completed", **result}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
