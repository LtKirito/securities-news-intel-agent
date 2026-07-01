---
name: securities-report-format
description: 证券日报 HTML 输出技能。在对话式生成日报时，必须用参考文件 outputs/securities-news-digest-2026-06-25-p1-review.html 的版式生成同款日报 HTML，并同时保存 JSON 数据和运行摘要；在 Workflow Runner 中对应 report_format 阶段。不得重新采集、重评或新增事实。
---

# Securities Report Format

## 职责

只负责把已评级信号和趋势判断渲染为：

1. HTML 日报。
2. JSON 结构化数据。
3. 每日运行摘要。

不得重新采集新闻，不得重新评级，不得新增趋势事实。

## 对话模式输入

来自前置阶段：

```json
{
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "sectors": ["板块名称"],
  "signals": [],
  "noise_items": [],
  "trends": {},
  "tracking_items": [],
  "source_counts": []
}
```

必须读取参考日报：

```text
outputs/securities-news-digest-2026-06-25-p1-review.html
```

如果用户另给参考 HTML，以用户给的为准。

## 输出路径

对话模式默认输出：

```text
outputs/securities-news-digest-YYYY-MM-DD.html
website/data/daily-YYYY-MM-DD.json
memory/YYYY-MM-DD.md
```

如果同一天同板块可能重复生成，文件名可加板块：

```text
outputs/securities-news-digest-YYYY-MM-DD-{sector_slug}.html
website/data/daily-YYYY-MM-DD-{sector_slug}.json
```

## HTML 版式要求

必须与参考日报保持同款结构和视觉语言：

- 白底，正文最大宽度约 860px。
- 标题：`证券产业新闻情报日报 | YYYY-MM-DD`。
- meta 行：覆盖窗口、来源摘要；默认展示为“滚动24小时：起止时间”，不要写成单纯“今日截至当前”。
- 区块顺序固定：
  1. 今日核心结论
  2. P0 关键新闻
  3. P1 重点新闻
  4. P2 · 一般关注
  5. 趋势判断
  6. 产业链共振点
  7. 分歧点
  8. 噪音过滤
  9. 后续跟踪清单
  10. 信息来源
  11. 免责声明

使用参考 HTML 的核心类名和结构：

- `.signal-card P0|P1|P2`
- `.rank P0|P1|P2`
- `.sentiment-tag 利好|利空|中性|不确定`
- `.score-row`
- `.score-bar`
- `.score-explain`
- `.chain-list`、`.chain-node`、`.chain-arrow`
- `.trend-direction`、`.trend-row`
- `.watch-signal`、`.watch-row`、`.watch-chain`、`.watch-node`、`.watch-arrow`
- `.explain-details`
- `.trend-section`、`.trend-card`
- `.source-summary`、`.source-badge`
- `.disclaimer`

不要改成普通 Markdown 或简单表格。最终必须是完整可打开的 HTML 文件。

### HTML 一次成型自检

生成 HTML 后必须自检并修正：

- 文件包含完整 `<!DOCTYPE html>`、`<html>`、`<head>`、`<style>`、`<body>`。
- 标题、meta 行、11 个日报区块完整存在；没有 P0 时也保留“P0 关键新闻”区块并说明“今日无 P0 级信号”。
- CSS 使用参考日报的浅色卡片风格，不输出 Markdown。
- 所有来源链接必须是 `<a href="...">来源名</a>`，没有 URL 的新闻不得进入 P0/P1/P2。
- P0 卡片必须出现评分解释、事实、影响链条、趋势方向、后续跟踪和来源。
- P1 卡片必须出现观察信号卡片、当前强度、升级条件、判断依据和来源。
- 免责声明必须在页面底部。
- 生成后读回文件，检查关键字：`今日核心结论`、`P1 重点新闻`、`趋势判断`、`免责声明`。

## P0 展示规则

每条 P0 卡片必须包含：

