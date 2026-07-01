type Signal = {
  rank: string;
  sentiment?: string;
  title: string;
  summary?: string;
  sector?: string;
  score?: Record<string, number>;
  fact?: string;
  judgement?: string;
  why_it_matters?: string;
  impact_chain?: string[];
  trend_direction?: Record<string, string>;
  impact_trend_explanation?: string;
  p0_score_explanation?: string;
  watch_signal_view?: {
    signal_type?: string;
    impact_direction?: string[];
    current_strength?: string;
    upgrade_condition?: string;
    judgement_explanation?: string;
  };
  follow_up?: string;
  sources?: { name: string; url: string; source_tier: string }[];
};

type Report = {
  title?: string;
  date?: string;
  sectors?: string[];
  conclusions?: string[];
  summary?: string;
  signals?: Signal[];
  trends?: any;
  tracking_items?: any[];
  source_counts?: { name: string; tier: string; count: number }[];
  disclaimer?: string;
  generation_mode?: { mode?: string; label?: string; must_disclose_limitations?: boolean };
  quality_gate?: { passed?: boolean; failures?: { metric?: string; reason?: string; actual?: number; threshold?: number }[] };
  quality_warnings?: string[];
  suggested_fixes?: string[];
};

function countRank(report: Report, rank: string) {
  return (report.signals || []).filter(signal => signal.rank === rank).length;
}

function trendText(report: Report) {
  const firstSector = report.sectors?.[0];
  if (!firstSector) return "待验证";
  return report.trends?.by_sector?.[firstSector]?.direction || "待验证";
}

function scoreLabel(key: string) {
  const labels: Record<string, string> = {
    sector_impact: "板块影响",
    supply_chain_relevance: "产业链",
    credibility: "可信度",
    timeliness: "时效性",
    trend_value: "趋势价值",
    total: "总分",
  };
  return labels[key] || key;
}

function SignalCard({ signal }: { signal: Signal }) {
  const isPositive = signal.sentiment === "利好";
  const isNegative = signal.sentiment === "利空";
  const isP2 = signal.rank === "P2";
  if (isP2) {
    return (
      <article className={`signal-card rank-p2 compact-p2`}>
        <div className="signal-head">
          <span className="rank-badge">P2</span>
          {signal.sentiment && <span className={`sentiment ${isPositive ? "red" : isNegative ? "green" : ""}`}>{signal.sentiment}</span>}
          {signal.sector && <span className="muted-chip">{signal.sector}</span>}
          {signal.score?.total != null && <span className="score-num">{signal.score.total}分</span>}
        </div>
        <h4>{signal.title}</h4>
        {signal.summary && <p className="lead-text compact">{signal.summary}</p>}
        {signal.follow_up && <p className="follow-up"><strong>后续：</strong>{signal.follow_up}</p>}
        {signal.sources?.length ? <div className="source-list compact">{signal.sources.slice(0, 2).map(source => <a key={source.url} href={source.url} target="_blank">{source.name}</a>)}</div> : null}
      </article>
    );
  }
  return (
    <article className={`signal-card rank-${signal.rank.toLowerCase()}`}>
      <div className="signal-head">
        <span className="rank-badge">{signal.rank}</span>
        {signal.sentiment && <span className={`sentiment ${isPositive ? "red" : isNegative ? "green" : ""}`}>{signal.sentiment}</span>}
        {signal.sector && <span className="muted-chip">{signal.sector}</span>}
      </div>
      <h4>{signal.title}</h4>
      {(signal.rank === "P0" || signal.rank === "P1") && signal.summary && <p className="lead-text">{signal.summary}</p>}
      {signal.score && (
        <div className="score-strip">
          {Object.entries(signal.score).map(([key, value]) => <span key={key}>{scoreLabel(key)} {value}</span>)}
          {signal.p0_score_explanation && <details><summary>评分解释</summary><p>{signal.p0_score_explanation}</p></details>}
        </div>
      )}
      {signal.rank !== "P2" && signal.fact && <section><strong>事实</strong><p>{signal.fact}</p></section>}
      {signal.rank !== "P2" && signal.impact_chain && signal.impact_chain.length > 0 && (
        <section>
          <strong>影响链条</strong>
          <div className="chain-row">{signal.impact_chain.map((node, index) => <span key={node}>{node}{index < signal.impact_chain!.length - 1 && <b>→</b>}</span>)}</div>
        </section>
      )}
      {signal.trend_direction && Object.keys(signal.trend_direction).length > 0 && (
        <section className="mini-grid">
          {Object.entries(signal.trend_direction).map(([key, value]) => <div key={key}><span>{key}</span><p>{value}</p></div>)}
        </section>
      )}
      {signal.impact_trend_explanation && <details><summary>影响链条与趋势解释</summary><p>{signal.impact_trend_explanation}</p></details>}
      {signal.watch_signal_view && (
        <section className="watch-box">
          <strong>观察信号</strong>
          {signal.watch_signal_view.signal_type && <p><span>信号性质：</span>{signal.watch_signal_view.signal_type}</p>}
          {signal.watch_signal_view.impact_direction?.length ? <p><span>影响方向：</span>{signal.watch_signal_view.impact_direction.join(" → ")}</p> : null}
          {signal.watch_signal_view.current_strength && <p><span>当前强度：</span>{signal.watch_signal_view.current_strength}</p>}
          {signal.watch_signal_view.upgrade_condition && <p><span>升级条件：</span>{signal.watch_signal_view.upgrade_condition}</p>}
          {signal.watch_signal_view.judgement_explanation && <details><summary>判断依据</summary><p>{signal.watch_signal_view.judgement_explanation}</p></details>}
        </section>
      )}
      {signal.follow_up && <p className="follow-up"><strong>后续跟踪：</strong>{signal.follow_up}</p>}
      {signal.sources?.length ? <div className="source-list">{signal.sources.map(source => <a key={source.url} href={source.url} target="_blank">{source.name} · {source.source_tier}</a>)}</div> : null}
    </article>
  );
}

