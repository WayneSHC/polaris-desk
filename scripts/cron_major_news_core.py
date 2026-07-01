"""
cron_major_news_core.py — 重大資訊定時入庫（直寫 polaris_core，冪等去重）

設計（方案 B：Cloud Run Job + Cloud Scheduler，每日 08/12/16/20）：
  - 滾動視窗：每次掃「近 N 天」重大訊息（預設 3 天），涵蓋 MOPS 補登
  - 冪等去重：寫前比對 core 既有 chunk_id / event_id，只寫不存在的
  - 直寫 core：DEV_DATASET="" → BigQueryStore / EventStore 皆路由到 polaris_core
  - 公司清單：從 company_dim 動態載入（新增公司自動納入）

環境變數（由 Cloud Run Job 注入）：
  GCP_PROJECT=polaris-desk-team
  BQ_DATASET=polaris_core
  DEV_DATASET=            # 必須為空，才會直寫 core
  GEMINI_API_KEY=...      # 由 Secret Manager 注入（--set-secrets）
  MAJOR_NEWS_WINDOW_DAYS=3         # 選配，滾動視窗天數
  VECTOR_BACKEND=bigquery
"""
import os
# ── 必須在 import polaris 之前，強制路由到 core ──────────────────────────────
os.environ.setdefault("BQ_DATASET", "polaris_core")
os.environ["DEV_DATASET"] = ""                       # 空字串 → falsy → 用 bq_dataset(core)
os.environ.setdefault("VECTOR_BACKEND", "bigquery")

import sys
import logging
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("cron_major_news")

TPE = timezone(timedelta(hours=8))
WINDOW_DAYS = int(os.environ.get("MAJOR_NEWS_WINDOW_DAYS", "3"))


def _load_tickers(client, proj: str, dataset: str) -> list[str]:
    """從 company_dim 動態載入公司清單（新增公司自動納入）。"""
    sql = f"SELECT ticker FROM `{proj}.{dataset}.company_dim` ORDER BY ticker"
    return [r.ticker for r in client.query(sql).result()]


def main() -> int:
    from google.cloud import bigquery
    from polaris.config import settings
    from polaris.data_feeds.mops_major_news import query as major_query
    from polaris.data_feeds.ingest_major_news import _record_to_doc, _record_to_event
    from polaris.llm.gemini import active_llm
    from polaris.vectorstore.factory import get_vector_store
    from polaris.vectorstore.event_store import EventStore

    proj = settings.gcp_project
    dataset = settings.bq_dataset            # 應為 polaris_core
    if dataset != "polaris_core":
        log.error("BQ_DATASET=%s，預期 polaris_core，中止以免誤寫", dataset)
        return 2
    if settings.dev_dataset:
        log.error("DEV_DATASET 非空（%s），會誤寫 dev，中止", settings.dev_dataset)
        return 2

    client = bigquery.Client(project=proj)

    # ── 滾動視窗 ────────────────────────────────────────────────────────────
    today = datetime.now(TPE).date()
    date_from = (today - timedelta(days=WINDOW_DAYS)).strftime("%Y%m%d")
    date_to = today.strftime("%Y%m%d")
    log.info("重大資訊排程啟動  視窗 %s ~ %s  → %s", date_from, date_to, dataset)

    tickers = _load_tickers(client, proj, dataset)
    log.info("公司清單：%d 家", len(tickers))

    # ── 既有 ID（去重基準）──────────────────────────────────────────────────
    existing_chunks = {r[0] for r in client.query(
        f"SELECT chunk_id FROM `{proj}.{dataset}.chunks` WHERE doc_type='major_news'"
    ).result()}
    existing_events = {r[0] for r in client.query(
        f"SELECT event_id FROM `{proj}.{dataset}.events` WHERE event_key LIKE 'major_news%'"
    ).result()}
    log.info("既有 chunk_id=%d  event_id=%d", len(existing_chunks), len(existing_events))

    # ── 抓 MOPS ─────────────────────────────────────────────────────────────
    records = major_query(tickers=tickers, date_from=date_from, date_to=date_to)
    log.info("MOPS 抓取 %d 筆", len(records))

    # ── 去重 → 新 docs ──────────────────────────────────────────────────────
    docs, dup, err = [], 0, 0
    for rec in records:
        doc = _record_to_doc(rec)
        if doc is None:
            err += 1
        elif doc.id in existing_chunks:
            dup += 1
        else:
            docs.append(doc)
    log.info("新增 chunks=%d  重複=%d  內容錯誤=%d", len(docs), dup, err)

    # ── embed + 寫 core.chunks ──────────────────────────────────────────────
    if docs:
        llm = active_llm()
        if llm is None:
            log.error("無 GEMINI_API_KEY，embedding 停用，中止（不寫半成品）")
            return 3
        embs = llm.embed_batch([d.content for d in docs])
        for d, e in zip(docs, embs):
            d.embedding = e
        get_vector_store().add_documents(docs)
        log.info("✅ chunks 寫入 %s（%d 筆）", dataset, len(docs))

    # ── 去重 → 新 events → 寫 core.events ──────────────────────────────────
    new_events, seen = [], set()
    for rec in records:
        ev = _record_to_event(rec)
        if ev and ev.event_id not in existing_events and ev.event_id not in seen:
            seen.add(ev.event_id)
            new_events.append(ev)
    if new_events:
        EventStore().upsert(new_events)
        log.info("✅ events 寫入 %s（%d 筆）", dataset, len(new_events))

    log.info("完成｜抓 %d／新增 chunks %d／events %d／重複 %d",
             len(records), len(docs), len(new_events), dup)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("排程執行失敗")
        sys.exit(1)
