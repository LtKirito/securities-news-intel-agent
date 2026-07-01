import { useEffect, useState } from "react";
import ReportChatPanel from "../components/ReportChatPanel";
import ReportViewer from "../components/ReportViewer";
import { api, parseApiError } from "../api/client";

function splitItems(value: string) {
  return value
    .split(/[\n,，、;；|｜\t]+|\s{2,}/)
    .map(item => item.trim())
    .filter(Boolean);
}

function itemCount(value: string) {
  return splitItems(value).length;
}

const multiValueHint = "支持换行、逗号、顿号、分号或竖线分隔，例如：人形机器人、减速器、伺服系统";

const workflowSteps = [
  "读取系统模板与板块画像",
  "固定源采集 source_registry",
  "公开来源补强 research_search",
  "去重过滤 news_dedup",
  "质量门控 quality_gate",
  "SenseAudio 趋势分析与报告生成",
];

type SectorTemplate = {
  id: string;
  name: string;
  display_name: string;
  status: string;
  description: string;
  keywords?: string[];
  expanded_keywords?: string[];
  exclude_keywords?: string[];
  related_companies?: string[];
  chain_nodes?: string[];
  verification_metrics?: string[];
  preferred_sources?: string[];
  keywords_count?: number;
  companies_count?: number;
  quality_baseline?: {
    last_verified_run_id?: string;
    kept_items?: number;
    sa_source_ratio?: number;
    company_hit_ratio?: number;
    quality_gate_passed?: boolean;
  };
};

function joinItems(items?: string[]) {
  return (items || []).join("\n");
}

function templateStatusLabel(status: string) {
  if (status === "curated_high") return "已调优";
  if (status === "curated_standard") return "已整理";
  if (status === "watchlist") return "观察版";
  return "模板";
}

