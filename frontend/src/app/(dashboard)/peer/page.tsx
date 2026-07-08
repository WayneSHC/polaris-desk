"use client";
import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { mutate } from "swr";
import { historyStore } from "@/lib/historyStore";
import { api } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { AlertItem } from "@/components/polaris/AlertItem";
import { CitationList } from "@/components/polaris/CitationList";
import { ComplianceBanner } from "@/components/polaris/ComplianceBanner";
import { DocViewer, type DocContent } from "@/components/polaris/DocViewer";
import { ReportModal } from "@/components/polaris/ReportModal";
import { useReadStore } from "@/hooks/useReadStore";
import { useCompanies } from "@/hooks/useCompanies";
import { useContraAlerts } from "@/hooks/useContraAlerts";
import { useSuggestions } from "@/hooks/useSuggestions";
import { toast } from "sonner";
import { contraAlertStore, type ContraAlert } from "@/lib/contraAlertStore";
import { parseQuery } from "@/lib/peer";
import { useFinancials, type FinancialRow } from "@/hooks/useFinancials";
import { usePeriods } from "@/hooks/usePeriods";
import { EmptyState } from "@/components/ui/EmptyState";
import { fmtYoy, fmtFinNum } from "@/lib/formatters";
import { scoreLabel, sortByRelevance, sortFinancialByRelevance } from "@/lib/queryRelevance";
import { hasValue, toLabel } from "@/lib/fieldUtils";
import { peerCitations } from "@/lib/peer-result";
import type { PeerCompareResult, PeerCompareTrendPoint, PeerCallNorm } from "@/types/api";
import type { CompanyVM, KpiVM, SummaryItemVM, CitationTrackerVM } from "@/types/viewmodel";
import { fmtTrendValue } from "@/lib/chartUtils";

const PRESETS = [
  "比較台積電與聯發科毛利率",
  "台積電 vs 鴻海 法說會重點",
  "聯發科與聯詠估值比較",
];
const PHASES = ["解析查詢意圖","檢索 A 公司文件","檢索 B 公司文件","交叉比對指標","生成比較摘要","合規檢查"];

// ── 數值＋單位拆分元件（保證個位數垂直對齊）─────────────────
function PtNum({ value }: { value: string }) {
  const m = value.match(/^([+\-]?[\d,\.]+)(.*)$/);
  if (!m) return <>{value}</>;
  const [, num, unit] = m;
  return (
    <>
      <span className="ptcell-num">{num}</span>
      {unit && <span className="ptcell-unit">{unit.trim()}</span>}
    </>
  );
}

// ── Trend Panel ──────────────────────────────────────────────

