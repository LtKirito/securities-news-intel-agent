import { useState } from "react";
import { api } from "../api/client";

export default function Chat() {
  const [question, setQuestion] = useState("今天 P0 为什么重要？");
  const [answer, setAnswer] = useState("");
  async function ask() {
    const result = await api<{ answer: string }>("/chat", { method: "POST", body: JSON.stringify({ question }) });
    setAnswer(result.answer);
  }
  return <div className="card grid">
    <h2>日报 AI 问答</h2>
    <label>问题<textarea value={question} onChange={e => setQuestion(e.target.value)} /></label>
    <button onClick={ask}>提问</button>
    {answer && <p>{answer}</p>}
  </div>;
}
