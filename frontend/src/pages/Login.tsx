import { useState } from "react";
import { api, parseApiError, setToken } from "../api/client";

export default function Login() {
  const [username, setUsername] = useState("test");
  const [password, setPassword] = useState("test123");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(path: string) {
    setError("");
    setMessage("");
    try {
      const result = await api<{ access_token: string }>(path, { method: "POST", body: JSON.stringify({ username, password }) });
      setToken(result.access_token);
      setMessage("已登录，正在进入工作台...");
      window.location.href = "/";
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  return <div className="login-panel">
    <div className="login-copy">
      <p className="eyebrow">Securities Daily Intel</p>
      <h1>证券产业新闻情报工作台</h1>
      <p>基于 Agent 技能、用户配置与 SenseAudio-S2 的日报生成、历史复盘和日报问答系统。</p>
    </div>
    <div className="login-card">
      <h2>登录 / 注册</h2>
      <label>用户名<input value={username} onChange={event => setUsername(event.target.value)} /></label>
      <label>密码<input type="password" value={password} onChange={event => setPassword(event.target.value)} /></label>
      <div className="button-row"><button onClick={() => submit("/auth/login")}>登录</button><button className="ghost" onClick={() => submit("/auth/register")}>注册</button></div>
      {message && <div className="notice success">{message}</div>}
      {error && <div className="notice warning">{error}</div>}
    </div>
  </div>;
}
