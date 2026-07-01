# website/data/

每日 JSON 日报存储目录。

命名格式：`daily-YYYY-MM-DD.json`

Schema 定义：`templates/daily_report.schema.json`

此目录下的 JSON 文件由 Agent 在每次运行时自动生成，用于：
- 后续运行时读取前一日记忆。
- 网页化展示数据源。
- 长期趋势分析。