1. 顶部标签：P0、情绪、板块、可信度。
2. 标题和摘要。
3. 五维评分条。
4. `评分解释` 折叠框，使用 `p0_score_explanation`。
5. `事实`，使用 `fact`。
6. `影响链条`，使用 `impact_chain` 渲染为链式节点。
7. `趋势方向`，使用 `trend_direction.short_term`、`medium_term`、`verification` 渲染为三行。
8. `展开影响链条与趋势解释` 折叠框，使用 `impact_trend_explanation`。
9. `后续跟踪`，使用 `follow_up`。
10. 来源链接。

P0 卡片目标：让用户快速理解为什么是 P0、影响了什么链条、趋势方向是什么、后续看什么验证。

## P1 展示规则

每条 P1 卡片必须包含：

1. 顶部标签：P1、情绪、板块。
2. 标题和摘要。
3. 五维评分条。
4. `事实`。
5. `判断` 区域必须使用 `watch_signal_view` 渲染观察信号卡片：
   - 信号性质：`signal_type`
   - 影响方向：`impact_direction` 渲染为链式节点
   - 当前强度：`current_strength`
   - 升级条件：`upgrade_condition`
6. `展开判断依据` 折叠框，使用 `watch_signal_view.judgement_explanation`。
7. 来源链接。

P1 卡片目标：让用户理解为什么值得跟踪、为什么还不能升级为 P0。

## P2 展示规则

P2 使用与参考日报一致的轻量卡片：

- P2 标签。
- 情绪。
- 板块。
- 标题。
- 摘要。
- 五维评分。
- 来源链接。

不要写长篇判断。

## 趋势、噪音和来源

### 趋势判断

使用 `.trend-section` 和 `.trend-card`，按板块动态渲染。每个趋势卡片用一段话说明：

- 今日趋势方向。
- 核心驱动变量。
- 短期和中期验证点。
- 不确定性。

### 产业链共振点

使用列表展示 2-5 条，必须来自已评级信号。

### 分歧点

如果没有明显分歧，可以写“暂无明显分歧，主要风险在后续验证不足”。不要硬凑。

### 噪音过滤

每条噪音显示：

- 新闻/来源/主题。
- 过滤原因。

### 信息来源

使用 `.source-summary` 和 `.source-badge` 展示来源名称、类型、收录数量。

## JSON 输出

`website/data/daily-YYYY-MM-DD.json` 至少包含：

```json
{
  "date": "YYYY-MM-DD",
  "title": "证券产业新闻情报日报",
  "coverage": "覆盖窗口",
  "sectors": [],
  "conclusions": [],
  "signals": [],
  "noise_items": [],
  "trends": {},
  "tracking_items": [],
  "source_counts": [],
  "disclaimer": "本日报仅为公开信息整理和研究参考，不构成任何投资建议。"
}
```

必须完整保留 P0/P1 展示字段，方便后续复盘。

## 运行摘要

写入 `memory/YYYY-MM-DD.md`：

```markdown
# 运行摘要 | YYYY-MM-DD
- 板块：
- 覆盖窗口：
- P0 新闻数：
- P1 新闻数：
- P2 新闻数：
- Noise 过滤数：
- 今日核心主题：
- 新增跟踪项：
- 输出文件：
```

## 合规检查

最终输出前确认：

- 每条入选新闻都有来源名称和 URL。
- P0 含 `fact`、`impact_chain`、`trend_direction`、`impact_trend_explanation`、`p0_score_explanation`、`follow_up`、`sources`。
- P1 含完整 `watch_signal_view`。
- 事实、判断、不确定性分开。
- 免责声明存在。
- 不包含买卖建议、目标价、收益承诺、仓位建议。
- 单一社区/股吧/论坛/自媒体来源没有独立支撑 P0。

## Runner 模式

- 输入 artifact：`rated_signals.json`、`trends.json`、`source_counts.json`
- 输出 artifact：`report.html`、`report.json`、`run_meta.json`
- Schema：`schemas/run_meta.schema.json`，报告结构参考 `config/output_schema.json`。

Runner 模式可以使用用户隔离路径；对话模式优先使用本项目 `outputs/`、`website/data/`、`memory/`。