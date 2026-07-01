---
name: securities-trend-analysis
description: 证券日报趋势分析技能。在对话式生成日报时，用于根据已评级 P0/P1/P2 信号总结目标板块趋势、产业链共振点、分歧点和后续跟踪清单；在 Workflow Runner 中对应 trend_analysis 阶段。不得新增未采集事实、不得重评新闻等级、不得写最终 HTML。
---

# Securities Trend Analysis

## 职责

只负责趋势、共振点、分歧点和跟踪清单。不得采集新闻，不重评 P0/P1/P2，不写最终 HTML 日报。

## 输入

来自 `securities-priority-rating`：

```json
{
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "signals": [],
  "noise_items": [],
  "source_counts": []
}
```

可选读取历史：

- `website/data/daily-YYYY-MM-DD.json`
- `memory/YYYY-MM-DD.md`
- 上次日报中的 `tracking_items`

## 趋势分析流程

### 1. 按板块归组

- 按 `signals[].sector` 分组。
- 每个板块按 P0、P1、P2 排序。
- Noise 只用于解释噪音质量，不进入趋势主线。
- 如果新闻同时影响多个板块，用 `cross_sector_links` 引用，不复制事实。

### 2. 板块趋势判断

每个板块输出一段清晰趋势判断：

- 今天主线是什么。
- 哪些变量构成边际变化。
- 短期偏情绪、偏基本面还是待验证。
- 中期看什么验证指标。
- 哪些风险或分歧会削弱结论。

趋势方向是信息层面的产业趋势，不是股价预测。

### 弱信号趋势写法

当日信息不足或强信号不足时，趋势要克制：

- 没有 P0 时，不得写“明确走强”“趋势确认”“拐点已至”。
- 只有 P1/P2 时，优先使用“待验证”“边际关注”“分歧较大”“观察信号增多”等表述。
- 趋势判断必须至少引用 1 条 P0/P1 标题作为依据；如果没有 P0/P1，明确写“缺少高等级信号支撑”。
- 如果公开信息少于 5 条，趋势卡片必须说明覆盖不足，不得给出强判断。
- 分歧点可以为空，但风险或待验证项不能省略。

### 3. 产业链共振点

从已评级信号中提取共振：

- 同一需求驱动影响多个环节。
- 上游供给瓶颈与下游需求同时出现。
- 政策、订单、价格、技术变量同时影响多个板块。
- 多个 P0/P1 指向同一验证指标。

共振点必须具体，不写“市场热度提升”这类泛句。

### 4. 分歧点

识别：

- 同一板块内强事实和弱来源信号冲突。
- 热度很高但公告/订单/业绩验证不足。
- 价格涨但需求端证据不足。
- 政策方向明确但落地节奏不明。

### 5. 后续跟踪清单

每条跟踪项包含：

- `item`：要跟踪什么。
- `priority`：高/中/低。
- `reason`：为什么要跟踪。
- `verification_metrics`：验证指标。
- `related_signal_titles`：关联新闻标题。

P0 必须生成跟踪项；可能升级为 P0 的 P1 也必须生成跟踪项。

## 对话模式输出

传给报告阶段：

```json
{
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "trends": {
    "by_sector": {},
    "resonance_points": [],
    "divergence_points": []
  },
  "tracking_items": []
}
```

## Runner 模式

- 输入 artifact：`rated_signals.json`
- 输出 artifact：`trends.json`
- Schema：`schemas/trends.schema.json`

## 写作要求

- 中文输出。
- 先结论，后原因。
- 保留不确定性，不确定时写“待验证”。
- 不新增未采集事实。
- 不输出买卖建议、目标价、收益承诺、仓位建议。
- 趋势判断要能直接放进参考 HTML 的“趋势判断”区域。