import { useEffect, useMemo, useState } from "react";
import ReportChatPanel from "../components/ReportChatPanel";
import ReportViewer from "../components/ReportViewer";
import { api, parseApiError } from "../api/client";

type ReportItem = {
  id: number;
  run_id: string;
  date: string;
  sector: string;
  title: string;
  html_path: string;
  json_path: string;
  created_at?: string;
};

export default function ReportHistory() {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [dateFilter, setDateFilter] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [error, setError] = useState("");

  const filtered = useMemo(() => reports.filter(report => (!dateFilter || report.date.includes(dateFilter)) && (!sectorFilter || report.sector.includes(sectorFilter))), [reports, dateFilter, sectorFilter]);

  async function load() {
    setError("");
    try {
      const list = await api<ReportItem[]>("/reports");
      setReports(list);
      if (!selected && list.length) open(list[0]);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function open(report: ReportItem) {
    setSelected(report);
    setError("");
    try {
      setDetail(await api(`/reports/${report.id}`));
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="history-page">
      <section className="hero-panel compact-hero">
        <div>
          <p className="eyebrow">历史日报</p>
          <h1>按日期和板块复盘历史情报</h1>
          <p>打开任意日报后，可基于当前日报直接向 AI 提问。</p>
        </div>
        <button className="ghost" onClick={load}>刷新列表</button>
      </section>

      {error && <div className="notice warning">{error}</div>}

      <section className="history-grid">
        <aside className="panel report-index">
          <div className="form-grid two compact-inputs">
            <label>日期筛选<input value={dateFilter} onChange={event => setDateFilter(event.target.value)} placeholder="2026-06" /></label>
            <label>板块筛选<input value={sectorFilter} onChange={event => setSectorFilter(event.target.value)} placeholder="存储" /></label>
          </div>
          <div className="history-list">
            {filtered.length === 0 ? <div className="empty-state compact">暂无匹配日报。</div> : filtered.map(report => <button key={report.id} className={`history-item ${selected?.id === report.id ? "selected" : ""}`} onClick={() => open(report)}><span>{report.date} · {report.created_at ? new Date(report.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Shanghai" }) : "--"}</span><strong>{report.sector}</strong><small>{report.title}</small></button>)}
          </div>
        </aside>

        <div className="history-detail-stack">
          <div className="panel report-panel"><ReportViewer report={detail} /></div>
          <ReportChatPanel report={detail} date={selected?.date} sector={selected?.sector} />
        </div>
      </section>
    </div>
  );
}
