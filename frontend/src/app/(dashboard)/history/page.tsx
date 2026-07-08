"use client";
import { useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { useRouter } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import { logError } from "@/lib/logger";
import { PanelSkeleton } from "@/components/polaris/Skeleton";
import { historyStore } from "@/lib/historyStore";
import type { HistoryEntry } from "@/lib/historyStore";
import { getGroup, resolveHistoryClick } from "@/lib/history-nav";
import type { HistoryGroup } from "@/lib/history-nav";

const FILTER_TABS = ["all", "research", "peer"];
const TAB_LABELS: Record<string, string> = { all: "全部", research: "研究助理", peer: "同業比較" };

const GROUP_LABELS = { today: "今日", thisWeek: "本週", earlier: "更早" } as const;
const GROUP_ORDER: HistoryGroup[] = ["today", "thisWeek", "earlier"];

function groupItems(items: HistoryEntry[]) {
  const buckets: Partial<Record<HistoryGroup, HistoryEntry[]>> = {};
  for (const item of items) {
    const g = getGroup(item);
    (buckets[g] ??= []).push(item);
  }
  return GROUP_ORDER
    .filter(g => buckets[g]?.length)
    .map(g => ({ key: g, label: GROUP_LABELS[g], items: buckets[g]! }));
}

export default function HistoryPage() {
  const { data, isLoading } = useSWR("history", () => api.history());
  const { mutate } = useSWRConfig();
  const { data: session } = useSession();
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await api.deleteHistory(deleteTarget);
    } catch (e) {
      logError("confirmDelete", e);
      historyStore.remove(deleteTarget);
    }
    mutate("history");
    setDeleteTarget(null);
    setIsDeleting(false);
  };

  const handleItemClick = async (item: HistoryEntry) => {
    const nav = await resolveHistoryClick(item, !!session, api.historyOne);
    if (nav.restore) sessionStorage.setItem("polaris_restore", JSON.stringify(nav.restore));
    router.push(nav.url);
  };

  const filtered = (data ?? []).filter(item => filter === "all" || item.page === filter);
  const groups = groupItems(filtered);

  return (
    <>
    <div className="page-scroll">
      <div className="page narrow">
        <div className="page-head">
          <div className="page-eyebrow">對話紀錄 · history</div>
          <h1 className="page-title">對話紀錄</h1>
          <p className="page-desc">研究助理與同業比較的歷史紀錄。</p>
        </div>
        <div className="news-tabs">
          {FILTER_TABS.map(t => (
            <button key={t} className={"news-tab" + (t === filter ? " active" : "")} onClick={() => setFilter(t)}>
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>
        {isLoading ? (
          <div className="panel" style={{ marginTop: 16, padding: "0 16px" }}>
            <PanelSkeleton rows={6} />
          </div>
        ) : groups.length === 0 ? (
          <div className="panel" style={{ marginTop: 16 }}>
            <div style={{ padding: "48px 16px", textAlign: "center", color: "rgb(var(--muted))" }}>
              <Icon name="clock" size={32} style={{ marginBottom: 10, opacity: 0.3 }}/>
              <div>目前無紀錄</div>
            </div>
          </div>
        ) : (
          <div className="panel" style={{ marginTop: 16 }}>
            {groups.map((group, gi) => (
              <div key={group.key}>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "rgb(var(--muted))",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  padding: gi === 0 ? "14px 16px 6px" : "24px 16px 6px",
                  fontFamily: "var(--mono)",
                }}>
                  {group.label}
                </div>
                {group.items.map((item, i) => (
                  <div
                    key={item.id}
                    className="history-item"
                    style={{ animationDelay: `${i * 45}ms`, cursor: "pointer" }}
                    onClick={() => handleItemClick(item)}
                  >
                    <div className="ni-icon">
                      <Icon name={item.page === "peer" ? "scale" : "brain"} size={17} />
                    </div>
                    <div className="history-body">
                      <div className="history-query">
                        {item.query || (
                          <span style={{ color: "rgb(var(--muted))" }}>
                            {item.page === "peer" ? "同業比較查詢" : "研究助理查詢"}
                          </span>
                        )}
                      </div>
                      <div className="history-meta font-mono">
                        {item.page === "peer" ? "同業比較" : "研究助理"} · {item.time}
                      </div>
                    </div>
                    <div className="history-tags">
                      {item.tags.map((t, ti) => <span key={ti} className="tag muted" style={{ fontSize: 12 }}>{t}</span>)}
                    </div>
                    <button
                      className="history-del"
                      title="刪除"
                      onClick={(e) => { e.stopPropagation(); setDeleteTarget(item.id); }}
                    >
                      <Icon name="trash" size={16} />
                    </button>
                    <Icon name="chevR" size={15} style={{ color: "rgb(var(--muted))", flexShrink: 0 }}/>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>

    {deleteTarget && (

      <div className="alert-modal-overlay" onClick={() => setDeleteTarget(null)}>
        <div className="hist-confirm-card" onClick={e => e.stopPropagation()}>
          <div className="hist-confirm-title">刪除此紀錄？</div>
          <div className="hist-confirm-desc">刪除後紀錄將無法還原，確認要繼續嗎？</div>
          <div className="hist-confirm-actions">
            <button className="btn" onClick={() => setDeleteTarget(null)} disabled={isDeleting}>取消</button>
            <button className="btn danger" onClick={confirmDelete} disabled={isDeleting}>{isDeleting ? "刪除中…" : "確認刪除"}</button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
