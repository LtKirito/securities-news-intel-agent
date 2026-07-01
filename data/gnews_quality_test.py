import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env_path = root / "backend" / ".env"
api_key = ""
for line in env_path.read_text(encoding="utf-8").splitlines():
    if line.strip().startswith("GNEWS_API_KEY="):
        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not api_key:
    raise SystemExit("GNEWS_API_KEY not found in backend/.env")

queries = [
    "机器人产业链 人形机器人 订单",
    "机器人产业链 减速器 上市公司",
    "埃斯顿 机器人 订单",
    "汇川技术 伺服系统 机器人",
    "绿的谐波 减速器 产能",
    "存储芯片 DRAM 价格",
    "HBM 存储芯片 订单",
    "长江存储 NAND",
    "存储芯片 上市公司 业绩",
]
finance_markers = ["证券", "财经", "财联社", "东方财富", "同花顺", "公告", "交易所", "上市公司", "公司", "业绩", "订单", "产能", "价格", "机器人", "存储", "DRAM", "HBM", "NAND"]
low_quality_markers = ["知乎", "贴吧", "论坛", "博客", "CSDN", "招聘", "百科"]

summary = []
for query in queries:
    params = {
        "q": query,
        "lang": "zh",
        "country": "cn",
        "max": "10",
        "apikey": api_key,
    }
    url = "https://gnews.io/api/v4/search?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")[:500]
        summary.append({"query": query, "error": f"HTTP {exc.code}: {body}"})
        continue
    except Exception as exc:
        summary.append({"query": query, "error": str(exc)})
        continue

    articles = data.get("articles") or []
    valid = 0
    low_quality = 0
    with_date = 0
    rows = []
    for item in articles:
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        description = str(item.get("description") or "")
        content = str(item.get("content") or "")
        published_at = str(item.get("publishedAt") or "")
        source = item.get("source") or {}
        source_name = str(source.get("name") or "") if isinstance(source, dict) else ""
        text = f"{title} {description} {content} {url} {source_name}"
        finance_like = any(marker.lower() in text.lower() for marker in finance_markers)
        low_like = any(marker.lower() in text.lower() for marker in low_quality_markers)
        if published_at:
            with_date += 1
        if finance_like and url and title:
            valid += 1
        if low_like:
            low_quality += 1
        rows.append({
            "title": title[:100],
            "url": url[:140],
            "source_name": source_name,
            "published_at": published_at,
            "description_len": len(description),
            "content_len": len(content),
            "finance_like": finance_like,
            "low_quality_marker": low_like,
        })
    summary.append({
        "query": query,
        "total_articles": data.get("totalArticles"),
        "result_count": len(articles),
        "valid_finance_like": valid,
        "with_date": with_date,
        "low_quality_count": low_quality,
        "articles": rows,
    })
    time.sleep(0.6)

out_path = root / "data" / "gnews_quality_result.json"
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(str(out_path))
