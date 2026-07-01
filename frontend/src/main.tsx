import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { clearToken, getToken } from "./api/client";
import Dashboard from "./pages/Dashboard";
import GenerateReport from "./pages/GenerateReport";
import Login from "./pages/Login";
import ReportHistory from "./pages/ReportHistory";
import "./styles.css";

function AppShell() {
  const location = useLocation();
  const token = getToken();
  const isLogin = location.pathname === "/login" || !token;

  if (isLogin) {
    return <main className="login-stage"><Login /></main>;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">SI</span>
          <div>
            <h1>证券产业情报</h1>
            <p>SenseAudio-S2</p>
          </div>
        </div>
        <nav>
          <NavLink to="/">工作台</NavLink>
          <NavLink to="/generate">日报生成</NavLink>
          <NavLink to="/reports">历史日报</NavLink>
        </nav>
        <button className="ghost full" onClick={() => { clearToken(); window.location.href = "/login"; }}>退出登录</button>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Securities Daily Intel</p>
            <h2>公开新闻驱动的产业日报工作台</h2>
          </div>
          <Link className="top-action" to="/generate">生成日报</Link>
        </header>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/generate" element={<GenerateReport />} />
          <Route path="/reports" element={<ReportHistory />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return <BrowserRouter><AppShell /></BrowserRouter>;
}

createRoot(document.getElementById("root")!).render(<App />);
