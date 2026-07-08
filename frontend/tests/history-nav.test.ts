import assert from "node:assert/strict";
import test from "node:test";

import {
  getGroup,
  isLocalHistoryId,
  resolveHistoryClick,
} from "../src/lib/history-nav.ts";
import type { HistoryEntry } from "../src/lib/historyStore.ts";

const entry = (over: Partial<HistoryEntry> = {}): HistoryEntry => ({
  id: "hist-1751957580000",
  query: "台積電與聯電的先進製程營收占比差異",
  page: "peer",
  time: "2026/07/02 下午06:41",
  tags: ["2303", "2330"],
  ...over,
});

test("isLocalHistoryId 只認 localStorage 的 hist- 前綴", () => {
  assert.equal(isLocalHistoryId("hist-1751957580000"), true);
  assert.equal(isLocalHistoryId("aB3dE9fGhI2kLmN0pQrS"), false);
});

test("登入 + localStorage id：不打後端（必 404），直接帶 q 重跑", async () => {
  let called = 0;
  const nav = await resolveHistoryClick(entry(), true, async () => {
    called += 1;
    return null;
  });
  assert.equal(called, 0);
  assert.equal(nav.restore, null);
  assert.equal(
    nav.url,
    `/peer?q=${encodeURIComponent("台積電與聯電的先進製程營收占比差異")}`,
  );
});

test("peer 紀錄 query 為空（下拉選公司跑的）：用 tags 組出可重跑的查詢", async () => {
  const nav = await resolveHistoryClick(
    entry({ query: "", tags: ["2308", "2317"] }),
    true,
    async () => null,
  );
  assert.equal(nav.url, `/peer?q=${encodeURIComponent("比較 2308 與 2317")}`);
});

test("登入 + 後端 id + 有 result：走 B 級還原，URL 同時帶 historyId 與 q（刷新後可 A 級重跑）", async () => {
  const result = { a_ticker: "2330", b_ticker: "2454" };
  const nav = await resolveHistoryClick(
    entry({ id: "aB3dE9fGhI2kLmN0pQrS" }),
    true,
    async (id) => {
      assert.equal(id, "aB3dE9fGhI2kLmN0pQrS");
      return { query: "台積電與聯電的先進製程營收占比差異", page: "peer", result };
    },
  );
  assert.deepEqual(nav.restore, {
    id: "aB3dE9fGhI2kLmN0pQrS",
    query: "台積電與聯電的先進製程營收占比差異",
    page: "peer",
    result,
    time: "2026/07/02 下午06:41",
  });
  assert.ok(nav.url.startsWith("/peer?historyId=aB3dE9fGhI2kLmN0pQrS&q="));
});

test("登入 + 後端 id 但查無 result：退回 q 重跑", async () => {
  const nav = await resolveHistoryClick(
    entry({ id: "aB3dE9fGhI2kLmN0pQrS", page: "research", query: "毛利率？" }),
    true,
    async () => null,
  );
  assert.equal(nav.restore, null);
  assert.equal(nav.url, `/research?q=${encodeURIComponent("毛利率？")}`);
});

test("未登入：不打後端，直接 q 重跑", async () => {
  let called = 0;
  const nav = await resolveHistoryClick(entry({ id: "aB3dE9fGhI2kLmN0pQrS" }), false, async () => {
    called += 1;
    return null;
  });
  assert.equal(called, 0);
  assert.equal(nav.restore, null);
});

test("getGroup：優先用 ts（Firestore 紀錄），否則解析 hist- id，都沒有歸更早", () => {
  const now = Date.parse("2026-07-08T15:00:00+08:00");
  const today = Date.parse("2026-07-08T09:00:00+08:00");
  const threeDaysAgo = now - 3 * 86400000;
  const tenDaysAgo = now - 10 * 86400000;

  // Firestore auto-id + ts → 不再全部掉進「更早」
  assert.equal(getGroup({ id: "aB3dE9fGhI2kLmN0pQrS", ts: today }, now), "today");
  assert.equal(getGroup({ id: "aB3dE9fGhI2kLmN0pQrS", ts: threeDaysAgo }, now), "thisWeek");
  assert.equal(getGroup({ id: "aB3dE9fGhI2kLmN0pQrS", ts: tenDaysAgo }, now), "earlier");
  // localStorage 紀錄沿用 id 內的 timestamp
  assert.equal(getGroup({ id: `hist-${today}` }, now), "today");
  // 解析不出時間 → 更早
  assert.equal(getGroup({ id: "aB3dE9fGhI2kLmN0pQrS" }, now), "earlier");
});