export default function ReportViewer({ report }: { report: Report | null }) {
  if (!report) {
    return <div className="empty-state">生成完成后，日报会直接显示在这里。</div>;
  }
  const p0 = countRank(report, "P0");
  const p1 = countRank(report, "P1");
  const sources = (report.source_counts || []).reduce((sum, item) => sum + item.count, 0);
  return (
    <div className="report-viewer">
      <section className="report-hero">
        <div>
          <p className="eyebrow">{report.date} · {(report.sectors || []).join(" / ")}</p>
          <h2>{report.title || "证券产业新闻情报日报"}</h2>
          {report.generation_mode?.label && <span className={`mode-badge ${report.generation_mode.mode || ""}`}>{report.generation_mode.label}</span>}
          {report.summary && <p>{report.summary}</p>}
        </div>
        <div className="metric-row">
          <div><strong>{trendText(report)}</strong><span>趋势</span></div>
          <div><strong>{p0}</strong><span>P0</span></div>
          <div><strong>{p1}</strong><span>P1</span></div>
          <div><strong>{sources}</strong><span>来源</span></div>
        </div>
      </section>

      {(report.quality_warnings?.length || report.suggested_fixes?.length) ? <section className="content-block quality-warning-block"><h3>采集质量提示</h3>{report.quality_warnings?.length ? <ul>{report.quality_warnings.map(item => <li key={item}>{item}</li>)}</ul> : null}{report.suggested_fixes?.length ? <details open><summary>建议怎么解决</summary><ul>{report.suggested_fixes.map(item => <li key={item}>{item}</li>)}</ul></details> : null}</section> : null}

      {report.conclusions?.length ? <section className="content-block"><h3>今日结论</h3><ul>{report.conclusions.map(item => <li key={item}>{item}</li>)}</ul></section> : null}

      <section className="content-block">
        <h3>重点信号</h3>
        <div className="signal-list">
          {(report.signals || []).map(signal => <SignalCard key={`${signal.rank}-${signal.title}`} signal={signal} />)}
        </div>
      </section>

      {report.trends?.by_sector && <section className="content-block"><h3>趋势判断</h3><div className="trend-grid">{Object.entries(report.trends.by_sector).map(([sector, trend]: [string, any]) => <div key={sector} className="trend-card"><strong>{sector} · {trend.direction}</strong><p>{trend.summary}</p><span>验证指标：{(trend.verification_metrics || []).join("、") || "待补充"}</span></div>)}</div></section>}

      {report.tracking_items?.length ? <section className="content-block"><h3>持续跟踪</h3><div className="tracking-list">{report.tracking_items.map((item: any) => <div key={`${item.sector}-${item.item}`} className="tracking-card"><span className="priority">{item.priority}</span><strong>{item.item}</strong><p>{item.reason}</p><small>{item.sector} · {(item.verification_metrics || []).join("、")}</small></div>)}</div></section> : null}

      {report.source_counts?.length ? <section className="content-block"><h3>来源统计</h3><div className="source-counts">{report.source_counts.map(source => <span key={`${source.name}-${source.tier}`}>{source.name} · {source.tier} · {source.count}</span>)}</div></section> : null}

      {report.disclaimer && <p className="disclaimer">{report.disclaimer}</p>}
    </div>
  );
}
