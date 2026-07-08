"use client";
import { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { mutate } from "swr";
import { Icon } from "@/components/ui/Icon";
import { AlertItem } from "@/components/polaris/AlertItem";
import { CitationList } from "@/components/polaris/CitationList";
import { TracePanel } from "@/components/polaris/TracePanel";
import { ComplianceBanner } from "@/components/polaris/ComplianceBanner";
import { TextGenerate } from "@/components/ui/TextGenerate";
import { DocViewer, type DocContent } from "@/components/polaris/DocViewer";
import { ReportModal } from "@/components/polaris/ReportModal";
import { KpiSkeleton, PanelSkeleton } from "@/components/polaris/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useResearch } from "@/hooks/useResearch";
import { useReadStore } from "@/hooks/useReadStore";
import { useSuggestions } from "@/hooks/useSuggestions";
import { useContraAlerts } from "@/hooks/useContraAlerts";
import { useCompanies } from "@/hooks/useCompanies";
import { useFinancials, inferTickerFromQuery, financialsToKpis } from "@/hooks/useFinancials";
import { isFinancialQuery } from "@/lib/queryRelevance";
import { hasValue } from "@/lib/fieldUtils";
import { fmtFinNum } from "@/lib/formatters";
import { contraAlertStore, type ContraAlert } from "@/lib/contraAlertStore";
import type { KpiVM } from "@/types/viewmodel";
import { historyStore, extractTickers } from "@/lib/historyStore";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ResearchTour } from "@/components/polaris/ResearchTour";

const PHASES = ["理解查詢意圖","檢索文件庫","重排序候選","計算 + 交叉驗證","生成摘要","合規檢查"];
const PRESETS = ["台積電 2026Q1 法說會營運重點","聯發科 AI 邊緣運算佈局","台股半導體庫存週期"];




const TOUR_MOCK_RESULT = {
  query: "台積電 2026Q1 法說會重點",
  compliance_status: "pass",
  retrieval_degraded: false,
  kpis: [
    { label: "毛利率", value: "57.8", unit: "%", delta: "QoQ +1.6pp", trend: "up" as const, cite: "stub-2330-2026Q1-fin" },
    { label: "營業利益率", value: "47.5", unit: "%", delta: "QoQ +0.8pp", trend: "up" as const, cite: "stub-2330-2026Q1-fin" },
    { label: "全年美元營收指引", value: "中段 20%+", unit: "", delta: "上調", trend: "up" as const, cite: "stub-2330-2026Q1-call" },
  ],
  summary: [
    { text: "台積電 2026Q1 毛利率達 57.8%，季增 1.6pp，超出市場預期。", cite: "stub-2330-2026Q1-fin", page: "p.11" },
    { text: "CoWoS 先進封裝需求強勁，Q4 產能預估較 Q3 翻倍。", cite: "stub-2330-2026Q1-call", page: "p.7" },
    { text: "全年美元營收指引上調至中段 20% 以上成長。", cite: "stub-2330-2026Q1-transcript", page: "p.3" },
  ],
  chart: [
    { label: "2025Q2", value: 53.1 }, { label: "2025Q3", value: 54.8 },
    { label: "2025Q4", value: 56.2 }, { label: "2026Q1", value: 57.8 },
  ],
  react: [
    { type: "THINK" as const, text: "解析查詢意圖：台積電 2026Q1 法說會重點", tool: false },
    { type: "ACT" as const, text: "檢索法說逐字稿與財報 chunks", tool: true },
    { type: "OBS" as const, text: "找到 12 筆相關段落，覆蓋毛利率、CoWoS 產能、營收指引", tool: false },
  ],
  citations: [
    { ix: "1", label: "台積電_2026Q1_合併財報", detail: "財務報表", cite: "stub-2330-2026Q1-fin", snippet: "毛利率 57.8%，營業利益率 47.5%", period: "2026Q1" },
    { ix: "2", label: "台積電_2026Q1_法說會逐字稿", detail: "法說會逐字稿", cite: "stub-2330-2026Q1-transcript", snippet: "CoWoS 產能 Q4 預估翻倍", period: "2026Q1" },
  ],
};