export default function GenerateReport() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [sector, setSector] = useState("存储芯片");
  const [keywords, setKeywords] = useState("DRAM\nNAND\nHBM\n存储芯片");
  const [companies, setCompanies] = useState("长江存储\n兆易创新\n北京君正");
  const [chainNodes, setChainNodes] = useState("需求端\n存储价格\n模组/封测\n相关公司");
  const [metrics, setMetrics] = useState("订单公告\n价格变化\n库存\n业绩预告");
  const [manualLinks, setManualLinks] = useState("");
  const [useMock, setUseMock] = useState(true);
  const [saveConfig, setSaveConfig] = useState(false);
  const [sourceStrictness, setSourceStrictness] = useState("standard");
  const [p0Strictness, setP0Strictness] = useState("standard");
  const [allowLimitedReport, setAllowLimitedReport] = useState(true);
  const [allowCommercialFallback, setAllowCommercialFallback] = useState(false);
  const [relaxQualityGate, setRelaxQualityGate] = useState(false);
  const [templates, setTemplates] = useState<SectorTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [templateError, setTemplateError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState(-1);
  const [elapsed, setElapsed] = useState(0);
  const [stepStatus, setStepStatus] = useState<string[]>([]); // idle / running / done
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [generationState, setGenerationState] = useState<"idle" | "running" | "completed">("idle");
  const [progressMessage, setProgressMessage] = useState("");

  useEffect(() => {
    api<SectorTemplate[]>("/sector-templates")
      .then(setTemplates)
      .catch(err => setTemplateError(parseApiError(err)));
    // Restore last generated report from session (survives page navigation)
    let pollTimer: number | undefined;
    let elapsedInt: number | undefined;
    try {
      const saved = sessionStorage.getItem("last_report_data");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.status === "done" && parsed.report) {
          setReport(parsed.report);
          setResult(parsed.result || null);
          setGenerationState("completed");
          setActiveStep(workflowSteps.length);
          setStepStatus(() => workflowSteps.map(() => "done"));
          setElapsed(0);
          // Restore form state so Mock checkbox etc. matches what was used
          if (parsed.form) {
            setUseMock(parsed.form.useMock !== false);
            if (parsed.form.sector) setSector(parsed.form.sector);
            if (parsed.form.keywords) setKeywords(parsed.form.keywords);
            if (parsed.form.companies) setCompanies(parsed.form.companies);
            if (parsed.form.chainNodes) setChainNodes(parsed.form.chainNodes);
            if (parsed.form.metrics) setMetrics(parsed.form.metrics);
            if (parsed.form.date) setDate(parsed.form.date);
          }
        } else if (parsed.status === "running" && parsed.report_id) {
          setGenerationState("running");
          setProgressMessage("恢复生成状态，等待后端进度...");
          setResult({ run_id: parsed.run_id, sector: parsed.sector, report_id: parsed.report_id });
          setStepStatus(() => ["running", "idle", "idle", "idle", "idle", "idle"]);
          const startedAt = parsed.started_at || Date.now();
          elapsedInt = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
          pollTimer = window.setInterval(async () => {
            try {
              const status = await api<any>(`/reports/${parsed.report_id}/status`);
              if (status.progress?.message) setProgressMessage(`${status.progress.message} · ${status.progress.elapsed_seconds || 0}s`);
              if (status.status === "done") {
                const detail = await api<any>(`/reports/${parsed.report_id}`);
                const doneResult = { run_id: parsed.run_id, sector: parsed.sector, report_id: parsed.report_id };
                setReport(detail);
                setResult(doneResult);
                setGenerationState("completed");
                setProgressMessage("");
                setActiveStep(workflowSteps.length);
                setStepStatus(() => workflowSteps.map(() => "done"));
                setElapsed(0);
                if (elapsedInt) window.clearInterval(elapsedInt);
                try { sessionStorage.setItem("last_report_data", JSON.stringify({ status: "done", report: detail, result: doneResult, form: parsed.form })); } catch {}
                if (pollTimer) window.clearInterval(pollTimer);
              } else if (status.status === "error") {
                setError(status.error || "日报生成失败");
                setProgressMessage("");
                setGenerationState("idle");
                if (elapsedInt) window.clearInterval(elapsedInt);
                if (pollTimer) window.clearInterval(pollTimer);
              }
            } catch {}
          }, 4000);
        }
      }
    } catch {}
    return () => {
      if (pollTimer) window.clearInterval(pollTimer);
      if (elapsedInt) window.clearInterval(elapsedInt);
    };
  }, []);

  async function applyTemplate(templateId: string) {
    setSelectedTemplateId(templateId);
    if (!templateId) return;
    try {
      const template = await api<SectorTemplate>(`/sector-templates/${templateId}`);
      setSector(template.name);
      setKeywords(joinItems([...(template.keywords || []), ...(template.expanded_keywords || [])]));
      setCompanies(joinItems(template.related_companies));
      setChainNodes(joinItems(template.chain_nodes));
      setMetrics(joinItems(template.verification_metrics));
      setTemplateError("");
    } catch (err) {
      setTemplateError(parseApiError(err));
    }
  }

  async function generate() {
    setError("");
    setResult(null);
    setReport(null);
    setGenerationState("running");
    setProgressMessage("创建日报生成任务...");
    const startedAt = Date.now();
    setLoading(true);
    setActiveStep(0);
    setStepStatus(workflowSteps.map((_, i) => i === 0 ? "running" : "idle"));
    setElapsed(0);
    const startTime = Date.now();
    const elapsedTimer = window.setInterval(() => setElapsed(e => e + 1), 1000);

    // natural progress: steps 1-3 (~15s), 4-5 (~5s), step 6 (rest)
    const stepTimings = [3, 8, 14, 17, 20]; // cumulative seconds for each step transition
    const progressTimer = window.setInterval(() => {
      const runningSeconds = (Date.now() - startTime) / 1000;
      setActiveStep(step => {
        if (step >= workflowSteps.length - 1) return step;
        const nextStep = stepTimings.findIndex(t => runningSeconds < t);
        const targetStep = nextStep >= 0 ? nextStep : workflowSteps.length - 1;
        if (targetStep > step) {
          setStepStatus(prev => {
            const next = [...prev];
            next[step] = "done";
            next[targetStep] = "running";
            return next;
          });
          return targetStep;
        }
        return step;
      });
    }, 1000);

    let completed = false;
    try {
      const payload = {
        date,
        sectors: [sector],
        manual_links: splitItems(manualLinks),
        collection_modes: manualLinks.trim() ? ["automatic_search", "configured_sources", "manual_links"] : ["automatic_search", "configured_sources"],
        use_mock: useMock,
        save_config: saveConfig,
        runtime_sector_config: {
          name: sector,
          enabled: true,
          keywords: splitItems(keywords),
          related_companies: splitItems(companies),
          chain_nodes: splitItems(chainNodes),
          verification_metrics: splitItems(metrics),
          expanded_keywords: [],
          exclude_keywords: [],
        },
        source_preferences: {
          strictness: sourceStrictness,
          community_source_policy: "no_single_community_p0",
        },
        rating_overlay: {
          p0_strictness: p0Strictness,
        },
        allow_limited_confidence_report: allowLimitedReport,
        allow_commercial_fallback: allowCommercialFallback,
        relax_quality_gate: relaxQualityGate,
      };
      const generated = await api<any>("/reports/generate", { method: "POST", body: JSON.stringify(payload) });
      setResult(generated);

      if (generated.status === "generating" && generated.report_id) {
        try { sessionStorage.setItem("last_report_data", JSON.stringify({
          status: "running",
          started_at: startedAt,
          report_id: generated.report_id,
          run_id: generated.run_id,
          sector: generated.sector,
          form: { useMock, sector, keywords, companies, chainNodes, metrics, date }
        })); } catch {}
        for (let i = 0; i < 180; i++) {
          await new Promise(resolve => setTimeout(resolve, 4000));
          const status = await api<any>(`/reports/${generated.report_id}/status`);
          if (status.progress?.message) setProgressMessage(`${status.progress.message} · ${status.progress.elapsed_seconds || 0}s`);
          if (status.status === "done") {
            const detail = await api<any>(`/reports/${generated.report_id}`);
            setReport(detail);
            completed = true;
            setGenerationState("completed");
            setProgressMessage("");
            setActiveStep(workflowSteps.length);
            setStepStatus(() => workflowSteps.map(() => "done"));
            try { sessionStorage.setItem("last_report_data", JSON.stringify({
              status: "done", report: detail, result: generated,
              form: { useMock, sector, keywords, companies, chainNodes, metrics, date }
            })); } catch {}
            break;
          }
          if (status.status === "error") {
            throw new Error(status.error || "日报生成失败");
          }
        }
      } else if (generated.report_id) {
        const detail = await api<any>(`/reports/${generated.report_id}`);
        setReport(detail);
        completed = true;
        setGenerationState("completed");
        setActiveStep(workflowSteps.length);
        setStepStatus(() => workflowSteps.map(() => "done"));
        try { sessionStorage.setItem("last_report_data", JSON.stringify({
          status: "done", report: detail, result: generated,
          form: { useMock, sector, keywords, companies, chainNodes, metrics, date }
        })); } catch {}
      }
    } catch (err) {
      setError(parseApiError(err));
      setProgressMessage("");
      setGenerationState("idle");
    } finally {
      window.clearInterval(elapsedTimer);
      window.clearInterval(progressTimer);
      setLoading(false);
      setStepStatus(prev => completed ? prev.map(() => "done") : prev);
    }
  }

  return (
    <div className="generate-workspace">
      <section className="hero-panel compact-hero">
        <div>
          <p className="eyebrow">日报生成</p>
          <h1>配置本次日报，并直接阅读生成结果</h1>
          <p>配置跟随本次生成，可选择仅本次使用或保存为常用配置。AI 问答会基于当前日报内容回答。</p>
        </div>
      </section>

      <section className="generate-grid">
        <div className="panel config-panel">
          <p className="eyebrow">本次生成配置</p>
          <h3>快速配置</h3>
          <div className="template-picker">
            <div className="template-picker-head">
              <div>
                <p className="eyebrow">系统模板库</p>
                <h4>选择已调优板块模板</h4>
              </div>
              <select value={selectedTemplateId} onChange={event => applyTemplate(event.target.value)}>
                <option value="">手动配置</option>
                {templates.map(template => <option key={template.id} value={template.id}>{template.display_name}</option>)}
              </select>
            </div>
            {templateError && <div className="notice warning">{templateError}</div>}
            <div className="template-cards">
              {templates.map(template => (
                <button type="button" className={`template-card ${selectedTemplateId === template.id ? "active" : ""}`} key={template.id} onClick={() => applyTemplate(template.id)}>
                  <span>{templateStatusLabel(template.status)}</span>
                  <strong>{template.display_name}</strong>
                  <small>{template.description}</small>
                  <em>{template.companies_count || 0} 家公司 · 最近验证 {template.quality_baseline?.quality_gate_passed ? "通过" : "待验证"}</em>
                </button>
              ))}
            </div>
          </div>
          <div className="form-grid two">
            <label>生成日期<input value={date} onChange={event => setDate(event.target.value)} /></label>
            <label>板块名称<input value={sector} onChange={event => setSector(event.target.value)} /></label>
          </div>
          <label>关键词<textarea value={keywords} onChange={event => setKeywords(event.target.value)} placeholder={multiValueHint} /><small className="input-hint">{multiValueHint} · 已识别 {itemCount(keywords)} 项</small></label>
          <label>手动链接<textarea value={manualLinks} onChange={event => setManualLinks(event.target.value)} placeholder="可选，支持换行、逗号、分号或竖线分隔多个公开新闻链接" /><small className="input-hint">可选 · 已识别 {itemCount(manualLinks)} 条链接</small></label>

          <details className="advanced-box" open>
            <summary>高级配置：板块、信息源、评级偏好</summary>
            <div className="form-grid two">
              <label>相关公司<textarea value={companies} onChange={event => setCompanies(event.target.value)} placeholder="例如：埃斯顿、汇川技术、绿的谐波" /><small className="input-hint">支持换行、逗号、顿号、分号或竖线分隔 · 已识别 {itemCount(companies)} 项</small></label>
              <label>产业链节点<textarea value={chainNodes} onChange={event => setChainNodes(event.target.value)} placeholder="例如：核心零部件、运动控制、系统集成" /><small className="input-hint">支持换行、逗号、顿号、分号或竖线分隔 · 已识别 {itemCount(chainNodes)} 项</small></label>
            </div>
            <label>验证指标<textarea value={metrics} onChange={event => setMetrics(event.target.value)} placeholder="例如：订单增速、出货量、毛利率、量产节奏" /><small className="input-hint">支持换行、逗号、顿号、分号或竖线分隔 · 已识别 {itemCount(metrics)} 项</small></label>
            <div className="form-grid two">
              <label>来源严格程度<select value={sourceStrictness} onChange={event => setSourceStrictness(event.target.value)}><option value="strict">严格</option><option value="standard">标准</option><option value="relaxed">宽松</option></select></label>
              <label>P0 稀缺程度<select value={p0Strictness} onChange={event => setP0Strictness(event.target.value)}><option value="strict">严格</option><option value="standard">标准</option><option value="relaxed">宽松</option></select></label>
            </div>
            <div className="rules-note">固定硬规则：禁止投资建议、禁止目标价、单一社区来源不能 P0、P0 必须具备影响链条和趋势解释。</div>
            <div className="quality-options">
              <label><input type="checkbox" checked={allowLimitedReport} onChange={event => setAllowLimitedReport(event.target.checked)} /> 质量不足时仍生成观察版日报</label>
              <label><input type="checkbox" checked={relaxQualityGate} onChange={event => setRelaxQualityGate(event.target.checked)} /> 放宽本次门槛</label>
              <label><input type="checkbox" checked={allowCommercialFallback} onChange={event => setAllowCommercialFallback(event.target.checked)} /> 必要时启用商业搜索兜底</label>
            </div>
            <div className="rules-note">若板块暂无成熟画像，系统会自动使用临时画像；建议补充 5-15 家代表上市公司以提高日报精度。</div>
          </details>

          <div className="toggle-row"><label><input type="checkbox" checked={useMock} onChange={event => setUseMock(event.target.checked)} /> 使用 Mock 模式测试</label><label><input type="checkbox" checked={saveConfig} onChange={event => setSaveConfig(event.target.checked)} /> 保存为常用配置</label></div>
          <button onClick={generate} disabled={loading}>{loading ? "生成中..." : saveConfig ? "保存配置并生成" : "仅本次生成"}</button>
          {error && <div className="notice warning">{error}</div>}
          {generationState === "running" && <div className="notice warning">日报生成中：{sector} · {elapsed > 0 && <>{elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}分${elapsed % 60}s`}</>}{progressMessage ? ` · ${progressMessage}` : ""}</div>}
          {generationState === "completed" && result && <div className="notice success">日报已生成：{result.sector} · {result.run_id?.slice(0, 12)}</div>}
        </div>

        <div className="panel progress-panel">
          <p className="eyebrow">ResearchRunner</p>
          <h3>共用日报生成引擎</h3>
          <div className="workflow-list">
            {workflowSteps.map((step, index) => <div className={`workflow-step ${stepStatus[index] === "done" ? "done" : stepStatus[index] === "running" ? "active" : ""}`} key={step}><span>{index + 1}</span><p>{step}{stepStatus[index] === "running" && index === workflowSteps.length - 1 ? <span className="pulse-dot"> ●</span> : null}</p></div>)}
          </div>
          <p className="muted">耗时：{elapsed > 0 && loading ? <>已运行 <strong>{elapsed}s</strong></> : elapsed > 0 ? <><strong>{elapsed}s</strong></> : null}</p>
          {progressMessage && <p className="muted">当前阶段：{progressMessage}</p>}
          <p className="muted">真实生成会复用 CLI 调优的 ResearchRunner：固定源采集、质量门控、低置信日报和中间产物统一落盘。</p>
        </div>
      </section>

      <section className="report-chat-layout">
        <div className="panel report-panel"><ReportViewer report={report} /></div>
        <ReportChatPanel report={report} date={date} sector={report?.sectors?.[0] || sector} />
      </section>
    </div>
  );
}
