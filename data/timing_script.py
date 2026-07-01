"""Run ResearchRunner with full LLM and print timing breakdown."""
import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from dotenv import load_dotenv
from app.core.config import PROJECT_ROOT
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from research_agent.models import ResearchTask
from research_agent.runner import ResearchRunner

async def main():
    task_path = Path(__file__).resolve().parent / "research_tasks" / "temp_profile_low_confidence_test.json"
    task = ResearchTask.from_dict(__import__("json").loads(task_path.read_text("utf-8")))
    
    runner = ResearchRunner(
        senseaudio_api_key="",  # will load from DB
        use_commercial_search=False,
    )
    
    t0 = time.time()
    meta = await runner.run_task(task, run_id="timing_run_20260628_full")
    t1 = time.time()
    
    total = t1 - t0
    status = meta.get("status", "unknown")
    counts = meta.get("counts", {})
    
    print(f"total: {total:.1f}s")
    print(f"status: {status}")
    print(f"kept_items: {counts.get('kept_items', 0)}")
    print(f"signals: {counts.get('signals', 0)}")
    print(f"model: {meta.get('model', 'none')}")
    print(f"run_dir: {meta.get('run_dir', '')}")
    print(f"created_at: {meta.get('created_at', '')}")
    print(f"generation_mode: {meta.get('generation_mode', {}).get('mode', '')}")

if __name__ == "__main__":
    asyncio.run(main())
