import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
api_key = ""
for line in (root / "backend" / ".env").read_text(encoding="utf-8").splitlines():
    if line.strip().startswith("GNEWS_API_KEY="):
        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not api_key:
    raise SystemExit("GNEWS_API_KEY not found")

cases = [
    {"name": "zh_cn_robot", "q": "机器人", "lang": "zh", "country": "cn"},
    {"name": "zh_any_robot", "q": "机器人", "lang": "zh"},
    {"name": "zh_cn_chip", "q": "芯片", "lang": "zh", "country": "cn"},
    {"name": "zh_any_chip", "q": "芯片", "lang": "zh"},
    {"name": "zh_stock", "q": "上市公司", "lang": "zh"},
    {"name": "en_ai_chip", "q": "AI chip", "lang": "en"},
    {"name": "en_robotics", "q": "robotics", "lang": "en"},
]
summary = []
for case in cases:
    params = {"q": case["q"], "lang": case["lang"], "max": "10", "apikey": api_key}
    if case.get("country"):
        params["country"] = case["country"]
    url = "https://gnews.io/api/v4/search?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        summary.append({"case": case, "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')[:300]}"})
        continue
    articles = []
    for item in data.get("articles") or []:
        source = item.get("source") or {}
        articles.append({
            "title": str(item.get("title") or "")[:100],
            "source": source.get("name") if isinstance(source, dict) else "",
            "publishedAt": item.get("publishedAt") or "",
            "url": str(item.get("url") or "")[:140],
        })
    summary.append({"case": case, "totalArticles": data.get("totalArticles"), "count": len(articles), "articles": articles})
    time.sleep(0.5)

out_path = root / "data" / "gnews_quality_probe_result.json"
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(str(out_path))
