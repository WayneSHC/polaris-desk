// lib/api.ts — 唯一資料存取層，直接打 ${API_BASE}${path}
import { API_BASE } from "./config";
import { logError } from "./logger";
import {
  normalizeAlerts, normalizeAlert, normalizeAsk, normalizeResearch, normalizeComparison,
  normalizeLibrary, normalizeNotifications,
  normalizeResolve, normalizeWatchItem, normalizeCompany,
} from "./adapters";
import type { ContraAlert } from "@/lib/contraAlertStore";
import { historyStore } from "./historyStore";
import { getSession } from "next-auth/react";
import type { ChunkRaw, FinancialRow, BackendPeerCompareResponse, PeerCompareResult, ContradictionResponse, SuggestionsResponse, PeriodInfo } from "@/types/api";
import type { DocContent } from "@/components/polaris/DocViewer";
import { normalizePeerCompare } from "@/lib/peer-result";

// 有登入 → 回 Authorization header；無登入 / 斷網 → 空物件（後端視為匿名）
async function authHeaders(): Promise<Record<string, string>> {
  try {
    const session = await getSession();
    const t = (session as any)?.idToken as string | undefined;
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch {
    return {};
  }
}

async function realFetch(path: string, init?: RequestInit): Promise<unknown> {
  const auth = await authHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...auth, ...(init?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

const get = (path: string) => realFetch(path);

const post = (path: string, body: unknown) =>
  realFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// ── 各端點 ──

export const api = {
  async ask(query: string) {
    const raw = await post("/ask", { query }) as any;
    return normalizeAsk(raw, query);
  },

  async research(query: string) {
    const raw = await post("/research", { question: query }) as any;
    return normalizeResearch(raw, query);
  },

  async suggestions(mode: "research" | "peer" = "research"): Promise<SuggestionsResponse> {
    const raw = await get(`/suggestions?mode=${mode}`) as SuggestionsResponse;
    return raw;
  },

  async contradiction(
    kpis: unknown[],
    summary: Array<{ text: string; cite: string; page: string }>,
  ): Promise<{ alerts: ContraAlert[] }> {
    try {
      const raw = await post("/contradiction", { kpis, summary }) as ContradictionResponse;
      const alerts: ContraAlert[] = (raw.alerts ?? []).map(a => ({
        ...normalizeAlert(a),
        origin: "contradiction" as const,
      }));
      return { alerts };
    } catch {
      return { alerts: [] };
    }
  },

  async alerts() {
    const raw = await get("/alerts") as any[];
    return normalizeAlerts(raw);
  },

  async notifications() {
    const raw = await get("/notifications") as any;
    return normalizeNotifications(raw);
  },

  async companies() {
    const raw = await get("/companies") as any[];
    return raw.map(normalizeCompany);
  },

  async company(id: string) {
    const raw = await realFetch(`/company/${id}`) as any;
    return normalizeComparison(raw);
  },

  async resolve(query: string) {
    const raw = await post("/resolve", { query }) as any;
    return normalizeResolve(raw);
  },

  async news() {
    const raw = await realFetch("/events?type=news&limit=100") as any[];
    const items = raw.map(e => ({
      id: e.event_id as string,
      cite: e.ticker ?? "",
      title: e.title ?? "",
      summary: "",
      time: e.published_at ?? "",
      tags: e.ticker ? [e.ticker as string] : [],
      url: e.source_url ?? undefined,
    }));
    const tickerCounts: Record<string, number> = {};
    items.forEach(item => item.tags.forEach((t: string) => { tickerCounts[t] = (tickerCounts[t] ?? 0) + 1; }));
    const tabs = [
      { id: "all", label: "全部", count: items.length },
      ...Object.entries(tickerCounts).map(([ticker, count]) => ({ id: ticker, label: ticker, count })),
    ];
    return { updated: new Date().toLocaleDateString("zh-TW"), tabs, items };
  },

  async library() {
    const raw = await get("/library") as any;
    return normalizeLibrary(raw);
  },

  async history() {
    try {
      const session = await getSession();
      if (session) {
        const raw = await realFetch("/history") as any[];
        return raw.map((h) => ({
          id: h.id as string,
          query: h.query as string,
          page: (h.origin ?? "research") as "research" | "peer",
          // Firestore auto-id 解析不出時間，分組要靠 created_at 換算的 ts
          ts: h.created_at && !isNaN(Date.parse(h.created_at)) ? Date.parse(h.created_at) : undefined,
          time: h.created_at
            ? new Date(h.created_at).toLocaleString("zh-TW", {
                timeZone: "Asia/Taipei", year: "numeric", month: "2-digit",
                day: "2-digit", hour: "2-digit", minute: "2-digit",
              })
            : "",
          tags: (h.tickers ?? []) as string[],
        }));
      }
    } catch (e) {
      logError("api.history", e);
    }
    return historyStore.read();
  },

  async historyOne(id: string): Promise<{ query: string; page: "research" | "peer"; result: unknown } | null> {
    try {
      const raw = await realFetch(`/history/${encodeURIComponent(id)}`) as any;
      return { query: raw.query, page: raw.origin ?? "research", result: raw.result };
    } catch (e) {
      logError("api.historyOne", e);
      return null;
    }
  },

  async deleteHistory(id: string): Promise<void> {
    // 登入者：先讓後端真的刪除（Firestore），失敗則拋出 → 呼叫端可顯示錯誤、
    // 不再「靜默成功」（後端原本缺 DELETE 端點，資料其實沒刪掉）。匿名只刪 localStorage。
    const session = await getSession();
    if (session) {
      await realFetch(`/history/${encodeURIComponent(id)}`, { method: "DELETE" });
    }
    historyStore.remove(id);
  },

  postHistory(origin: "research" | "peer", query: string, tickers: string[], result: unknown): void {
    authHeaders().then((auth) =>
      fetch(`${API_BASE}/history`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ origin, query, tickers, result }),
      })
    ).catch(() => {
      // 未登入 (401) 或網路錯誤時靜默忽略，localStorage 已有備援
    });
  },

  async watch() {
    const raw = await get("/watch") as any[];
    return raw.map(normalizeWatchItem);
  },

  async chunk(sourceId: string): Promise<DocContent | null> {
    try {
      const raw = await realFetch(`/chunk/${encodeURIComponent(sourceId)}`) as ChunkRaw;
      return {
        key: raw.source_id,
        title: raw.title,
        kind: raw.kind_label,
        source_id: raw.source_id,
        page: raw.page ?? "頁碼未提供",
        period: raw.fiscal_period || undefined,
        trust: raw.trust,
        highlight: raw.highlight,
        hlTokens: raw.hl_tokens,
        body: raw.content.split(/(?<=。)|\n/).map((s) => s.trim()).filter(Boolean),
      };
    } catch (e) {
      logError("api.chunk", e);
      return null;
    }
  },

  async financials(ticker: string, limit = 30): Promise<FinancialRow[]> {
    try {
      const raw = await get(`/financials?ticker=${encodeURIComponent(ticker)}&limit=${limit}`) as FinancialRow[];
      return Array.isArray(raw) ? raw : [];
    } catch (e) {
      logError("api.financials", e);
      return [];
    }
  },

  async periods(): Promise<PeriodInfo[]> {
    const raw = await get("/periods") as PeriodInfo[];
    return Array.isArray(raw) ? raw : [];
  },

  async healthz() {
    const raw = await get("/healthz") as any;
    return raw;
  },

  async markNotificationRead(id: string): Promise<void> {
    try {
      await realFetch(`/notifications/${encodeURIComponent(id)}/read`, { method: "POST" });
    } catch { /* best-effort，localStorage 已讀狀態仍保留 */ }
  },

  async getSubscriptions(): Promise<string[]> {
    try {
      const raw = await realFetch("/subscriptions") as { status: string; tickers: string[] };
      return raw.tickers ?? [];
    } catch (e) {
      logError("api.getSubscriptions", e);
      return [];
    }
  },

  async setSubscriptions(tickers: string[]): Promise<void> {
    await realFetch("/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers }),
    });
  },

  async peerCompare(params: {
    a_ticker: string;
    b_ticker: string;
    fiscal_period: string;
    question: string;
    month?: number | null;
  }): Promise<PeerCompareResult> {
    const raw = await realFetch("/peer-compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }) as BackendPeerCompareResponse;

    return normalizePeerCompare(raw);
  },
};
