import { useState } from "react";
import { api, parseApiError } from "../api/client";

type Props = {
  report: any | null;
  date?: string;
  sector?: string;
};

export default function ReportChatPanel({ report, date, sector }: Props) {
  const [question, setQuestion] = useState("这份日报里最需要后续验证的信号是什么？");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function ask() {
    setError("");
    setAnswer("");
    setLoading(true);
    try {
      const result = await api<{ answer: string }>("/chat", {
        method: "POST",
        body: JSON.stringify({ question, date: date || report?.date, sector: sector || report?.sectors?.[0] }),
      });
      setAnswer(result.answer);
    } catch (err) {
      setError(parseApiError(err) || "问答暂不可用。真实问答需要配置可用的 SenseAudio API Key。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="chat-panel">
      <p className="eyebrow">基于当前日报提问</p>
      <h3>日报 AI 助手</h3>
      <p className="muted">仅基于当前日报内容回答，不提供买卖建议。</p>
      <textarea value={question} onChange={event => setQuestion(event.target.value)} disabled={!report} />
      <button onClick={ask} disabled={!report || loading}>{loading ? "分析中..." : "提问"}</button>
      {!report && <p className="hint">生成或打开一份日报后可提问。</p>}
      {error && <div className="notice warning">{error}</div>}
      {answer && <div className="answer-box">{answer}</div>}
    </aside>
  );
}
