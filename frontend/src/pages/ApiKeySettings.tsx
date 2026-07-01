import { useState } from "react";
import { api } from "../api/client";

export default function ApiKeySettings() {
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");
  async function save() {
    await api("/api-keys", { method: "POST", body: JSON.stringify({ api_key: apiKey }) });
    setMessage("API Key 已保存");
  }
  async function test() {
    const result = await api<{ ok: boolean }>("/api-keys/test", { method: "POST" });
    setMessage(result.ok ? "连接成功" : "连接失败");
  }
  return <div className="card grid">
    <h2>SenseAudio API Key</h2>
    <p>模型固定为 senseaudio-s2，地址固定为 https://api.senseaudio.cn。</p>
    <label>API Key<input value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="Bearer token" /></label>
    <div><button onClick={save}>保存</button> <button className="secondary" onClick={test}>测试连接</button></div>
    <p>{message}</p>
  </div>;
}
