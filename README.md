# Securities News Intel Agent

证券产业新闻情报 Agent，面向个人用户提供任意指定证券产业板块的公开新闻抓取、去噪、评级、趋势判断和每日摘要。支持 WorkBuddy 对话式生成日报，也支持后台 Workflow Runner 分阶段执行。

## 默认任务

- 对话式场景按需运行：用户说“基于人设文件和技能文件生成今日某某板块日报”即可触发。
- 自动化场景可每日 18:30 固定运行一次。
- 只抓取公开网页内容。
- 板块由用户指定或由 `config/topics.json` / `sector_configs` 配置。
- 示例主题：PCB、存储芯片、机器人、医药、消费电子、新能源车、低空经济、半导体设备、先进封装、AI 算力等。
- 输出 HTML 日报和 JSON 结构化记忆。
- HTML 日报形式默认参考：`outputs/securities-news-digest-2026-06-25-p1-review.html`。

## 输出文件

- HTML 日报：`outputs/securities-news-digest-YYYY-MM-DD.html`
- JSON 数据：`website/data/daily-YYYY-MM-DD.json`
- 运行摘要：`memory/YYYY-MM-DD.md`

如果同一天生成多个板块日报，文件名可增加板块 slug。

## 核心流程

1. 读取人设文件、规则文件、技能文件和基础配置。
2. 按用户指定板块搜索公开财经、公告、产业和主流新闻来源。
3. 提取候选新闻，保留标题、摘要、发布时间、来源名称和来源链接。
4. 去重、识别旧闻翻炒、过滤标题党和弱来源噪音。
5. 使用 `config/rating_rules.json` 进行 P0/P1/P2/Noise 评级。
6. 生成 P0 影响链条、趋势方向、评分解释和后续跟踪。
7. 生成 P1 观察信号卡片、当前强度、升级条件和判断依据。
8. 判断板块趋势、产业链共振点、分歧点和跟踪清单。
9. 按参考 HTML 风格生成日报和 JSON 数据。
10. 写入 `memory/YYYY-MM-DD.md` 作为每日运行摘要。

## 合规边界

本 Agent 只做公开信息整理和研究参考，不构成投资建议。禁止输出买入、卖出、加仓、减仓、目标价、收益承诺、仓位建议等表达。
