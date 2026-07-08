// history-nav.ts — 對話紀錄「點開還原」的純邏輯（可單測，不碰 React / router）。
//
// 兩套 id 並存：localStorage 是 `hist-<timestamp>`、Firestore 是 auto-id。
// localStorage 的 id 在後端必查無（404），所以登入與否都不該拿它打 /history/{id}；
// 拿不到整包 result 時退回 A 級：帶 `?q=` 到原頁面重跑一次查詢。
import type { HistoryEntry } from "./historyStore";

export function isLocalHistoryId(id: string): boolean {
  return id.startsWith("hist-");
}

export interface HistoryRestorePayload {
  id: string;
  query: string;
  page: "research" | "peer";
  result: unknown;
  time: string;
}

export interface HistoryNavigation {
  url: string;
  /** 非 null 時呼叫端要先寫進 sessionStorage("polaris_restore") 再導頁 */
  restore: HistoryRestorePayload | null;
}

/** 下拉選公司跑的比較 query 是空字串——用 tags（兩檔 ticker）組回可重跑的查詢 */
function fallbackQuery(item: HistoryEntry): string {
  if (item.query) return item.query;
  if (item.page === "peer" && item.tags.length >= 2) {
    return `比較 ${item.tags[0]} 與 ${item.tags[1]}`;
  }
  return "";
}

export async function resolveHistoryClick(
  item: HistoryEntry,
  loggedIn: boolean,
  fetchOne: (id: string) => Promise<{ query: string; page: "research" | "peer"; result: unknown } | null>,
): Promise<HistoryNavigation> {
  if (loggedIn && !isLocalHistoryId(item.id)) {
    const full = await fetchOne(item.id);
    if (full?.result) {
      const q = full.query || fallbackQuery(item);
      return {
        // historyId 之外同時帶 q：還原後 sessionStorage 已清，使用者刷新頁面時退回重跑而非白頁
        url: `/${full.page}?historyId=${encodeURIComponent(item.id)}&q=${encodeURIComponent(q)}`,
        restore: { id: item.id, query: full.query, page: full.page, result: full.result, time: item.time },
      };
    }
  }
  return { url: `/${item.page}?q=${encodeURIComponent(fallbackQuery(item))}`, restore: null };
}

// ── 時間分組（今日／本週／更早）────────────────────────────────────────────
// Firestore auto-id 解析不出 timestamp，改吃 api.history() 從 created_at 算好的 ts；
// localStorage 紀錄沿用 id 內的 timestamp。

export type HistoryGroup = "today" | "thisWeek" | "earlier";

export function getGroup(item: { id: string; ts?: number }, now: number = Date.now()): HistoryGroup {
  const ts = item.ts ?? parseInt(item.id.replace("hist-", ""), 10);
  if (isNaN(ts)) return "earlier";
  if (new Date(ts).toDateString() === new Date(now).toDateString()) return "today";
  if (now - ts < 7 * 86400000) return "thisWeek";
  return "earlier";
}
