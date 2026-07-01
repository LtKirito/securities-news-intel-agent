import { useState } from "react";
import { api } from "../api/client";

function splitLines(value: string) { return value.split(/\n|,/).map(v => v.trim()).filter(Boolean); }

export default function SectorConfigs() {
  const [name, setName] = useState("PCB");
  const [keywords, setKeywords] = useState("PCB\n高端PCB\n覆铜板");
  const [metrics, setMetrics] = useState("涨价函\n订单\n业绩预告");
  const [message, setMessage] = useState("");
  async function save() {
    await api("/configs/sectors", { method: "POST", body: JSON.stringify({ name, enabled: true, keywords: splitLines(keywords), verification_metrics: splitLines(metrics) }) });
    setMessage("板块配置已保存");
  }
  return <div className="card grid">
    <h2>板块配置</h2>
    <label>板块名称<input value={name} onChange={e => setName(e.target.value)} /></label>
    <label>关键词<textarea value={keywords} onChange={e => setKeywords(e.target.value)} /></label>
    <label>验证指标<textarea value={metrics} onChange={e => setMetrics(e.target.value)} /></label>
    <button onClick={save}>保存配置</button>
    <p>{message}</p>
  </div>;
}
