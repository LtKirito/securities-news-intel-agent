---
name: securities-priority-rating
description: 证券日报评分评级技能。在对话式生成日报时，用于把清洗后的新闻按五维评分生成 P0/P1/P2/Noise、情绪、评分解释、P0 影响链条和 P1 观察信号卡片；在 Workflow Runner 中对应 priority_rating 阶段。不得采集新闻或写最终 HTML。
---

# Securities Priority Rating

## 职责

只负责评分、评级、情绪和展示字段生成。不得采集新闻、去重新闻、写跨板块趋势总结或最终 HTML 日报。

## 输入

来自 `securities-news-dedup`：

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

同时读取：

- `config/rating_rules.json`
- `RULES.md`
- 用户指定板块和历史跟踪项

## 五维评分

每条新闻按 1-5 分评分：

- `sector_impact`：是否影响目标板块供需、政策、价格、订单、产能、竞争格局。
- `supply_chain_relevance`：是否涉及产业链节点、核心公司、终端需求、材料、设备、制造、价格、订单。
- `credibility`：是否来自一手来源、主流财经源或多源交叉验证。
- `timeliness`：是否处于滚动 24 小时窗口内，或虽早于 24 小时但在窗口内出现明确后续进展。
- `trend_value`：是否改变后续跟踪方向或形成连续信号。

## 评级规则

- P0：高可信、高边际变化、高趋势价值。必须影响板块预期或产业链判断。
- P1：值得重点跟踪，但缺少 P0 级确认；常见于产业链逻辑强但缺公告、订单、业绩验证。
- P2：有参考价值，但影响有限、验证不足或短期边际变化较弱。
- Noise：低可信、重复、旧闻、标题党、无产业事实或纯行情噪音。

## P0 时间窗口规则

- P0 候选优先来自滚动 24 小时窗口内的新信息。
- 早于 24 小时的事件，只有在滚动 24 小时内出现一手公告、权威媒体确认、订单/合同、产能、价格、客户、政策细则、财报/业绩等新增验证时，才可进入 P0 候选。
- 24 小时内的信息不能自动升级为 P0；仍必须满足高可信、强产业边际变化和趋势价值。
- 中午生成日报时，不得因为自然日信息不足而把 P0 判空；必须先检查过去 24 小时。

## P0 收紧规则

以下情况禁止直接评为 P0：

- 单一论坛、股吧、社区、自媒体来源。
- 只有股价异动，没有事实原因。
- 只有资金流、热度或 ETF 营销。
- 只是机构观点重复，没有新增事实。
- 来源正文无法访问或没有原始链接。
- 可信度不足，或缺少可验证来源。

P0 宁少勿滥。日报可以没有 P0。

## P0 必填展示字段

每条 P0 必须生成以下字段，供参考 HTML 同款卡片使用：

```json
{
  "rank": "P0",
  "sentiment": "利好|利空|中性|不确定",
  "sector": "板块名称",
  "title": "标题",
  "summary": "摘要",
  "score": {
    "sector_impact": 5,
    "supply_chain_relevance": 5,
    "credibility": 4,
    "timeliness": 5,
    "trend_value": 5
  },
  "p0_score_explanation": "逐项解释为什么达到 P0",
  "fact": "只写客观事实",
  "impact_chain": ["触发因素", "影响环节", "产业链传导", "板块/公司映射"],
  "trend_direction": {
    "short_term": "短期方向",
    "medium_term": "中期方向",
    "verification": "后续验证指标"
  },
  "impact_trend_explanation": "解释影响链条、趋势方向、证据和不确定性",
  "follow_up": "后续跟踪什么",
  "sources": []
}
```

目标是让用户一眼看懂：为什么是 P0、影响了什么链条、趋势方向是什么、后续看什么。

## P1 必填展示字段

每条 P1 必须生成 `watch_signal_view`，供参考 HTML 的观察信号卡片使用：

```json
{
  "rank": "P1",
  "watch_signal_view": {
    "signal_type": "中期产业链信号|政策信号|价格信号|订单信号|资金信号|区域信号|其他",
    "impact_direction": ["触发因素", "影响环节", "观察对象"],
    "current_strength": "为什么值得关注但暂定 P1",
    "upgrade_condition": "什么验证出现后可进入 P0 候选",
    "judgement_explanation": "证据强弱、为什么不是 P0、后续看什么"
  }
}
```

P1 的重点是解释“为什么值得跟踪，但为什么还不能升级”。

### P1 升级条件模板

`upgrade_condition` 必须具体，优先落在以下可验证类型，不要写“继续关注”这种空话：

- 公司公告确认：公告、合同、投资者关系纪要或交易所文件出现明确事实。
- 订单/合同落地：客户、金额、周期、交付范围或合作主体更明确。
- 价格连续变化：产品价格、原材料价格、供需报价出现连续验证。
- 产能/开工率验证：扩产、投产、稼动率、交付节奏有数据或公告支撑。
- 政策细则落地：政策从方向性表述进入补贴、准入、采购、审批等执行细则。
- 财报/业绩预告验证：收入、利润、订单、毛利率或资本开支出现印证。
- 多源交叉验证：至少两个 S/A 级来源独立指向同一事实。

## P2 和 Noise

- P2 保留标题、摘要、评分、情绪、来源即可，不写长判断。
- Noise 必须写 `noise_reason`。
- 纯行情、资金流、ETF 营销、社区热帖默认偏 P2 或 Noise。

## 对话模式输出

传给趋势阶段：

```json
{
  "date": "YYYY-MM-DD",
  "date_window": "覆盖窗口",
  "signals": [],
  "noise_items": [],
  "source_counts": []
}
```

## Runner 模式

- 输入 artifact：`deduped_news.json`
- 输出 artifact：`rated_signals.json`
- Schema：`schemas/rated_signals.schema.json`

## 禁止事项

- 不输出买卖建议、目标价、收益承诺、仓位建议。
- 不把模型推理写成“思考过程”。
- 不新增未采集事实。
- 不因想让日报好看而拔高等级。