function thinkingMsgTier(sec: number): number {
  if (sec >= 25) return 5;
  if (sec >= 20) return 4;
  if (sec >= 15) return 3;
  if (sec >= 10) return 2;
  if (sec >= 5)  return 1;
  return 0;
}
function thinkingMsgText(sec: number): string {
  if (sec >= 25) return "手滑就要重等囉~快完成了~謝謝您的等候~";
  if (sec >= 20) return "真的快好了，別離開喔~不然又要重跑一遍~";
  if (sec >= 15) return "絞盡腦汁中，快好了";
  if (sec >= 10) return "正在睜大雙眼檢查數據";
  if (sec >= 5)  return "腦袋快速翻轉跟審閱相關資料";
  return "正在思考中";
}
function kpiSortKey(label: string): number {
  if (label.startsWith("月營收 YoY")) return 2;
  if (label.startsWith("月營收"))    return 1;
  if (label.startsWith("淨利率"))  return 3;
  if (label.includes("毛利率"))      return 4;
  if (label.includes("EPS"))      return 5;
  if (label.includes("累計 YoY"))         return 6;
  return 99;
}

function ResearchPageInner() {
  const { trigger, data, isMutating } = useResearch();
  const rs = useReadStore();
  const searchParams = useSearchParams();
  const [restoredData, setRestoredData] = useState<typeof data>(undefined);
  const [restoredAt, setRestoredAt] = useState<string | null>(null);
  const [tourSampleFailed, setTourSampleFailed] = useState(false);
  const { suggestions: dynamicSuggestions, fading: chipsFading } = useSuggestions();
  const contraAlerts = useContraAlerts("research");
  const companies = useCompanies();
  const chips = dynamicSuggestions ?? PRESETS;
  const [query, setQuery] = useState("");
  const [hasQueried, setHasQueried] = useState(false);
  const [inferredTicker, setInferredTicker] = useState<string | null>(null);
  const [selectedAlertIdx, setSelectedAlertIdx] = useState<number|null>(null);
  const [modalAlert, setModalAlert] = useState<any>(null);
  const [isCheckingContra, setIsCheckingContra] = useState(false);
  const [openDoc, setOpenDoc] = useState<DocContent|null>(null);
  const [phase, setPhase] = useState("idle");
  const [loadError, setLoadError] = useState(false);
  const [stepN, setStepN] = useState(0);
  const [progress, setProgress] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [thinkingSec, setThinkingSec] = useState(0);
  const [isListening, setIsListening] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [ctxOpen, setCtxOpen] = useState(true);
  const [kpiShowAll, setKpiShowAll] = useState(false);

  // B 級還原：從 history 頁點進來時，讀 sessionStorage 直接復原結果；
  // 還原不成（localStorage 紀錄無整包 result、或刷新後 sessionStorage 已清）
  // 退回 A 級：帶 ?q= 自動重跑一次查詢，不再停在空白初始頁
  const historyEntryConsumedRef = useRef(false);
  useEffect(() => {
    // 冪等 guard：restore 分支會消耗掉 sessionStorage，effect 重跑（dev StrictMode）
    // 時第二次會誤入 q 分支、拿 API 重跑蓋掉剛還原的結果
    if (historyEntryConsumedRef.current) return;
    historyEntryConsumedRef.current = true;
    const historyId = searchParams.get("historyId");
    if (historyId) {
      try {
        const raw = sessionStorage.getItem("polaris_restore");
        if (raw) {
          const saved = JSON.parse(raw);
          if (saved.id === historyId) {
            setQuery(saved.query ?? "");
            setHasQueried(true);
            setPhase("done");
            setProgress(100);
            setRestoredData(saved.result);
            setRestoredAt(saved.time ?? null);
            sessionStorage.removeItem("polaris_restore");
            return;
          }
        }
      } catch {}
    }
    const q = searchParams.get("q");
    if (q) {
      setQuery(q);
      run(q);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startVoice = () => {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) { alert("此瀏覽器不支援語音輸入，請改用 Chrome"); return; }
    const rec = new SR();
    rec.lang = "zh-TW";
    rec.interimResults = false;
    rec.onstart = () => setIsListening(true);
    rec.onend   = () => setIsListening(false);
    rec.onerror = () => setIsListening(false);
    rec.onresult = (e: any) => {
      const text = e.results[0][0].transcript;
      setQuery(text);
      run(text);
    };
    rec.start();
  };

  const displayData = restoredData ?? data;
  const kpis = displayData?.kpis ?? [];
  const summary = displayData?.summary ?? [];
  const reactSteps = displayData?.react ?? [];
  const citations = displayData?.citations ?? [];

  const { rows: financialRows, isLoading: isLoadingFinancials } = useFinancials(inferredTicker);
  const financialKpis = financialsToKpis(financialRows);
  const sortedKpis = [...(kpis.length > 0 ? kpis : (isFinancialQuery(query) ? financialKpis : []))]
    .sort((a, b) => kpiSortKey(a.label) - kpiSortKey(b.label))
    .filter(k => hasValue(k.value));

  const researchAlerts = contraAlerts.filter(a => a.level !== "info");

  const runContradictionCheck = async (
    k: KpiVM[] = kpis,
    s: Array<{ text: string; cite: string; page: string }> = summary,
  ) => {
    if (isCheckingContra) return;
    setIsCheckingContra(true);
    try {
      const data = await api.contradiction(k, s);
      contraAlertStore.set(data.alerts, "research");
    } catch { /* backend not ready, fall through */ }
    finally {
      setIsCheckingContra(false);
    }
  };

  const run = async (q?: string) => {
    // 防止上一題還在跑時被 Enter / chip 再次觸發：較慢的舊請求晚回來會蓋掉新結果，
    // 造成畫面顯示的引用來源其實是上一題的（見 R6 台積電/聯發科混淆報告）。
    if (phase === "running") return;
    timers.current.forEach(clearTimeout); timers.current = [];
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }

    contraAlertStore.clear("research");
    setSelectedAlertIdx(null);
    setHasQueried(true);
    setLoadError(false);
    setPhase("running"); setStepN(0); setProgress(0);

    // 從查詢推斷 ticker，讓 useFinancials 預先取 R4 財務資料
    const resolvedQ = q ?? query;
    const ticker = inferTickerFromQuery(resolvedQ, companies);
    setInferredTicker(ticker);

    // 階段一：API 等待期間，爬升至 30%
    intervalRef.current = setInterval(() => {
      setProgress(p => Math.min(p + 2, 30));
    }, 200);

    setTourSampleFailed(false);
    try {
      const result = await trigger(q ?? query);

      historyStore.write({ page: "research", query: q ?? query, tags: extractTickers(q ?? query) });
      api.postHistory("research", q ?? query, extractTickers(q ?? query), result);
      mutate("history");
      toast.success("已儲存至對話紀錄");

      // 切換至階段二：清除 interval，snap 到 30%，再依真實步數推進
      clearInterval(intervalRef.current); intervalRef.current = null;
      setProgress(p => Math.max(p, 30));

      const steps = result?.react ?? [];
      const total = Math.max(steps.length, 1);
      steps.forEach((_, i) => {
        timers.current.push(setTimeout(() => {
          setStepN(i + 1);
          setProgress(_ => 30 + Math.round(((i + 1) / total) * 70));
        }, 220 * (i + 1)));
      });
      timers.current.push(setTimeout(() => {
        setPhase("done");
        runContradictionCheck(result?.kpis ?? [], result?.summary ?? []);
      }, 220 * total + 300));

    } catch (err) {
      // 請求失敗（後端 4xx/5xx、斷網、API_BASE/proxy 設錯…）。不要 silent 吞成
      // 「查無資料」——那會跟「真的沒資料」混淆。明確標記錯誤 + 提示使用者。
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      console.error("[research] request failed", err);
      setLoadError(true);
      setPhase("done");
      setProgress(0);
      setTourSampleFailed(true);
      toast.error("研究請求失敗，請稍後再試（後端無回應或設定錯誤）");
    }
  };
  useEffect(() => () => {
    timers.current.forEach(clearTimeout);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  useEffect(() => {
    if (phase !== "running") { setThinkingSec(0); return; }
    setThinkingSec(0);
    const t = setInterval(() => setThinkingSec(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  const handleTourRunSample = () => {
    setQuery(TOUR_MOCK_RESULT.query);
    setHasQueried(true);
    setPhase("running");
    setStepN(0);
    setProgress(0);
    setTourSampleFailed(false);
    // 假進度動畫：2 秒爬升至 100%，結束後注入 mock 資料（不呼叫 API、不寫對話紀錄）
    const start = Date.now();
    const tick = () => {
      const elapsed = Date.now() - start;
      const p = Math.min(Math.round((elapsed / 2000) * 100), 100);
      setProgress(p);
      if (p < 100) { timers.current.push(setTimeout(tick, 80)); return; }
      setPhase("done");
      setRestoredData(TOUR_MOCK_RESULT as typeof data);
    };
    timers.current.push(setTimeout(tick, 80));
  };

  const handleTourReset = () => {
    setQuery("");
    setHasQueried(false);
    setPhase("idle");
    setProgress(0);
    setRestoredData(undefined);
    setRestoredAt(null);
    contraAlertStore.clear("research");
  };

  const running = phase==="running";
  const total = reactSteps.length || 1;
  const curPhase = running ? PHASES[Math.min(Math.floor((stepN / total) * PHASES.length), PHASES.length - 1)] : null;
  const handleOpenDoc = async (cite: string) => {
    // 先打真實 API（R3 實作後自動生效）
    const chunk = await api.chunk(cite);
    if (chunk) { setOpenDoc(chunk); return; }
    // fallback：從引用 VM 自行組裝
    const vm = citations.find(c => c.cite === cite);
    if (!vm) return;
    const relatedText = summary.filter(s => s.cite === cite).map(s => s.text).join(" ");
    const hlTokens = relatedText
      .match(/[一-鿿]{2,}|[A-Z][a-zA-Z]+|[\d]+\.[\d]+%?/g)
      ?.filter(t => vm.snippet.includes(t))
      .slice(0, 6) ?? [];
    setOpenDoc({
      key: vm.cite,
      title: vm.label,
      kind: vm.label,
      source_id: vm.cite,
      page: vm.detail,
      period: vm.period || undefined,
      trust: "mid",
      hlTokens,
      highlight: vm.snippet,
      body: vm.snippet.split(/(?<=。)|\n/).map(s => s.trim()).filter(Boolean),
    });
  };

  return (
    <>
      <div className="page-scroll">
        <div className={"page research-layout" + (ctxOpen ? "" : " ctx-collapsed")}>
          <div className="rcol-main">
            <div className="page-head">
              <div className="page-eyebrow">研究助理 · research</div>
              <h1 className="page-title">研究分析</h1>
            </div>
            {restoredData && (
              <div className="mock-note" style={{ marginBottom: 0 }}>
                <Icon name="clock" size={15} style={{ flexShrink: 0 }}/>
                <span>
                  此為歷史分析{restoredAt ? `（${restoredAt}）` : ""}，資料可能已有更新。
                  <button
                    className="btn ghost"
                    style={{ marginLeft: 10, padding: "1px 10px", fontSize: 13, height: "auto" }}
                    onClick={() => { setRestoredData(undefined); setRestoredAt(null); run(query); }}
                  >重新查詢</button>
                </span>
              </div>
            )}
            {!hasQueried ? (
              <div className="peer-empty">
                <Icon name="spark" size={28} style={{color:"rgb(var(--muted))",marginBottom:12}}/>
                <p>輸入研究問題後開始分析</p>
              </div>
            ) : (
              <>
                {displayData?.compliance_status === "blocked" ? (
                  <ComplianceBanner message={summary[0]?.text ?? "因合規考量，本系統無法回答此類查詢。"} />
                ) : (
                <>
                <ComplianceBanner/>
                {displayData?.retrieval_degraded && (
                  <div className="mock-note">
                    <Icon name="alert" size={15} style={{ flexShrink: 0, color: "rgb(var(--warning, 200 150 50))" }}/>
                    <span>向量搜尋未命中，本次結果來自備援資料，內容可能不完整。</span>
                  </div>
                )}
                {(isMutating || isLoadingFinancials) ? <KpiSkeleton/> : (
                  sortedKpis.length > 0 && (
                    <div className="kpi-list-wrap">
                      <div className="kpi-list">
                        {(kpiShowAll ? sortedKpis : sortedKpis.slice(0, 5)).map((k, i) => (
                          <button key={i} className="kpi-row" onClick={() => handleOpenDoc(k.cite)}>
                            <span className="kr-label">{k.label}</span>
                            {k.period && <span className="kr-period">{k.period}</span>}
                            <span className="kr-value">
                              <span className="kr-num">{fmtFinNum(k.value)}</span>
                              {k.unit && <span className="kr-unit">{k.unit}</span>}
                            </span>
                            {k.delta && (
                              <span className={"kr-delta " + k.trend}>
                                <Icon name={k.trend === "up" ? "arrowUp" : "arrowDown"} size={12}/>
                                {k.delta}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                      {sortedKpis.length > 5 && (
                        <button
                          className="btn ghost"
                          style={{ fontSize: 13, padding: "3px 12px", marginTop: 4 }}
                          onClick={() => setKpiShowAll(v => !v)}
                        >
                          {kpiShowAll ? `收起 · 顯示前 5 項` : `其他 ${sortedKpis.length - 5} 項指標`}
                        </button>
                      )}
                    </div>
                  )
                )}
                <div className="rcol-stack">
                  <div className="panel">
                    <div className="panel-head">
                      <span className="panel-title"><Icon name="layers" size={15} style={{color:"rgb(var(--primary))",verticalAlign:"-3px",marginRight:6}}/>營運重點摘要</span>
                      <span className="panel-meta">{summary.length > 0 ? `${summary.length} 條 · 全數可溯源` : loadError ? "請求失敗" : "查無資料"}</span>
                    </div>
                    <div className="panel-body">
                      {isMutating ? <PanelSkeleton/> : (
                        summary.length > 0 ? (
                          <ul className="summary">
                            {summary.map((s,i)=>{
                              const hasContra = contraAlerts.some(a => a.level !== "info" && (a as any).cite_key === s.cite);
                              return (
                                <li key={s.cite + i}><span className="sum-marker"/><span><TextGenerate key={s.text} text={s.text} delay={i * 0.08} />{hasContra && <span className="tag mid" style={{marginLeft:5,padding:"1px 7px",fontSize:12,verticalAlign:"middle"}} title="矛盾偵測警告，建議核對引用原文"><span className="tdot"/>矛盾</span>}{s.cite && <span className="cchip" role="button" tabIndex={0} onClick={()=>handleOpenDoc(s.cite)} onKeyDown={e=>(e.key==="Enter"||e.key===" ")&&handleOpenDoc(s.cite)}>{s.doc_type_label ?? "文件"} {s.page}</span>}</span></li>
                              );
                            })}
                          </ul>
                        ) : (
                          <div className="chart-empty">
                            <Icon name={loadError ? "alert" : "layers"} size={20} style={{color:"rgb(var(--muted))",marginBottom:8}}/>
                            <span>{loadError ? "研究請求失敗，未取得後端回應" : "查詢的資料未涵蓋於現有資料庫"}</span>
                            <span className="font-mono" style={{fontSize:"0.72rem",color:"rgb(var(--muted))"}}>{loadError ? "請稍後再試；若持續發生請確認後端服務與 API 設定" : "請確認公司代號及財報期別是否已入庫"}</span>
                          </div>
                        )
                      )}
                    </div>
                  </div>

                </div>
              </>
            )}
              </>
            )}
            <div className="actions">
              <button className="btn" disabled={!data} title={!data ? "請先執行研究" : undefined} onClick={()=>setShowReport(true)}><Icon name="file" size={15}/>完整報告</button>
<button className="btn ghost" disabled={running} onClick={()=>run()}><Icon name="refresh" size={15}/>重新分析</button>
            </div>
          </div>
          <aside className="rcol-ctx">
            <button className="ctx-toggle-btn" onClick={()=>setCtxOpen(o=>!o)}>
              <Icon name={ctxOpen ? "chevR" : "panelLeft"} size={14}/>
              <span className="ctx-toggle-label">{ctxOpen ? "收起側欄" : "展開側欄"}</span>
            </button>
            <div className="panel ctx-panel">
              <div className="panel-head">
                <span className="panel-title"><Icon name="brain" size={15} style={{color:"rgb(var(--primary))",verticalAlign:"-3px",marginRight:6}}/>思考追蹤</span>
                <span className="panel-meta">思考追蹤</span>
              </div>
              {phase === "idle" ? (
                <div className="chart-empty" style={{padding:"20px 16px"}}>
                  <span>執行研究後顯示思考路徑</span>
                </div>
              ) : (
                <>
                  <div className="ctx-progress">
                    <div className="ctx-prog-track"><div className="ctx-prog-fill" style={{width:progress+"%"}}/></div>
                    <span className="font-mono">{running ? (curPhase ?? "") : "done"} · {progress}%</span>
                  </div>
                  {running && (
                    <div className="thinking-pulse">
                      <div className="thinking-dots"><span/><span/><span/></div>
                      <span key={thinkingMsgTier(thinkingSec)} className="thinking-msg">{thinkingMsgText(thinkingSec)}</span>
                    </div>
                  )}
                  <TracePanel steps={reactSteps} activeIndex={running?stepN-1:undefined} visibleCount={running?stepN:undefined}/>
                </>
              )}
            </div>
            <div className="panel ctx-panel">
              <div className="panel-head">
                <span className="panel-title"><Icon name="alert" size={14} style={{color:"rgb(var(--danger))",verticalAlign:"-2px",marginRight:6}}/>監控系統</span>
              </div>
              <div className="alert-list">
                {running
                  ? <div className="thinking-pulse" style={{padding:"14px 16px"}}>
                      <div className="thinking-dots"><span/><span/><span/></div>
                      <span>正在抓取資料中</span>
                    </div>
                  : researchAlerts.length > 0
                    ? researchAlerts.map((a,i)=>(
                        <AlertItem key={a.id} alert={a} selected={selectedAlertIdx===i} read={rs.isRead(a.id)}
                          onClick={()=>{setSelectedAlertIdx(selectedAlertIdx===i?null:i);rs.markRead(a.id);}}
                          onDoubleClick={()=>{setModalAlert(a);rs.markRead(a.id);}}/>
                      ))
                    : <div className="chart-empty" style={{padding:"20px 16px"}}><span>{hasQueried ? "本次研究未發現異常訊號" : "執行研究後顯示相關警示"}</span></div>
                }
              </div>
            </div>
            <div className="panel ctx-panel">
              <div className="panel-head">
                <span className="panel-title"><Icon name="quote" size={14} style={{color:"rgb(var(--primary))",verticalAlign:"-2px",marginRight:6}}/>引用資訊</span>
                {citations.length > 0 && <span className="panel-meta">可溯源</span>}
              </div>
              {running
                ? <div className="thinking-pulse" style={{padding:"14px 16px"}}>
                    <div className="thinking-dots"><span/><span/><span/></div>
                    <span>正在抓取資料中</span>
                  </div>
                : citations.length > 0
                  ? <CitationList citations={citations} onOpen={handleOpenDoc}/>
                  : <div className="chart-empty" style={{padding:"20px 16px"}}>
                      <span>{hasQueried ? "本次研究無引用來源" : "執行研究後顯示引用來源"}</span>
                    </div>
              }
            </div>
          </aside>
        </div>
      </div>
      <div className="dock">
        <div className="dock-inner">
          <div className={"dock-chips" + (chipsFading ? " chips-fading" : "")}>
            {chips.map((p,i)=><button key={i} className="chip" onClick={()=>{setQuery(p);run(p);}}>{p}</button>)}
          </div>
          <div className="dock-row">
            <Icon name="spark" size={18} style={{color:"rgb(var(--primary))",flexShrink:0}}/>
            <input className="dock-input" value={query} onChange={e=>setQuery(e.target.value)}
              onKeyDown={e=>{if(e.key==="Enter"&&(e.ctrlKey||e.metaKey||!e.shiftKey))run();}} placeholder="輸入研究問題... (Enter 送出)"/>
            <button className={"dock-tool" + (isListening ? " active" : "")} title={isListening ? "聆聽中…" : "語音輸入"} onClick={startVoice} disabled={running}><Icon name="mic" size={19}/></button>
            <button className={"btn primary dock-send" + (running ? " sending" : "")} onClick={()=>run()} disabled={running}>
              <Icon name={running?"refresh":"send"} size={18}/>
            </button>
          </div>
          <div className="dock-hint">輸入問題並交叉驗證來源 · 每筆結論皆可溯源 · 非投資建議</div>
        </div>
      </div>
      {modalAlert && (
        <div className="alert-modal-overlay" onClick={()=>setModalAlert(null)}>
          <div className="alert-modal" onClick={e=>e.stopPropagation()}>
            <div className="alert-modal-head">
              <h2>{modalAlert.title}</h2>
              <button className="alert-modal-close" onClick={()=>setModalAlert(null)} aria-label="關閉"><Icon name="x" size={18}/></button>
            </div>
            <div className="alert-modal-body">
              <div className="alert-modal-tag">
                <span className={"tag "+modalAlert.level}><span className="tdot"/>
                  {modalAlert.level==="high"?"高":modalAlert.level==="mid"?"中":"低"}
                </span>
              </div>
              <p>{modalAlert.summary}</p>
              <div className="alert-modal-meta font-mono">{modalAlert.source} · {modalAlert.time}</div>
            </div>
          </div>
        </div>
      )}
      {showReport && (
        <ReportModal
          query={query}
          kpis={kpis}
          summary={summary}
          react={reactSteps}
          citations={citations}
          onClose={()=>setShowReport(false)}
        />
      )}
      <ResearchTour
        onRunSample={handleTourRunSample}
        onReset={handleTourReset}
        hasResults={!!displayData}
        sampleFailed={tourSampleFailed}
      />
      <DocViewer doc={openDoc} onClose={()=>setOpenDoc(null)}/>
    </>
  );
}

// useSearchParams() 需包在 Suspense 內，否則 next build 靜態匯出 /research 會 bail-out。
export default function ResearchPage() {
  return (
    <Suspense fallback={null}>
      <ResearchPageInner />
    </Suspense>
  );
}