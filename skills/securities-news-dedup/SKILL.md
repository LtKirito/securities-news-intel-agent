---
name: securities-news-dedup
description: 证券日报候选新闻清洗技能。在对话式生成日报时，用于把 source_research 得到的候选新闻去重、合并转载、过滤旧闻、预识别噪音，并保留可评级新闻池；在 Workflow Runner 中对应 news_dedup 阶段。不得做最终 P0/P1/P2 评级。
---

# Securities News Dedup

## 职责

只负责候选新闻清洗：去重、旧闻过滤、噪音预识别、跨板块归属和可信度线索。不得做最终 P0/P1/P2 评级，不生成日报卡片，不写趋势判断。

## 对话模式输入

来自 `securities-source-research` 的候选新闻结构：

```json
{
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "sectors": ["板块名称"],
  "candidates": [],
  "source_counts": []
}
```

可选读取：

- `website/data/daily-YYYY-MM-DD.json` 历史日报。
- `memory/YYYY-MM-DD.md` 历史运行摘要。
- 当前对话中用户补充的链接或新闻。

## 清洗流程

### 1. URL 和转载去重

- 相同 URL 只保留一条。
- 相同事件多源转载，合并为一条，使用 `merged_sources` 保存其他来源。
- 优先保留一手来源、主流财经源、正文更完整、发布时间更早或新增事实更明确的版本。
- 后续进展不是重复，应保留并标记 `is_follow_up`。

### 2. 旧闻过滤

- 与当前板块最近日报或记忆比对。
- 已写过且无新增事实 -> 移入 `removed_items`。
- 从“传闻/预期”升级为“公告/落地/数据确认” -> 保留。
- 如果无法确认是否旧闻，保留但标记 `uncertainty_note`。

### 3. 噪音预识别

优先移入 `noise_items`：

- 只有股价、资金流、热度，没有产业事实。
- 标题党、正文无实质内容。
- 来源弱且无交叉验证。
- 旧闻翻炒。
- 与目标板块无关。
- 纯 ETF 营销或单纯行情复盘。

### 4. 跨板块处理

- 一条新闻影响多个板块时，只保留一条。
- 主板块写入 `matched_sector`。
- 相关板块写入 `cross_sector_relevance`。
- 真正的共振点交给趋势阶段处理。

### 5. 可信度线索

本阶段只给线索，不下最终结论：

- `verified = true`：公告、交易所、监管、公司官网等一手来源。
- `credibility_adjustment = up`：多个 S/A 来源一致。
- `credibility_adjustment = down`：正文不可访问、来源弱、缺发布时间或摘要过短。

## 对话模式输出

传给评级阶段：

```json
{
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "kept_items": [],
  "removed_items": [],
  "noise_items": [],
  "source_counts": []
}
```

每条 `kept_items` 必须保留：`title`、`summary`、`published_at`、`source_name`、`source_tier`、`url`、`matched_sector`、`related_companies`、`merged_sources`、`verified`、`credibility_adjustment`、`access_issue`。

## Runner 模式

- 输入 artifact：`candidates.json`
- 输出 artifact：`deduped_news.json`
- Schema：`schemas/deduped_news.schema.json`
- 保存路径：`data/users/{user_id}/reports/{date}/run/artifacts/deduped_news.json`

## 禁止事项

- 不做最终 P0/P1/P2 评级。
- 不写最终情绪判断。
- 不输出买卖建议、目标价、收益承诺、仓位建议。
- 不新增未采集到的事实。
- 不把 Noise 改写成新闻事实。