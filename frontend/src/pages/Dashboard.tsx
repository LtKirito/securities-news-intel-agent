import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, parseApiError } from "../api/client";

type ReportItem = {
  id: number;
  date: string;
  sector: string;
  title: string;
  html_path: string;
  json_path: string;
};

function todayText() {
  return new Date().toISOString().slice(0, 10);
}

export default function Dashboard() {
  const [apiKey, setApiKey] = useState("");
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [details, setDetails] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const today = todayText();
  const todayReports = useMemo(() => reports.filter(report => report.date === today), [reports, today]);
  const recentReports = reports.slice(0, 5);
  const trackingItems = details.flatMap(report => (report.tracking_items || []).map((item: any) => ({ ...item, date: report.date, sector: item.sector || report.sectors?.[0] }))).slice(0, 6);

  async function load() {
    setError("");
    try {
      const [status, list] = await Promise.all([
        api<{ configured: boolean }>("/api-keys/status"),
        api<ReportItem[]>("/reports"),
      ]);
      setApiKeyConfigured(status.configured);
      setReports(list);
      const detailRows = await Promise.all(list.slice(0, 5).map(report => api<any>(`/reports/${report.id}`).catch(() => null)));
      setDetails(detailRows.filter(Boolean));
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function saveApiKey() {
    setMessage("");
    setError("");
    try {
      await api("/api-keys", { method: "POST", body: JSON.stringify({ api_key: apiKey }) });
      setApiKeyConfigured(true);
      setApiKey("");
      setMessage("API Key 已保存。建议点击“测试连接”确认真实模型可用。");
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function testApiKey() {
    setMessage("");
    setError("");
    try {
      const result = await api<{ ok: boolean }>("/api-keys/test", { method: "POST" });
      setMessage(result.ok ? "连接测试通过，可关闭 Mock 模式使用真实模型生成日报。" : "连接测试未通过，请检查 API Key。")
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">工作台</p>
          <h1>今日产业情报总览</h1>
          <p>查看今日已生成日报、持续跟踪事项，并配置 SenseAudio API Key。</p>
        </div>
        <Link className="primary-link" to="/generate">进入日报生成</Link>
      </section>

      {error && <div className="notice warning">{error}</div>}
      {message && <div className="notice success">{message}</div>}

      <section className="dashboard-grid">
        <div className="panel api-card">
          <p className="eyebrow">模型状态</p>
          <h3>SenseAudio-S2</h3>
          <p className="muted">模型 ID：senseaudio-s2 · API 地址：https://api.senseaudio.cn</p>
          <div className={`status-pill ${apiKeyConfigured ? "ok" : ""}`}>{apiKeyConfigured ? "API Key 已配置" : "API Key 未配置"}</div>
          <label>更新 API Key<input type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder="输入你的 SenseAudio API Key" /></label>
          <div className="button-row">
            <button onClick={saveApiKey} disabled={apiKey.length < 8}>保存 Key</button>
            <button className="ghost" onClick={testApiKey} disabled={!apiKeyConfigured}>测试连接</button>
          </div>
        </div>

        <div className="panel today-panel">
          <div className="section-title-row">
            <div>
              <p className="eyebrow">今日日报</p>
              <h3>今日已生成 {todayReports.length} 份日报</h3>
            </div>
            <button className="ghost" onClick={load}>刷新</button>
          </div>
          {todayReports.length === 0 ? <div className="empty-state compact">今日还没有生成日报。你可以在“日报生成”中选择板块和配置，创建今日情报。</div> : <div className="report-card-list">{todayReports.map(report => <ReportSummaryCard key={report.id} report={report} details={details.find(item => item.date === report.date && item.sectors?.includes(report.sector))} />)}</div>}
        </div>
      </section>

      <section className="dashboard-grid lower">
        <div className="panel">
          <p className="eyebrow">持续跟踪</p>
          <h3>后续值得关注的验证点</h3>
          {trackingItems.length === 0 ? <div className="empty-state compact">生成日报后，这里会汇总跟踪事项。</div> : <div className="tracking-list">{trackingItems.map((item, index) => <div className="tracking-card" key={`${item.item}-${index}`}><span className="priority">{item.priority}</span><strong>{item.item}</strong><p>{item.reason}</p><small>{item.date} · {item.sector} · {(item.verification_metrics || []).join("、")}</small></div>)}</div>}
        </div>

        <div className="panel">
          <p className="eyebrow">最近日报</p>
          <h3>历史生成记录</h3>
          {recentReports.length === 0 ? <div className="empty-state compact">暂无历史日报。</div> : <div className="recent-list">{recentReports.map(report => <Link key={report.id} to="/reports"><span>{report.date}</span><strong>{report.sector}</strong><small>{report.title}</small></Link>)}</div>}
        </div>
      </section>
    </div>
  );
}

function ReportSummaryCard({ report, details }: { report: ReportItem; details?: any }) {
  const signals = details?.signals || [];
  const p0 = signals.filter((item: any) => item.rank === "P0").length;
  const p1 = signals.filter((item: any) => item.rank === "P1").length;
  const trend = details?.trends?.by_sector?.[report.sector]?.direction || "待验证";
  const sources = (details?.source_counts || []).reduce((sum: number, item: any) => sum + item.count, 0);
  const follow = (details?.tracking_items || [])[0]?.item || "等待后续公开来源验证";

  return <article className="daily-card"><div><p className="eyebrow">{report.date}</p><h4>{report.sector}日报</h4><p className="muted">补充关注：{follow}</p></div><div className="mini-metrics"><span>{trend}<small>趋势</small></span><span>{p0}<small>P0</small></span><span>{p1}<small>P1</small></span><span>{sources}<small>来源</small></span></div><Link to="/reports" className="text-link">查看日报</Link></article>;
}
