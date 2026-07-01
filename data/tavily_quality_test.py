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
    "机器人产业链 减速器 上市公司 最新",
    "埃斯顿 机器人 订单 最新",
    "汇川技术 伺服系统 机器人 最新",
    "绿的谐波 减速器 产能 最新",
    "存储芯片 DRAM 价格 最新",
    "HBM 存储芯片 订单 最新",
    "长江存储 NAND 最新",
    "存储芯片 上市公司 业绩 最新",
]
finance_markers = ["证券", "财经", "财联社", "东方财富", "同花顺", "公告", "交易所", "上市公司", "公司", "业绩", "订单", "产能", "价格", "机器人", "存储", "DRAM", "HBM", "NAND"]
low_quality_markers = ["知乎", "贴吧", "论坛", "博客", "CSDN", "招聘", "百科"]

summary = []
for query in queries:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False,
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
        body = exc.read().decode("utf-8", errors="ignore")[:500]
        summary.append({"query": query, "error": f"HTTP {exc.code}: {body}"})
        continue
    except Exception as exc:
        summary.append({"query": query, "error": str(exc)})
        continue

    results = data.get("results") or []
    valid = 0
    low_quality = 0
    rows = []
    for item in results:
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        content = str(item.get("content") or "")
        published = item.get("published_date") or item.get("publishedDate") or ""
        text = f"{title} {content} {url}"
        finance_like = any(marker.lower() in text.lower() for marker in finance_markers)
        low_like = any(marker.lower() in text.lower() for marker in low_quality_markers)
        if finance_like and url and (title or content):
            valid += 1
        if low_like:
            low_quality += 1
        rows.append({
            "title": title[:90],
            "url": url[:120],
            "has_content": bool(content),
            "content_len": len(content),
            "published_date": published,
            "score": item.get("score"),
            "finance_like": finance_like,
            "low_quality_marker": low_like,
        })
    summary.append({
        "query": query,
        "result_count": len(results),
        "valid_finance_like": valid,
        "low_quality_count": low_quality,
        "results": rows,
    })
    time.sleep(0.4)

out_path = root / "data" / "tavily_quality_result.json"
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(str(out_path))
