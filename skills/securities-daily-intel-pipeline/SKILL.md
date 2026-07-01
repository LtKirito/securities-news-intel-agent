---
name: securities-daily-intel-pipeline
description: 证券日报总控技能，WorkBuddy 对话式日报生成的唯一入口。用户在对话中说「基于人设文件和技能文件为我生成今日的某某板块日报」「帮我看一下今天XX板块」「生成今日日报」「做一份XX日报」时必须触发。也支持 Workflow Runner 按阶段执行。普通股票问答、单只股票分析、一般投资聊天不要触发。
---

# Securities Daily Intel Pipeline

## 对话模式（WorkBuddy 首选路径）

用户在 WorkBuddy 中说出「基于人设文件和技能文件为我生成今日的XX板块日报」等类似意图时，按以下流程执行：

### 执行流程

1. **读取人设与规则**：读取 IDENTITY.md、RULES.md、MEMORY.md、SOUL.md，了解 Agent 身份、边界和默认规则。
2. **读取参考样式**：读取参考日报 HTML（例如 outputs/securities-news-digest-2026-06-25-p1-review.html），确保输出样式一致。
3. **读取基础配置**：读取 config/topics.json、config/sources.json、config/rating_rules.json。
4. **明确用户需求**：用户指定的板块名称（支持任意证券产业链板块，不限于 PCB/存储芯片）、日期、覆盖窗口；未指定时覆盖窗口固定为滚动 24 小时。
5. **按流水线生产**：
   - 搜索并采集公开网页新闻（source_research 阶段）
   - 去重、旧闻过滤、噪音预识别（news_dedup 阶段）
   - 五维评分、P0/P1/P2/Noise 评级、情绪标注（priority_rating 阶段）
   - 趋势判断、共振点、分歧点、跟踪清单（trend_analysis 阶段）
   - 产出 HTML 日报 + JSON 数据 + 运行摘要（report_format 阶段）

### 对话模式要点

- 用户只需要指定板块和日期，其余由 Agent 自主完成。
- 默认覆盖窗口为滚动 24 小时；中午生成日报时也要回看昨晚、盘后和海外夜间信息，不能只按自然日截至当前时间判断。
- 每个阶段可以不走 JSON artifact 文件，直接传递结构化数据。
- 最终产出必须写入文件：`outputs/securities-news-digest-YYYY-MM-DD.html`。
- 同时产出 `website/data/daily-YYYY-MM-DD.json` 和 `memory/YYYY-MM-DD.md`。
- 操作后向用户简要汇报结果：今日覆盖板块、P0/P1/P2/Noise 数量、核心结论摘要。
- 不要向用户展示内部阶段流程细节，只说最终结果和发现。

### 对话模式降级策略

真实对话里优先完成可用日报，不要因为信息不足卡住：

- 如果公开搜索结果少于 8 条，必须扩大关键词并进行第二轮采集。
- 如果第二轮后仍少于 5 条候选，允许生成“轻量日报”，但必须在核心结论和运行摘要中说明“今日公开信息较少”。
- 如果 P0 为空，不要硬凑 P0；日报可以从 P1/P2 和趋势待验证开始。
- 如果 P1/P2 也不足，报告重点转为“公开信息覆盖情况、噪音过滤、后续应跟踪的验证指标”。
- 如果无法联网或公开网页不可访问，应要求用户提供链接或素材；若用户已给素材，则基于用户素材生成，并标注来源限制。
- 任何降级都不能突破公开来源、禁止投资建议和 P0 稀缺规则。

## 流水线阶段（两种模式共用）

1. `securities-source-research` — 公开来源采集，输出候选新闻和来源统计。
2. `securities-news-dedup` — 去重、旧闻过滤、噪音预识别、跨板块归属。
3. `securities-priority-rating` — 五维评分、P0/P1/P2/Noise 评级、情绪标注。
4. `securities-trend-analysis` — 板块趋势方向、产业链共振点、分歧点、跟踪清单。
5. `securities-report-format` — HTML 日报渲染、JSON 结构化数据、运行摘要。

## Workflow Runner 协议（后台/测试模式）

每个阶段按统一协议执行：

1. 读取总控技能。
2. 读取当前阶段技能。
3. 读取基础配置：`config/topics.json`、`config/sources.json`、`config/rating_rules.json`、`config/output_schema.json`。
4. 读取当前阶段 JSON Schema（`schemas/*.json`）。
5. 合并用户 overlay：`sector_configs`、`source_preferences`、`rating_overlay`、`display_preferences`、`schedule_config`。
6. 读取当前阶段输入 artifact。
7. 调用模型，只生成当前阶段 JSON。
8. 按 schema 校验。
9. 如校验失败，只修复 JSON 结构/字段，不重新发散生成；最多 2 次。
10. 保存输出 artifact。
11. 进入下一阶段。

Runner 输入：

```json
{
  "run_id": "唯一运行 ID",
  "user_id": "用户标识",
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "sector_configs": [],
  "source_preferences": {},
  "rating_overlay": {},
  "display_preferences": {},
  "schedule_config": {},
  "start_stage": "source_research"
}
```

`sector_configs` 驱动具体板块，不限于 PCB/存储芯片。允许任意证券产业板块。

## 不可覆盖规则

- 只处理公开网页信息。
- 不采集非公开、付费墙后、内网、本地文件、localhost、云元数据地址。
- 用户 URL 必须先安全校验。
- 不输出买卖建议、目标价、收益承诺、仓位建议。
- 每条入选新闻必须保留来源名称和 URL。
- 事实、判断、不确定性必须分开。
- 单一论坛、股吧、社区、自媒体来源不能独立支撑 P0。
- P0 必须稀缺，不能为填充日报而拔高。