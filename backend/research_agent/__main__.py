from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .credentials import load_user_senseaudio_key
from .storage import read_json

from dotenv import load_dotenv

from app.core.config import PROJECT_ROOT
from .models import ResearchTask
from .runner import ResearchRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run standalone securities research agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run a research task JSON")
    run.add_argument("--task", required=True, help="Path to research task JSON")
    run.add_argument("--run-id", default="", help="Optional run id")
    run.add_argument("--tavily-api-key", default="", help="Tavily API key; defaults to env")
    run.add_argument("--gnews-api-key", default="", help="GNews API key; defaults to env")
    run.add_argument("--disable-tavily", action="store_true", help="Disable Tavily provider for this run")
    run.add_argument("--disable-gnews", action="store_true", help="Disable GNews provider for this run")
    run.add_argument("--searxng-url", default=None, help="Self-hosted SearXNG base URL; defaults to SEARXNG_URL")
    run.add_argument("--disable-searxng", action="store_true", help="Disable SearXNG provider for this run")
    run.add_argument("--use-commercial-search", action="store_true", help="Allow Tavily/GNews commercial search fallback")
    run.add_argument("--senseaudio-api-key", default="", help="SenseAudio API key; defaults to env")
    run.add_argument("--no-llm", action="store_true", help="Stop after search, extraction, normalization and dedup")
    key = subparsers.add_parser("key-source", help="Show which SenseAudio key source would be used for a task")
    key.add_argument("--task", required=True, help="Path to research task JSON")
    key.add_argument("--senseaudio-api-key", default="", help="SenseAudio API key; highest priority if provided")
    return parser


def main() -> None:
    load_dotenv(PROJECT_ROOT / "backend" / ".env")
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        task_path = Path(args.task)
        if not task_path.is_absolute():
            task_path = (Path.cwd() / task_path).resolve()
        runner = ResearchRunner(
            tavily_api_key="" if args.disable_tavily else args.tavily_api_key or os.getenv("TAVILY_API_KEY", ""),
            gnews_api_key="" if args.disable_gnews else args.gnews_api_key or os.getenv("GNEWS_API_KEY", ""),
            senseaudio_api_key=args.senseaudio_api_key,
            searxng_url="" if args.disable_searxng else args.searxng_url,
            use_commercial_search=args.use_commercial_search,
        )
        result = asyncio.run(runner.run(task_path, args.run_id or None, no_llm=args.no_llm))
        print(f"run_id={result['run_id']}")
        print(f"run_dir={result['run_dir']}")
        print(f"report={result['artifacts']['report']}")
    elif args.command == "key-source":
        task_path = Path(args.task)
        if not task_path.is_absolute():
            task_path = (Path.cwd() / task_path).resolve()
        task = ResearchTask.from_dict(read_json(task_path))
        if args.senseaudio_api_key:
            source = "cli"
        elif load_user_senseaudio_key(task.user_id):
            source = "database"
        elif os.getenv("SENSEAUDIO_API_KEY", ""):
            source = "env"
        else:
            source = "missing"
        print(f"user_id={task.user_id}")
        print(f"senseaudio_key_source={source}")


if __name__ == "__main__":
    main()