function TrendPanel({ aName, bName, trend }: { aName: string; bName: string; trend: PeerCompareTrendPoint[] }) {
  const allMetrics = [...new Set(trend.map(t => t.metric))];
  const metricsWithData = allMetrics.filter(metric =>
    trend.some(t => t.metric === metric && (t.a_value !== null || t.b_value !== null))
  );
  if (!metricsWithData.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">
            <Icon name="arrowUp" size={15} style={{ color: "rgb(var(--primary))", verticalAlign: "-3px", marginRight: 6 }}/>
            跨期趨勢
          </span>
          <span className="panel-meta">無跨期資料</span>
        </div>
        <div className="chart-empty" style={{ padding: "28px 16px" }}>
          <span>{aName} vs {bName} · 無跨期趨勢資料（需兩期以上相同指標）</span>
        </div>
      </div>
    );
  }
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">
          <Icon name="arrowUp" size={15} style={{ color: "rgb(var(--primary))", verticalAlign: "-3px", marginRight: 6 }}/>
          跨期趨勢
        </span>
        <span className="panel-meta">{metricsWithData.map(toLabel).join(" / ")}</span>
      </div>
      <div className="panel-body">
        {metricsWithData.map(metric => {
          const label = toLabel(metric);
          const pts = trend
            .filter(t => t.metric === metric && (t.a_value !== null || t.b_value !== null))
            .sort((a, b) => a.period.localeCompare(b.period));
          return (
            <div key={metric} style={{ marginBottom: 16 }}>
              <div className="fchart-metric-label">{label}</div>
              <div className="ptable-wrap">
                <table className="ptable">
                  <thead><tr><th>期間</th><th className="num">{aName}</th><th className="num">{bName}</th></tr></thead>
                  <tbody>
                    {pts.map(pt => (
                      <tr key={pt.period}>
                        <td className="font-mono">{pt.period}</td>
                        <td className="num"><PtNum value={fmtTrendValue(pt.a_value, label)} /></td>
                        <td className="num"><PtNum value={fmtTrendValue(pt.b_value, label)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Peer Summary Panel ────────────────────────────────────────

function PeerSummaryPanel({ summary }: { summary: string }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">
          <Icon name="layers" size={15} style={{ color: "rgb(var(--primary))", verticalAlign: "-3px", marginRight: 6 }}/>
          比較摘要
        </span>
      </div>
      <div className="panel-body">
        <p className="peer-sum-text">{summary}</p>
      </div>
    </div>
  );
}

// ── 法說會看法矩陣（主題 × 兩家立場／語氣；資料來自 /peer-compare calls）──

function PeerCallCell({ side }: { side: PeerCallNorm["a"] }) {
  const tone = side.tone === "pos" || side.tone === "neg" ? side.tone : "neu";
  return (
    <div className="cm-cell">
      <span className={`stance ${tone}`}>{side.stance}</span>
      <p className="cm-quote">{side.quote || "—"}</p>
    </div>
  );
}

function PeerCallMatrix({ result, aName, bName }: { result: PeerCompareResult; aName: string; bName: string }) {
  const rows = result.calls.filter(c => c.a.quote || c.b.quote);
  if (!rows.length) return null;
  const aLabel = aName || result.a_ticker;
  const bLabel = bName || result.b_ticker;
  // 法說退回提示：請求季（如 2026Q2）季底剛過尚無法說，後端退回最新已公布季（如 2026Q1）。
  // calls_period 有值且 ≠ 請求季時，明示法說實際來源季，避免誤以為法說也是請求季。
  const callsFromOtherQuarter = result.calls_period && result.calls_period !== result.fiscal_period;
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">
          <Icon name="quote" size={14} style={{ color: "rgb(var(--primary))", verticalAlign: "-2px", marginRight: 6 }}/>
          法說會看法
        </span>
        {callsFromOtherQuarter && (
          <span className="panel-meta" title={`${result.fiscal_period} 尚無法說會資料，改用最新已公布季 ${result.calls_period}`}>
            法說來源：{result.calls_period}
          </span>
        )}
      </div>
      <div className="panel-body">
        <div className="cmatrix">
          <div className="cm-row cm-headrow">
            <div className="cm-th">主題</div>
            <div className="cm-th">{aLabel}</div>
            <div className="cm-th">{bLabel}</div>
          </div>
          {rows.map((c, i) => (
            <div className="cm-row" key={i}>
              <div className="cm-topic">{c.topic}</div>
              <PeerCallCell side={c.a}/>
              <PeerCallCell side={c.b}/>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Live KPI Grid (from /peer-compare response) ──────────────

function PeerKpiGridLive({ result, aName, bName, queryHint = "" }: {
  result: PeerCompareResult;
  aName: string;
  bName: string;
  queryHint?: string;
}) {
  const [showAll, setShowAll] = useState(false);

  const validKpis = result.kpis.filter(k => hasValue(k.a.v) || hasValue(k.b.v));
  if (!validKpis.length) {
    return <EmptyState message={`所選季度無財務指標資料（${result.fiscal_period}）`} style={{padding:"20px 16px"}}/>;
  }

  const sorted = queryHint ? sortByRelevance(validKpis, queryHint) : validKpis;
  const topByQuery = queryHint ? sorted.filter(k => scoreLabel(k.label, queryHint) > 0) : [];
  const restByQuery = queryHint ? sorted.filter(k => scoreLabel(k.label, queryHint) === 0) : [];
  const querySplit = topByQuery.length > 0 && restByQuery.length > 0;
  const top = querySplit ? topByQuery : sorted.slice(0, 5);
  const rest = querySplit ? restByQuery : sorted.slice(5);
  const showSplit = querySplit || sorted.length > 5;
  const displayKpis = showSplit && !showAll ? top : sorted;

  const renderRow = (kpi: typeof result.kpis[0], i: number) => (
    <tr key={i}>
      <td className="pt-metric">{kpi.label}</td>
      <td className={`num${kpi.better === "a" ? " text-[rgb(var(--primary-bright))] font-bold" : ""}`}><PtNum value={fmtFinNum(kpi.a.v)} /></td>
      <td className={`num${kpi.better === "b" ? " text-[rgb(var(--primary-bright))] font-bold" : ""}`}><PtNum value={fmtFinNum(kpi.b.v)} /></td>
      <td className="num pt-note">{kpi.diff && kpi.diff !== "—" ? `${kpi.better === "a" ? aName : bName} +${kpi.diff}` : "—"}</td>
    </tr>
  );

  return (
    <>
      <div className="ptable-wrap">
        <table className="ptable" style={{marginBottom: 4}}>
          <thead>
            <tr>
              <th>指標</th>
              <th className="num">{aName}</th>
              <th className="num">{bName}</th>
              <th className="num">領先</th>
            </tr>
          </thead>
          <tbody>
            {displayKpis.map((kpi, i) => renderRow(kpi, i))}
          </tbody>
        </table>
      </div>
      {showSplit && (
        <button
          className="btn ghost"
          style={{ fontSize: 13, padding: "3px 12px", marginTop: 2 }}
          onClick={() => setShowAll(v => !v)}
        >
          {showAll ? `收起 · 顯示前 ${top.length} 項` : `其他 ${rest.length} 項指標`}
        </button>
      )}
    </>
  );
}

// ── Fallback KPI Grid (uses /financials, period-aware) ────────

function getMetricForPeriod(rows: FinancialRow[], metricId: string, period: string, month?: number | null): number | null {
  if (month != null) {
    const hit = rows.find(r => r.fiscal_period === period && r.metric_id === metricId && r.month === month);
    if (hit != null) return hit.value;
  }
  return rows.find(r => r.fiscal_period === period && r.metric_id === metricId)?.value ?? null;
}



function PeerKpiGridFallback({ aName, bName }: {
  aName: string; bName: string; aTicker: string; bTicker: string; fiscalPeriod: string; selectedMonth: number | null;
}) {
  return (
    <table className="ptable" style={{ marginBottom: 4 }}>
      <thead>
        <tr>
          <th>指標</th>
          <th className="num">{aName || "—"}</th>
          <th className="num">{bName || "—"}</th>
          <th className="num">領先</th>
        </tr>
      </thead>
      <tbody>
        {[1, 2, 3].map(i => (
          <tr key={i}>
            <td className="pt-metric"><span className="skeleton" style={{ display:"inline-block", width:60, height:14, borderRadius:4, background:"rgb(var(--muted)/.15)" }}/></td>
            <td className="num"><span className="skeleton" style={{ display:"inline-block", width:48, height:14, borderRadius:4, background:"rgb(var(--muted)/.15)" }}/></td>
            <td className="num"><span className="skeleton" style={{ display:"inline-block", width:48, height:14, borderRadius:4, background:"rgb(var(--muted)/.15)" }}/></td>
            <td className="num"/>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Financial Block (from /peer-compare kpis) ─────────────────

function FinancialBlock({ result, aName, bName, queryHint = "" }: {
  result: PeerCompareResult; aName: string; bName: string; queryHint?: string;
}) {
  const [showAll, setShowAll] = useState(false);

  const validFinancial = result.financial.filter(f => hasValue(f.a.v) || hasValue(f.b.v));
  if (!validFinancial.length) {
    return (
      <div className="panel">
        <div className="panel-head"><span className="panel-title">損益指標對比</span><span className="panel-meta">{result.fiscal_period}</span></div>
        <div className="panel-body"><EmptyState message="所選季度無財務指標資料" style={{padding:"20px 16px"}} /></div>
      </div>
    );
  }

  const sorted = queryHint ? sortFinancialByRelevance(validFinancial, queryHint) : validFinancial;
  const topByQuery = queryHint ? sorted.filter(f => scoreLabel(f.metric, queryHint) > 0) : [];
  const restByQuery = queryHint ? sorted.filter(f => scoreLabel(f.metric, queryHint) === 0) : [];
  const querySplit = topByQuery.length > 0 && restByQuery.length > 0;
  const top = querySplit ? topByQuery : sorted.slice(0, 5);
  const rest = querySplit ? restByQuery : sorted.slice(5);
  const showSplit = querySplit || sorted.length > 5;
  const display = showSplit && !showAll ? top : sorted;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">損益指標對比</span>
        <span className="panel-meta">{result.fiscal_period}</span>
      </div>
      <div className="panel-body">
        <div className="ptable-wrap">
          <table className="ptable">
            <thead><tr><th>指標</th><th className="num">{aName}</th><th className="num">{bName}</th><th className="num">差異</th></tr></thead>
            <tbody>
              {display.map((f, i) => (
                <tr key={i}>
                  <td className="pt-metric">{toLabel(f.metric)}</td>
                  <td className={`num${f.better === "a" ? " text-[rgb(var(--primary-bright))] font-bold" : ""}`}><PtNum value={fmtFinNum(f.a.v)} /></td>
                  <td className={`num${f.better === "b" ? " text-[rgb(var(--primary-bright))] font-bold" : ""}`}><PtNum value={fmtFinNum(f.b.v)} /></td>
                  <td className="num pt-note">{f.note.replace("差異 ", "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {showSplit && (
          <button className="btn ghost" style={{ fontSize: 13, padding: "3px 12px", marginTop: 6 }}
            onClick={() => setShowAll(v => !v)}>
            {showAll ? `收起 · 顯示前 ${top.length} 項` : `其他 ${rest.length} 項指標`}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Company Slot ──────────────────────────────────────────────

interface SlotProps {
  company: CompanyVM | undefined;
  open: boolean;
  search: string;
  options: CompanyVM[];
  placeholder: string;
  onToggle: () => void;
  onSearch: (v: string) => void;
  onSelect: (id: string) => void;
}
function CompanySlot({ company, open, search, options, placeholder, onToggle, onSearch, onSelect }: SlotProps) {
  const filtered = options.filter(c => (c.name ?? "").includes(search) || c.id.includes(search));
  return (
    <div className="cpick-wrap">
      <button className={"cpick-btn"+(company ? "" : " empty")} onClick={onToggle}>
        {company?.name ?? placeholder}
        <Icon name="chevD" size={12} style={{marginLeft:5,opacity:.6}}/>
      </button>
      {open && (
        <div className="cpick-dropdown">
          <input className="cpick-search" placeholder="搜尋公司..." value={search}
            onChange={e => onSearch(e.target.value)} autoFocus/>
          {filtered.length === 0
            ? <div className="cpick-empty">無符合結果</div>
            : filtered.map(c => (
                <button key={c.id} className={"cpick-option"+(company?.id===c.id?" selected":"")}
                  onClick={() => onSelect(c.id)}>
                  <span>{c.name}</span>
                  <span className="font-mono cpick-ticker">{c.id}</span>
                </button>
              ))
          }
        </div>
      )}
    </div>
  );
}

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

// ── Page ──────────────────────────────────────────────────────

function PeerPageInner() {
  const searchParams = useSearchParams();
  const rs = useReadStore();
  const companies = useCompanies();
  const contraAlerts = useContraAlerts("peer");
  const { suggestions: dynamicSuggestions, fading: chipsFading } = useSuggestions({ mode: "peer" });
  const chips = dynamicSuggestions ?? PRESETS;

  const dbPeriods = usePeriods();

  const [aId, setAId] = useState("");
  const [bId, setBId] = useState("");
  const [fiscalPeriod, setFiscalPeriod] = useState("");
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);

  const { rows: aFinRows } = useFinancials(aId || null);
  const { rows: bFinRows } = useFinancials(bId || null);
  const availablePeriods = (() => {
    const aPeriods = new Set(aFinRows.map(r => r.fiscal_period).filter((p): p is string => !!p));
    const bPeriods = new Set(bFinRows.map(r => r.fiscal_period).filter((p): p is string => !!p));
    let result: string[];
    if (aPeriods.size > 0 && bPeriods.size > 0) {
      // 兩家都有資料：只顯示雙方都有的期別（交集），避免選到一邊是空的
      result = [...aPeriods].filter(p => bPeriods.has(p)).sort().reverse();
    } else {
      // 只有一家或都沒有：顯示有資料的期別（聯集）
      result = [...new Set([...aPeriods, ...bPeriods])].sort().reverse();
    }
    return result.length > 0 ? result : dbPeriods.map(p => p.period);
  })();

  // 年/季/月拆分 derived values
  const fiscalYear = fiscalPeriod.slice(0, 4);
  const fiscalQuarter = fiscalPeriod.slice(4); // "Q1" ~ "Q4"
  const availableYears = [...new Set(availablePeriods.map(p => p.slice(0, 4)))].sort().reverse();
  const availableQuartersForYear = [...new Set(
    availablePeriods.filter(p => p.startsWith(fiscalYear)).map(p => p.slice(4))
  )].sort().reverse();
  const periodInfoMap = new Map(dbPeriods.map(p => [p.period, p]));
  // 月份從 BQ 實際資料推導（只顯示有資料的月份），不 hardcode
  const availableMonthsForPeriod = (() => {
    const aMonths = new Set(
      aFinRows.filter(r => r.fiscal_period === fiscalPeriod && r.month != null).map(r => r.month as number)
    );
    const bMonths = new Set(
      bFinRows.filter(r => r.fiscal_period === fiscalPeriod && r.month != null).map(r => r.month as number)
    );
    const allMonths = new Set([...aMonths, ...bMonths]);
    return [...allMonths].sort((a, b) => a - b);
  })();


  const [query, setQuery] = useState("");
  const [hasQueried, setHasQueried] = useState(false);
  const [peerResult, setPeerResult] = useState<PeerCompareResult | null>(null);
  const [parseMsg, setParseMsg] = useState({ ignored:[] as string[], unknown:[] as string[] });
  // 使用者在查詢中指名的指標（如「EPS」）；若該指標於解析出的期別無資料，顯示提示而非靜默退回月營收
  const [requestedMetric, setRequestedMetric] = useState<{ id: string; label: string } | null>(null);
  // 指名指標在當前結果期別是否雙方皆無資料（如 EPS 於本季——季報尚未公布）。
  // 同業比較只取雙方交集，任一方缺即無法比較 → 提示而非靜默顯示其他指標。
  const metricNotice = (() => {
    if (!requestedMetric || !peerResult) return null;
    const period = peerResult.fiscal_period;
    const aHas = aFinRows.some(r => r.fiscal_period === period && r.metric_id === requestedMetric.id);
    const bHas = bFinRows.some(r => r.fiscal_period === period && r.metric_id === requestedMetric.id);
    if (aHas && bHas) return null;
    return `「${requestedMetric.label}」於 ${period} 尚無資料（季報未公布），以下顯示該期可得指標。`;
  })();
  const [selectedAlertIdx, setSelectedAlertIdx] = useState<number|null>(null);
  const [modalAlert, setModalAlert] = useState<any>(null);
  const [openDoc, setOpenDoc] = useState<DocContent|null>(null);
  const [openSlot, setOpenSlot] = useState<"a"|"b"|null>(null);
  const [slotSearch, setSlotSearch] = useState("");
  const [phase, setPhase] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [showReport, setShowReport] = useState(false);
  const [ctxOpen, setCtxOpen] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [thinkingSec, setThinkingSec] = useState(0);
  const [apiError, setApiError] = useState<string | null>(null);
  // A 級重跑：從對話紀錄退回 ?q= 進來時暫存查詢，等 companies / fiscalPeriod 載好再跑
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);
  const historyEntryConsumedRef = useRef(false);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  // Stable ref for current query/ticker/period to avoid stale closures
  const runParamsRef = useRef({ aId: "", bId: "", fiscalPeriod: "", query: "" });

  useEffect(() => () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  useEffect(() => {
    if (phase !== "running") { setThinkingSec(0); return; }
    setThinkingSec(0);
    const t = setInterval(() => setThinkingSec(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  useEffect(() => {
    if (!openSlot) return;
    const handle = (e: MouseEvent) => {
      if (slotRef.current && !slotRef.current.contains(e.target as Node)) {
        setOpenSlot(null); setSlotSearch("");
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [openSlot]);

  // 從對話紀錄點進來時，讀 sessionStorage 還原比較結果（B 級）；
  // 還原不成（localStorage 紀錄無整包 result、或刷新後 sessionStorage 已清）
  // 退回 A 級：帶 ?q= 自動重跑一次查詢，不再停在空白初始頁
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
          if (saved.id === historyId && saved.page === "peer") {
            const result = saved.result as PeerCompareResult;
            setQuery(saved.query ?? "");
            setAId(result.a_ticker ?? "");
            setBId(result.b_ticker ?? "");
            if (result.fiscal_period) setFiscalPeriod(result.fiscal_period);
            setHasQueried(true);
            setPhase("done");
            setProgress(100);
            setPeerResult(result);
            sessionStorage.removeItem("polaris_restore");
            return;
          }
        }
      } catch {}
    }
    const q = searchParams.get("q");
    if (q) {
      setQuery(q);
      setPendingQuery(q);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A 級重跑：runQuery 的公司辨識吃 companies、期別 fallback 吃 fiscalPeriod（BQ 期別載入後才有值），
  // 兩者就緒才執行，否則會靜默 no-op（辨識不到公司就 return）
  useEffect(() => {
    if (!pendingQuery || companies.length === 0 || !fiscalPeriod) return;
    const q = pendingQuery;
    setPendingQuery(null);
    runQuery(q);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuery, companies, fiscalPeriod]);

  // 初始化：dbPeriods 從 BQ 載入後，若 fiscalPeriod 還是空（未選過）就設成最新期別
  useEffect(() => {
    if (dbPeriods.length > 0 && !fiscalPeriod) {
      setFiscalPeriod(dbPeriods[0].period);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dbPeriods]);

  // Auto-select latest period when BQ financials load and current selection is stale
  useEffect(() => {
    if (availablePeriods.length > 0 && !availablePeriods.includes(fiscalPeriod)) {
      setFiscalPeriod(availablePeriods[0]);
      setSelectedMonth(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availablePeriods]);

  const A = companies.find(c => c.id === aId);
  const B = companies.find(c => c.id === bId);
  const running = phase === "running";

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
      runQuery(text);
    };
    rec.start();
  };

  const toggleSlot = (slot: "a"|"b") => { setOpenSlot(prev => prev===slot ? null : slot); setSlotSearch(""); };
  const selectCompany = (slot: "a"|"b", id: string) => {
    if (slot==="a") setAId(id); else setBId(id);
    setOpenSlot(null); setSlotSearch("");
  };

  const runContraCheck = async (_aName: string, _bName: string) => {
    contraAlertStore.clear("peer");
  };

  const runQueryWith = useCallback(async (
    q: string,
    nextAId: string,
    nextBId: string,
    period: string,
    nextA: CompanyVM | undefined,
    nextB: CompanyVM | undefined,
    month: number | null = null,
  ) => {
    if (running) return;
    if (!nextAId || !nextBId) return;

    runParamsRef.current = { aId: nextAId, bId: nextBId, fiscalPeriod: period, query: q };

    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    contraAlertStore.clear("peer");
    setSelectedAlertIdx(null);
    setHasQueried(true);
    setApiError(null);
    setPeerResult(null);
    setPhase("running"); setProgress(0);

    intervalRef.current = setInterval(() => {
      setProgress(p => Math.min(p + 2, 85));
    }, 300);

    try {
      const result = await api.peerCompare({
        a_ticker: nextAId,
        b_ticker: nextBId,
        fiscal_period: period,
        question: q || `比較 ${nextA?.name ?? nextAId} 與 ${nextB?.name ?? nextBId}`,
        ...(month != null ? { month } : {}),
      });

      clearInterval(intervalRef.current!); intervalRef.current = null;
      setProgress(100);
      setPeerResult(result);

      historyStore.write({ page: "peer", query: q, tags: [nextAId, nextBId].filter(Boolean) });
      api.postHistory("peer", q, [nextAId, nextBId].filter(Boolean), result as unknown as Record<string, unknown>);
      mutate("history");
      toast.success("已儲存至對話紀錄");

      setPhase("done");
      runContraCheck(nextA?.name ?? "", nextB?.name ?? "");
    } catch (err) {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      setPhase("done"); setProgress(0);
      setApiError(err instanceof Error ? err.message : String(err));
      toast.error("API 錯誤，請稍後重試");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  const runQuery = async (q?: string) => {
    const text = q ?? query;
    // parseQuery 取 period / tab / year / metric
    const res = parseQuery(text);
    setRequestedMetric(res.metric ? { id: res.metric, label: res.metricLabel ?? res.metric } : null);

    // 動態公司辨識：比對 BQ company_dim 的 ticker、company_name、aliases（涵蓋全部 20 家）
    const dynMatches = companies.filter(c =>
      text.includes(c.id) ||
      (c.name && text.includes(c.name)) ||
      c.aliases.some(alias => alias && text.includes(alias))
    );

    // 優先序：動態辨識 > parseQuery alias > 選擇框
    const ok = res.ordered.filter(o => o.status === "ok");
    const nextAId = dynMatches[0]?.id ?? ok[0]?.id ?? aId;
    const nextBId = dynMatches[1]?.id ?? ok[1]?.id ?? bId;
    if (!nextAId || !nextBId) return;

    if (dynMatches[0]) setAId(dynMatches[0].id);
    else if (ok[0]) setAId(ok[0].id);
    if (dynMatches[1]) setBId(dynMatches[1].id);
    else if (ok[1]) setBId(ok[1].id);

    const normPeriod = res.period.replace(/\s+/g, "");
    // 若只解析到年份（無季別），從 availablePeriods 取該年最新一季
    const yearFallback = res.year
      ? (availablePeriods.find(p => p.startsWith(String(res.year))) ?? fiscalPeriod)
      : null;
    const period = availablePeriods.includes(normPeriod)
      ? normPeriod
      : (yearFallback ?? fiscalPeriod);
    if (availablePeriods.includes(normPeriod)) setFiscalPeriod(normPeriod);
    else if (yearFallback) setFiscalPeriod(yearFallback);
    setParseMsg({
      ignored: dynMatches.slice(2).map(o => o.name),
      unknown: res.ordered.filter(o => o.status === "nodata").map(o => o.name),
    });

    const nextA = companies.find(c => c.id === nextAId);
    const nextB = companies.find(c => c.id === nextBId);

    await runQueryWith(text, nextAId, nextBId, period, nextA, nextB, selectedMonth);
  };

  // Re-query when period changes (only if already queried and tickers are set)
  // period 切換一律重置月份為全季（null），由呼叫端的 setSelectedMonth(null) + 傳 null 保持一致
  const changePeriod = async (p: string, month: number | null = null) => {
    setFiscalPeriod(p);
    if (!hasQueried || !aId || !bId || running) return;
    const nextA = companies.find(c => c.id === aId);
    const nextB = companies.find(c => c.id === bId);
    await runQueryWith(query, aId, bId, p, nextA, nextB, month);
  };

  const changeYear = async (year: string) => {
    const samePeriod = `${year}${fiscalQuarter}`;
    const valid = availablePeriods.includes(samePeriod)
      ? samePeriod
      : (availablePeriods.find(p => p.startsWith(year)) ?? availablePeriods[0]);
    setSelectedMonth(null);
    await changePeriod(valid, null);
  };

  const changeQuarter = async (q: string) => {
    setSelectedMonth(null);
    await changePeriod(`${fiscalYear}${q}`, null);
  };

  const changeMonth = async (m: number | null) => {
    setSelectedMonth(m);
    if (!hasQueried || !aId || !bId || running) return;
    const nextA = companies.find(c => c.id === aId);
    const nextB = companies.find(c => c.id === bId);
    await runQueryWith(query, aId, bId, fiscalPeriod, nextA, nextB, m);
  };


  const readyToCompare = aId && bId;
  const pageTitle = A && B ? `${A.name} vs ${B.name} — 同業對比` : "同業比較";
  const optionsForA = companies.filter(c => c.id !== bId);
  const optionsForB = companies.filter(c => c.id !== aId);

  // Citations for tracker & report modal
  const citations: CitationTrackerVM[] = peerCitations(peerResult).map((src, i) => ({
    ix: String(i + 1),
    label: src.label,
    detail: src.detail,
    cite: src.sourceId,
    snippet: src.snippet,
    period: "",
  }));

  const handleOpenDoc = async (cite: string) => {
    if (!cite) return;
    const chunk = await api.chunk(cite);
    if (chunk) { setOpenDoc(chunk); return; }
    const vm = citations.find(c => c.cite === cite);
    if (!vm) { toast.error("查無此文件原文"); return; }
    setOpenDoc({
      key: cite,
      title: vm.label,
      kind: "citation",
      source_id: cite,
      page: vm.detail,
      trust: "mid",
      highlight: vm.snippet || vm.detail || "",
      body: [vm.snippet || vm.detail || vm.label].filter(Boolean),
    });
  };

  // Report modal KPIs (from real response or empty)
  const reportKpis: KpiVM[] = peerResult?.kpis.flatMap(k => ([
    { label:`${A?.name ?? peerResult.a_ticker} ${k.label}`, value: k.a.v, unit:"", delta:"", trend: k.better === "a" ? "up" as const : "down" as const, cite: k.a.citations[0]?.src ?? "" },
    { label:`${B?.name ?? peerResult.b_ticker} ${k.label}`, value: k.b.v, unit:"", delta:"", trend: k.better === "b" ? "up" as const : "down" as const, cite: k.b.citations[0]?.src ?? "" },
  ])) ?? [];

  const reportSummary: SummaryItemVM[] = peerResult
    ? [{ text: peerResult.summary, cite: "", page: "" }]
    : [];

  const peerAlerts = contraAlerts.filter(a => a.level !== "info");

  return (
    <>
      <div className="page-scroll">
        <div className={"page peer-page research-layout" + (ctxOpen ? "" : " ctx-collapsed")}>
          <div className="rcol-main">
            <div className="page-head">
              <div className="page-eyebrow">同業比較 · peer</div>
              <h1 className="page-title">{pageTitle}</h1>
              <p className="page-desc">選擇兩間公司後送出查詢，或直接輸入「比較 A 與 B」由系統解析。</p>
            </div>

            {/* Company Slot Toolbar */}
            <div className="peer-toolbar" ref={slotRef}>
              <div className="ptb-vs">
                <CompanySlot
                  company={A} open={openSlot==="a"} search={slotSearch}
                  options={optionsForA} placeholder="選擇主體公司"
                  onToggle={() => toggleSlot("a")} onSearch={setSlotSearch}
                  onSelect={id => selectCompany("a", id)}
                />
                <span className="ptb-x font-mono">vs</span>
                <CompanySlot
                  company={B} open={openSlot==="b"} search={slotSearch}
                  options={optionsForB} placeholder="選擇比較對象"
                  onToggle={() => toggleSlot("b")} onSearch={setSlotSearch}
                  onSelect={id => selectCompany("b", id)}
                />
                {parseMsg.unknown.map((n,i) => (
                  <span key={i} className="parse-chip warn"><Icon name="alert" size={12}/>未識別：{n}</span>
                ))}
              </div>
              {availableYears.length > 0 && (
                <div className="ptb-period">
                  <div className="ptb-period-row">
                    {availableYears.map(y => (
                      <button key={y} className={"ptb-period-btn" + (y === fiscalYear ? " active" : "")}
                        onClick={() => changeYear(y)}>{y}</button>
                    ))}
                  </div>
                  <div className="ptb-period-row">
                    {availableQuartersForYear.map(q => {
                      const info = periodInfoMap.get(`${fiscalYear}${q}`);
                      const label = info
                        ? (info.has_eps ? `${q}（已公布財報）` : `${q}（僅月營收）`)
                        : q;
                      return (
                        <button key={q} className={"ptb-period-btn" + (q === fiscalQuarter ? " active" : "")}
                          onClick={() => changeQuarter(q)}>{label}</button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Comparison content */}
            {hasQueried && readyToCompare ? (
              <>
                {apiError && (
                  <div className="mock-note" style={{ borderColor: "rgb(var(--danger))" }}>
                    <Icon name="alert" size={15}/>
                    <span><b>API 錯誤</b>：{apiError}</span>
                  </div>
                )}
                {metricNotice && (
                  <div className="mock-note" style={{ borderColor: "rgb(var(--warning))" }}>
                    <Icon name="alert" size={15}/>
                    <span>{metricNotice}</span>
                  </div>
                )}
                <ComplianceBanner message={
                  peerResult
                    ? `合規檢查：${peerResult.compliance_status === "passed" ? "通過" : peerResult.compliance_status}。以上為事實對比，非投資建議。`
                    : "以上為事實對比，非投資建議。"
                }/>
                <div className="peer-l2">
                  {peerResult
                    ? <PeerKpiGridLive result={peerResult} aName={A?.name ?? ""} bName={B?.name ?? ""} queryHint={query}/>
                    : <PeerKpiGridFallback aName={A?.name??""} bName={B?.name??""} aTicker={aId} bTicker={bId} fiscalPeriod={fiscalPeriod} selectedMonth={selectedMonth}/>
                  }
                </div>
                <div className="rcol-stack">
                  {peerResult && <PeerSummaryPanel summary={peerResult.summary}/>}
                  {peerResult && <PeerCallMatrix result={peerResult} aName={A?.name ?? ""} bName={B?.name ?? ""}/>}
                  <div className="peer-blocks">
                    {peerResult
                      ? <FinancialBlock result={peerResult} aName={A?.name ?? ""} bName={B?.name ?? ""} queryHint={query}/>
                      : <div className="panel"><div className="panel-body"><div className="chart-empty" style={{padding:"20px 16px"}}><span>送出查詢後顯示財務資料</span></div></div></div>
                    }
                  </div>
                  {peerResult && <TrendPanel aName={A?.name??""} bName={B?.name??""} trend={peerResult.trend}/>}
                </div>
              </>
            ) : (
              <div className="peer-empty">
                <Icon name="scale" size={28} style={{color:"rgb(var(--muted))",marginBottom:12}}/>
                <p>{!readyToCompare ? "請從上方選擇，或是輸入問題後開始分析" : "公司已選定，送出查詢後顯示比較結果"}</p>
              </div>
            )}

            {/* Actions */}
            <div className="actions">
              <button className="btn" disabled={!hasQueried} onClick={() => setShowReport(true)}>
                <Icon name="file" size={15}/>完整報告
              </button>
              <button className="btn ghost" disabled={running || !readyToCompare} onClick={() => runQuery()}>
                <Icon name="refresh" size={15}/>重新分析
              </button>
            </div>
          </div>

          {/* Sidebar */}
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
                  <span>執行比較後顯示思考路徑</span>
                </div>
              ) : (
                <>
                  <div className="ctx-progress">
                    <div className="ctx-prog-track"><div className="ctx-prog-fill" style={{width:progress+"%"}}/></div>
                    <span className="font-mono">{running ? (PHASES[Math.floor(progress / (100 / PHASES.length))] ?? "") : "done"} · {progress}%</span>
                  </div>
                  {running && (
                    <div className="thinking-pulse">
                      <div className="thinking-dots"><span/><span/><span/></div>
                      <span key={thinkingMsgTier(thinkingSec)} className="thinking-msg">{thinkingMsgText(thinkingSec)}</span>
                    </div>
                  )}
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
                  : peerAlerts.length > 0
                    ? peerAlerts.map((a,i) => (
                        <AlertItem key={a.id} alert={a} selected={selectedAlertIdx===i} read={rs.isRead(a.id)}
                          onClick={() => { setSelectedAlertIdx(selectedAlertIdx===i?null:i); rs.markRead(a.id); }}
                          onDoubleClick={() => { setModalAlert(a); rs.markRead(a.id); }}/>
                      ))
                    : <div className="chart-empty" style={{padding:"20px 16px"}}>
                        <span>{hasQueried ? "本次比較未發現異常訊號" : "執行比較後顯示相關警示"}</span>
                      </div>
                }
              </div>
            </div>
            {/* Citation Tracker */}
            <div className="panel ctx-panel">
              <div className="panel-head">
                <span className="panel-title"><Icon name="quote" size={14} style={{color:"rgb(var(--primary))",verticalAlign:"-2px",marginRight:6}}/>引用資訊</span>
                {citations.length > 0 && <span className="panel-meta">{citations.length} 筆</span>}
              </div>
              {running ? (
                <div className="thinking-pulse" style={{padding:"14px 16px"}}>
                  <div className="thinking-dots"><span/><span/><span/></div>
                  <span>正在抓取資料中</span>
                </div>
              ) : citations.length > 0 ? (
                <CitationList citations={citations} onOpen={handleOpenDoc}/>
              ) : (
                <div className="chart-empty" style={{padding:"20px 16px"}}>
                  <span>{hasQueried ? "本次比較無引用來源" : "執行比較後顯示引用來源"}</span>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>

      {/* Dock */}
      <div className="dock">
        <div className="dock-inner">
          <div className={`dock-chips${chipsFading ? " chips-fading" : ""}`}>
            {chips.map((p,i) => <button key={i} className="chip" onClick={() => { setQuery(p); runQuery(p); }}>{p}</button>)}
          </div>
          <div className="dock-row">
            <Icon name="spark" size={18} style={{color:"rgb(var(--primary))",flexShrink:0}}/>
            <input className="dock-input" value={query} onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if(e.key==="Enter"&&(e.ctrlKey||e.metaKey||!e.shiftKey)) runQuery(); }}
              placeholder="輸入欲比較的公司，例如：比較台積電與聯發科財務... (Enter 送出)"/>
            <button className={"dock-tool" + (isListening ? " active" : "")} title={isListening ? "聆聽中…" : "語音輸入"} onClick={startVoice} disabled={running}><Icon name="mic" size={19}/></button>
            <button className={"btn primary dock-send" + (running ? " sending" : "")} onClick={() => runQuery()} disabled={running}>
              <Icon name={running ? "refresh" : "send"} size={18}/>
            </button>
          </div>
          <div className="dock-hint">選擇公司插槽或輸入自然語言 · 自動解析公司／季別／維度 · 非投資建議</div>
        </div>
      </div>

      {/* Alert Modal */}
      {modalAlert && (
        <div className="alert-modal-overlay" onClick={() => setModalAlert(null)}>
          <div className="alert-modal" onClick={e => e.stopPropagation()}>
            <div className="alert-modal-head">
              <h2>{modalAlert.title}</h2>
              <button className="alert-modal-close" onClick={() => setModalAlert(null)} aria-label="關閉"><Icon name="x" size={18}/></button>
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

      {/* Report Modal */}
      {showReport && A && B && (
        <ReportModal
          query={`${A.name} vs ${B.name} 同業比較${peerResult ? ` (${peerResult.fiscal_period})` : ""}`}
          kpis={reportKpis}
          summary={reportSummary}
          react={[]}
          citations={citations}
          onClose={() => setShowReport(false)}
        />
      )}

      <DocViewer doc={openDoc} onClose={() => setOpenDoc(null)}/>
    </>
  );
}

// useSearchParams() 需包在 Suspense 內，否則 next build 靜態匯出會 bail-out。
export default function PeerPage() {
  return (
    <Suspense fallback={null}>
      <PeerPageInner />
    </Suspense>
  );
}
