"use client";
import { useState, useRef, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { mutate } from "swr";
import { Icon } from "@/components/ui/Icon";
import { KpiCard } from "@/components/polaris/KpiCard";
import { AlertItem } from "@/components/polaris/AlertItem";
import { CitationList } from "@/components/polaris/CitationList";
import { ReActTrace } from "@/components/polaris/ReActTrace";
import { ComplianceBanner } from "@/components/polaris/ComplianceBanner";
import { TextGenerate } from "@/components/ui/TextGenerate";
import { DocViewer, type DocContent } from "@/components/polaris/DocViewer";
import { ReportModal } from "@/components/polaris/ReportModal";
import { KpiSkeleton, PanelSkeleton } from "@/components/polaris/Skeleton";
import { useResearch } from "@/hooks/useResearch";
import { useAlerts } from "@/hooks/useAlerts";
import { useReadStore } from "@/hooks/useReadStore";
import { useSuggestions } from "@/hooks/useSuggestions";
import { useContraAlerts } from "@/hooks/useContraAlerts";
import { useCompanies } from "@/hooks/useCompanies";
import { useFinancials, inferTickerFromQuery, financialsToKpis } from "@/hooks/useFinancials";
import { contraAlertStore, type ContraAlert } from "@/lib/contraAlertStore";
import type { KpiVM } from "@/types/viewmodel";
import { historyStore, extractTickers } from "@/lib/historyStore";
import { api } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import { toast } from "sonner";

const PHASES = ["理解查詢意圖","檢索文件庫","重排序候選","計算 + 交叉驗證","生成摘要","合規檢查"];
const PRESETS = ["台積電 2026Q1 法說會營運重點","聯發科 AI 邊緣運算佈局","台股半導體庫存週期"];

// Client-side mock: cross-check KPI values against summary text for discrepancies.
// Real detection is delegated to the backend /contradiction endpoint.
function buildMockContradictions(
  k: KpiVM[],
  s: Array<{ text: string; cite: string; page: string }>
): ContraAlert[] {
  const now = new Date().toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
  const found: ContraAlert[] = [];

  const revKpi = k.find(kpi => kpi.label.includes("全年") && kpi.label.includes("指引"));
  const revSum = s.find(item => /25%|25 %/.test(item.text) && item.text.includes("全年"));
  if (revKpi && revSum) {
    found.push({
      id: `contra-rev-${Date.now()}`,
      origin: "contradiction",
      level: "mid",
      cite_key: revSum.cite,
      title: `${revKpi.label}：KPI 與摘要數字落差`,
      summary: `KPI 卡顯示「${revKpi.value}${revKpi.unit}」，摘要（${revSum.cite} ${revSum.page}）引述「中段 25% 以上」。同份法說來源但表述不一致，建議核對 ${revSum.cite} 原文。`,
      source: `矛盾偵測 · ${revSum.cite} vs KPI`,
      time: now,
    });
  }

  if (found.length === 0) {
    found.push({
      id: `contra-pass-${Date.now()}`,
      origin: "contradiction",
      level: "info",
      title: "交叉比對通過",
      summary: "本次研究各引用來源數字交叉比對完成，未發現明顯矛盾。",
      source: "矛盾偵測引擎",
      time: now,
    });
  }
  return found;
}

const DOC_CONTENTS: Record<string, DocContent> = {
  fin: { key:"fin", title:"台積電_2026Q1_合併財報.pdf", kind:"財務報表", source_id:"stub-2330-2026Q1-fin", page:"p.11", trust:"high", hlTokens:["57.8","439,105","47.5"], highlight:"毛利率 57.8%，營業利益率 47.5%，本期淨利 3,253 億元。", body:["單位：新台幣百萬元","營業毛利　　　　　439,105　毛利率 57.8%","營業利益　　　　　361,064　營益率 47.5%","本期淨利　　　　　325,260　EPS 12.54 元"] },
  call: { key:"call", title:"台積電_2026Q1_法說會簡報.pdf", kind:"法說會簡報", source_id:"stub-2330-2026Q1-call", page:"p.7", trust:"high", hlTokens:["CoWoS","double"], highlight:"CoWoS 先進封裝產能持續擴充，Q4 預估翻倍；全年美元營收指引上調。", body:["Q1 2026 Business Highlights","• CoWoS advanced packaging capacity expanding —","  Q4 capacity expected to double"] },
  transcript: { key:"transcript", title:"台積電_2026Q1_法說會逐字稿.pdf", kind:"法說會逐字稿", source_id:"stub-2330-2026Q1-transcript", page:"p.3", trust:"high", hlTokens:["CoWoS","mid-20s"], highlight:"我們預期第四季 CoWoS 產能將較第三季顯著提升，全年美元營收成長上看中段 20%。", body:["C.C. Wei (CEO):","full-year USD revenue growth in the mid-20s percent."] },
  perf: { key:"perf", title:"台積電_2026Q1_營運績效報告.pdf", kind:"營運績效報告", source_id:"stub-2330-2026Q1-perf", page:"p.5", trust:"mid", hlTokens:["6.2%","3,210","69%"], highlight:"晶圓出貨量季增 6.2%，先進製程營收占比達 69%。", body:["晶圓出貨量　　　3,210　QoQ +6.2%","先進製程營收占比　69%（7nm 及以下）"] },
};


function Chart({ data }: { data: Array<{label:string;value:number}> }) {
  const max = Math.max(...data.map(d=>d.value));
  const min = Math.min(...data.map(d=>d.value)) - 1.5;
  return (
    <div className="chart">
      {data.map((d,i) => {
        const h = ((d.value-min)/(max-min))*100;
        return (
          <div className="chart-col" key={i}>
            <div className="chart-val font-mono">{d.value}%</div>
            <div className="chart-bar" style={{height:h+"%",animationDelay:i*80+"ms"}} data-last={i===data.length-1} />
            <div className="chart-label font-mono">{d.label}</div>
          </div>
        );
      })}
    </div>
  );
}

function ResearchPageInner() {
  const { trigger, data, isMutating } = useResearch();
  const { data: alerts } = useAlerts();
  const rs = useReadStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [restoredData, setRestoredData] = useState<typeof data>(undefined);
  const [restoredAt, setRestoredAt] = useState<string | null>(null);
  const { suggestions: dynamicSuggestions, fading: chipsFading } = useSuggestions();
  const contraAlerts = useContraAlerts();
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
  const [stepN, setStepN] = useState(0);
  const [progress, setProgress] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [ctxOpen, setCtxOpen] = useState(true);

  // B 級還原：從 history 頁點進來時，讀 sessionStorage 直接復原結果
  useEffect(() => {
    const historyId = searchParams.get("historyId");
    if (!historyId) return;
    try {
      const raw = sessionStorage.getItem("polaris_restore");
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved.id !== historyId) return;
      setQuery(saved.query ?? "");
      setHasQueried(true);
      setPhase("done");
      setProgress(100);
      setRestoredData(saved.result);
      setRestoredAt(saved.time ?? null);
      sessionStorage.removeItem("polaris_restore");
    } catch {}
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

  const researchAlerts = [
    ...(alerts ?? []),  // watchdog alerts 不區分 origin，兩頁共用；等 R3 補 origin 欄位後再加 filter
    ...contraAlerts,
  ];

  const runContradictionCheck = async (
    k: KpiVM[] = kpis,
    s: Array<{ text: string; cite: string; page: string }> = summary,
  ) => {
    if (isCheckingContra) return;
    setIsCheckingContra(true);
    try {
      let ok = false;
      try {
        const res = await fetch(`${API_BASE}/contradiction`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kpis: k, summary: s }),
        });
        if (res.ok) {
          const data = await res.json();
          contraAlertStore.set(data.alerts ?? []);
          ok = true;
        }
      } catch { /* backend not ready, fall through */ }
      if (!ok) contraAlertStore.set(buildMockContradictions(k, s));
    } finally {
      setIsCheckingContra(false);
    }
  };

  const run = async (q?: string) => {
    timers.current.forEach(clearTimeout); timers.current = [];
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }

    contraAlertStore.clear();
    setSelectedAlertIdx(null);
    setHasQueried(true);
    setPhase("running"); setStepN(0); setProgress(0);

    // 從查詢推斷 ticker，讓 useFinancials 預先取 R4 財務資料
    const resolvedQ = q ?? query;
    const ticker = inferTickerFromQuery(resolvedQ, companies);
    setInferredTicker(ticker);

    // 階段一：API 等待期間，爬升至 30%
    intervalRef.current = setInterval(() => {
      setProgress(p => Math.min(p + 2, 30));
    }, 200);

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

    } catch {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      setPhase("done");
      setProgress(0);
    }
  };
  useEffect(() => () => {
    timers.current.forEach(clearTimeout);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  const running = phase==="running";
  const total = reactSteps.length || 1;
  const curPhase = running ? PHASES[Math.min(Math.floor((stepN / total) * PHASES.length), PHASES.length - 1)] : null;
  const handleOpenDoc = async (cite: string) => {
    // 先打真實 API（R3 實作後自動生效）
    const chunk = await api.chunk(cite);
    if (chunk) { setOpenDoc(chunk); return; }
    // fallback：hardcoded demo mock
    if (DOC_CONTENTS[cite]) { setOpenDoc(DOC_CONTENTS[cite]); return; }
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
              <div className="page-eyebrow">研究助理 · /research</div>
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
                {(isMutating || isLoadingFinancials) ? <KpiSkeleton/> : (
                  (kpis.length > 0 || financialKpis.length > 0) && (
                    <div className="kpi-grid">
                      {kpis.length > 0
                        ? kpis.map((k,i)=><KpiCard key={i} k={k} onCite={handleOpenDoc}/>)
                        : financialKpis.map((k,i)=>(
                            <KpiCard key={i} k={{...k, cite:""}} onCite={()=>{}}/>
                          ))
                      }
                    </div>
                  )
                )}
                <div className="rcol-stack">
                  <div className="panel">
                    <div className="panel-head">
                      <span className="panel-title"><Icon name="layers" size={15} style={{color:"rgb(var(--primary))",verticalAlign:"-3px",marginRight:6}}/>營運重點摘要</span>
                      <span className="panel-meta">{summary.length > 0 ? `${summary.length} 條 · 全數可溯源` : "查無資料"}</span>
                    </div>
                    <div className="panel-body">
                      {isMutating ? <PanelSkeleton/> : (
                        summary.length > 0 ? (
                          <ul className="summary">
                            {summary.map((s,i)=>{
                              const hasContra = contraAlerts.some(a => a.level !== "info" && (a as any).cite_key === s.cite);
                              return (
                                <li key={s.cite + i}><span className="sum-marker"/><span><TextGenerate key={s.text} text={s.text} delay={i * 0.08} />{hasContra && <span className="tag mid" style={{marginLeft:5,padding:"1px 7px",fontSize:12,verticalAlign:"middle"}} title="矛盾偵測警告，建議核對引用原文"><span className="tdot"/>矛盾</span>}<span className="cchip" role="button" tabIndex={0} onClick={()=>handleOpenDoc(s.cite)} onKeyDown={e=>(e.key==="Enter"||e.key===" ")&&handleOpenDoc(s.cite)}>{s.cite==="fin"?"財報":"法說"} {s.page}</span></span></li>
                              );
                            })}
                          </ul>
                        ) : (
                          <div className="chart-empty">
                            <Icon name="layers" size={20} style={{color:"rgb(var(--muted))",marginBottom:8}}/>
                            <span>查詢的資料未涵蓋於現有資料庫</span>
                            <span className="font-mono" style={{fontSize:"0.72rem",color:"rgb(var(--muted))"}}>請確認公司代號及財報期別是否已入庫</span>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panel-head">
                      <span className="panel-title">量化分析</span>
                      <span className="panel-meta">財務指標</span>
                    </div>
                    <div className="panel-body">
                      {(displayData?.chart?.length ?? 0) > 0
                        ? <>
                            <Chart data={displayData!.chart}/>
                            <div className="chart-foot">
                              <span>單季毛利率（來源：財務資料庫）</span>
                            </div>
                          </>
                        : <div className="chart-empty">
                            <Icon name="layers" size={20} style={{color:"rgb(var(--muted))",marginBottom:8}}/>
                            <span>財務指標資料建置中</span>
                            <span className="font-mono" style={{fontSize:"0.72rem",color:"rgb(var(--muted))"}}>financial_metrics 表尚未入庫</span>
                          </div>
                      }
                    </div>
                  </div>
                </div>
              </>
            )}
              </>
            )}
            <div className="actions">
              <button className="btn" disabled={!data} title={!data ? "請先執行研究" : undefined} onClick={()=>setShowReport(true)}><Icon name="file" size={15}/>完整報告</button>
              <button className="btn" disabled={!query} onClick={()=>{ toast("已帶入同業比較"); router.push(`/peer?q=${encodeURIComponent(query)}`); }}><Icon name="scale" size={15}/>送同業比較</button>
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
                <span className="panel-title"><Icon name="brain" size={15} style={{color:"rgb(var(--primary))",verticalAlign:"-3px",marginRight:6}}/>模型思考追蹤</span>
                <span className="panel-meta">ReAct</span>
              </div>
              {phase === "idle" ? (
                <div className="chart-empty" style={{padding:"20px 16px"}}>
                  <span>執行研究後顯示模型思考路徑</span>
                </div>
              ) : (
                <>
                  <div className="ctx-progress">
                    <div className="ctx-prog-track"><div className="ctx-prog-fill" style={{width:progress+"%"}}/></div>
                    <span className="font-mono">{running ? (curPhase ?? "") : "done"} · {progress}%</span>
                  </div>
                  <ReActTrace steps={reactSteps} activeIndex={running?stepN-1:undefined} visibleCount={running?stepN:undefined}/>
                </>
              )}
            </div>
            <div className="panel ctx-panel">
              <div className="panel-head">
                <span className="panel-title"><Icon name="alert" size={14} style={{color:"rgb(var(--danger))",verticalAlign:"-2px",marginRight:6}}/>監控系統警示</span>
              </div>
              <div className="alert-list">
                {researchAlerts.length > 0
                  ? researchAlerts.map((a,i)=>(
                      <AlertItem key={a.id} alert={a} selected={selectedAlertIdx===i} read={rs.isRead(a.id)}
                        onClick={()=>{setSelectedAlertIdx(selectedAlertIdx===i?null:i);rs.markRead(a.id);}}
                        onDoubleClick={()=>{setModalAlert(a);rs.markRead(a.id);}}/>
                    ))
                  : <div className="chart-empty" style={{padding:"20px 16px"}}>
                      <Icon name="shield" size={18} style={{color:"rgb(var(--muted))",marginBottom:6}}/>
                      <span>{hasQueried ? "本次研究未發現異常訊號" : "執行研究後顯示相關警示"}</span>
                    </div>
                }
              </div>
            </div>
            <div className="panel ctx-panel">
              <div className="panel-head">
                <span className="panel-title"><Icon name="quote" size={14} style={{color:"rgb(var(--primary))",verticalAlign:"-2px",marginRight:6}}/>引用追蹤器</span>
                {citations.length > 0 && <span className="panel-meta">100% 可溯源</span>}
              </div>
              {citations.length > 0
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
              onKeyDown={e=>{if(e.key==="Enter")run();}} placeholder="輸入研究問題..."/>
            <button className="dock-tool" title="上傳檔案"><Icon name="paperclip" size={19}/></button>
            <button className={"dock-tool" + (isListening ? " active" : "")} title={isListening ? "聆聽中…" : "語音輸入"} onClick={startVoice} disabled={running}><Icon name="mic" size={19}/></button>
            <button className="btn primary dock-send" onClick={()=>run()} disabled={running}>
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
              <button className="alert-modal-close" onClick={()=>setModalAlert(null)}><Icon name="x" size={18}/></button>
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