# 開發環境：改用 BigQuery（一頁速懂）

> **2026-06-02 起，開發預設後端從 pgvector 改為 BigQuery。** 大家在同一份共用 canonical（`polaris_core`）上協作，個人實驗寫進自己的 scratch。pgvector 保留為**離線 / Demo fallback**（改一個 env 就切回）。
> 給**人**也給 **AI agent**（Claude Code / Codex / Antigravity / Cursor / Gemini）看 —— agent 規則見 [`AGENTS.md`](../AGENTS.md)。

## 為什麼改

- **算一次、大家讀**：100 份法說稿的 embedding 算一次寫進 `polaris_core`，7 人共用，不必各自重算重灌（省 token、資料一致）。呼應 SOP 的核心原則。
- 共用資料 > 7 份各自的本地 DB；Demo 本來就跑雲端，開發直接對齊。

## 怎麼設定（每人一次，約 3 分鐘）

前提：你的 gmail 已被加進權限（`polaris_core` READER + 專案 `bigquery.user`，已由 SOP §3.4 開好）。本機跑 BigQuery 還需要專案層 `roles/serviceusage.serviceUsageConsumer`（設 ADC quota project 用），同樣由 SOP §3.4 開。

```bash
# 1) 認證（ADC）— 一定要先 login 再 set-quota-project，否則 quota project 沒有身分可掛
gcloud auth login
gcloud auth application-default login
gcloud config set project polaris-desk-team
gcloud auth application-default set-quota-project polaris-desk-team
# 若報 "serviceusage.services.use" 缺權限 → 缺 serviceUsageConsumer，回頭找 PM 補（SOP §3.4）
# 若報 "unregistered callers" → ADC 沒登入，或 GOOGLE_APPLICATION_CREDENTIALS 指到壞檔；先 unset 再重跑 login

# 2) .env（cp .env.example .env 後預設值已是 BigQuery）
#    VECTOR_BACKEND=bigquery
#    GCP_PROJECT=polaris-desk-team
#    BQ_DATASET=polaris_core          # 共用唯讀 canonical
#    DEV_DATASET=polaris_dev_<name>   # 換成你的英文名

# 3) 建自己的 scratch（只你可寫）
bq --location=asia-east1 mk --dataset polaris-desk-team:polaris_dev_<name>

# 4) 驗證讀取（canonical 還沒 ingest 前，可先驗證連得到）
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS tables FROM `polaris-desk-team.polaris_core.INFORMATION_SCHEMA.TABLES`'
```

完整步驟與成本護欄見 [`協作開發環境_SOP_v1.md`](協作開發環境_SOP_v1.md) §5。

## 日常守則（重要）

- **讀 `polaris_core`、寫 `polaris_dev_<name>`**。一般開發者永遠不要寫 `polaris_core`。
  - 例外（2026-06-08 經 PM 同意）：`polaris_core` 的 WRITER 已擴大到 R4（人帳號 OWNER + GCE 預設 SA WRITER）與 R1（WRITER）；其餘成員仍唯讀。即便是這兩人，schema／index 變更仍走 SOP §7 PR，別直接動 canonical 結構。細節與風險見 SOP §3.4。
- 查詢帶 `published_at` 範圍 + `ticker`；大查詢先 `bq query --dry_run` 估成本。
- 不要自己重建 index / 重跑 ingestion；要改 schema 走 SOP §7 的 PR 流程。

## 測試還是離線的

`make test`（70 passed）是 **stub 模式**，不連 BigQuery、不需要金鑰或網路。後端切換只影響真正跑檢索 / ingestion 時。

## 離線 / Demo fallback：切回 pgvector

雲端斷網或 Demo Day 要離線時：

```bash
# .env 改一行
VECTOR_BACKEND=pgvector
# 起本地 Postgres + pgvector
make db-up
```

`get_vector_store()` 會自動回 pgvector 實作，**程式碼一行都不用改**。

> pgvector 查詢一定用 `<=>`（cosine）；用 `<->` / `<#>` 會全表掃描。詳見 `scripts/init_pgvector.sql` 註解。

## 給 AI agent 的提醒

- **預設後端是 `bigquery`，不要改回 `pgvector` 預設**（fallback 只在離線情境手動切）。
- 寫入一律進 `polaris_dev_<name>`，**不可寫 `polaris_core`**（例外僅 R1／R4 的 ingestion，見上方守則）。
- 金鑰 / 認證**不要碰**（人自己 `gcloud auth ...`）；別把任何 key 寫進檔案或 commit。

---
_對應：`docs/協作開發環境_SOP_v1.md`、憲法 §III、`.env.example`、`src/polaris/vectorstore/`_
