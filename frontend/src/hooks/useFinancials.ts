"use client";
import useSWR from "swr";
import { API_BASE } from "@/lib/config";

export interface FinancialRow {
  ticker: string;
  fiscal_period: string | null;
  metric_id: string | null;
  value: number | null;
  unit: string | null;
  source_id: string | null;
  published_at: string | null;
}

async function fetchFinancials(ticker: string): Promise<FinancialRow[]> {
  const res = await fetch(`${API_BASE}/financials?ticker=${ticker}&limit=30`);
  if (!res.ok) return [];
  return res.json();
}

export function useFinancials(ticker: string | null) {
  const key = ticker ? `financials-${ticker}` : null;
  const { data, isLoading } = useSWR<FinancialRow[]>(key, () => fetchFinancials(ticker!), {
    revalidateOnFocus: false,
  });
  return { rows: data ?? [], isLoading: !!ticker && isLoading };
}

// 從 query 文字 + 已知公司清單推斷 ticker
export function inferTickerFromQuery(
  query: string,
  companies: Array<{ id: string; name: string }>
): string | null {
  // 先試直接 4 碼數字（非年份）
  const found = companies.find(c => {
    if (query.includes(c.id)) return true;
    if (c.name && query.includes(c.name)) return true;
    return false;
  });
  return found?.id ?? null;
}

// FinancialRow[] → 顯示用 KPI 摘要（最新期別）
export function financialsToKpis(rows: FinancialRow[]): Array<{
  label: string; value: string; unit: string; delta: string; trend: "up" | "down";
}> {
  if (!rows.length) return [];

  // 取最新期別
  const periods = [...new Set(rows.map(r => r.fiscal_period).filter(Boolean))].sort();
  const latestPeriod = periods.at(-1);
  const periodRows = rows.filter(r => r.fiscal_period === latestPeriod);
  const get = (id: string) => periodRows.find(r => r.metric_id === id)?.value ?? null;

  const result = [];
  const yoy = get("revenue_yoy");
  if (yoy !== null) {
    result.push({
      label: `月營收 YoY（${latestPeriod}）`,
      value: yoy.toFixed(2),
      unit: "%",
      delta: "",
      trend: yoy >= 0 ? ("up" as const) : ("down" as const),
    });
  }
  const ytdYoy = get("ytd_yoy");
  if (ytdYoy !== null) {
    result.push({
      label: `累計 YoY（${latestPeriod}）`,
      value: ytdYoy.toFixed(2),
      unit: "%",
      delta: "",
      trend: ytdYoy >= 0 ? ("up" as const) : ("down" as const),
    });
  }
  return result;
}
