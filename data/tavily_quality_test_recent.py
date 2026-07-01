import json
import time
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env_path = root / "backend" / ".env"
api_key = ""
for line in env_path.read_text(encoding="utf-8").splitlines():
    if line.strip().startswith("TAVILY_API_KEY="):
        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not api_key:
    raise SystemExit("TAVILY_API_KEY not found in backend/.env")

queries = [
    "机器人产业链 人形机器人 订单 最新",
    "汇川技术 伺服系统 机器人 最新",
    "HBM 存储芯片 订单 最新",
]
variants = [
    {"name": "basic", "include_raw_content": False},
    {"name": "raw", "include_raw_content": True},
]
summary = []
for query in queries:
    for variant in variants:
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5,
            "include_answer": False,
            "include_raw_content": variant["include_raw_content"],
        }
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            summary.append({"query": query, "variant": variant["name"], "error": f"HTTP {exc.code}"})
            continue
        rows = []
        for item in data.get("results") or []:
            raw = str(item.get("raw_content") or "")
            content = str(item.get("content") or "")
            rows.append({
                "title": str(item.get("title") or "")[:90],
                "url": str(item.get("url") or "")[:120],
                "content_len": len(content),
                "raw_content_len": len(raw),
                "published_date": item.get("published_date") or item.get("publishedDate") or "",
                "score": item.get("score"),
            })
        summary.append({"query": query, "variant": variant["name"], "results": rows})
        time.sleep(0.4)

out_path = root / "data" / "tavily_quality_recent_result.json"
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(str(out_path))
