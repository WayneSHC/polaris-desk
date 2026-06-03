# G2 架構面驗收自評（R2）

> **閘門**：W2 D10 G2（架構面）。本文是 R2 對「W2 架構強化是否就緒 + 上雲管路是否通」的自評，
> 對應 spec 的 FR/SC 與 R2 角色 spec 的 W2 交付（D6–D10）。每條都附**可重跑的證據**（測試名 / 指令）。
>
> ⚠️ **D10 完整版需 R4 的 BigQuery 入庫資料煙測（show-stopper，R4 尚未開工）**。本文涵蓋
> **不被 R4 阻擋**的架構面：D6–D9 交付 + 上雲「管路」煙測 harness。real-data 煙測 pending R4。

更新時間：2026-06-03 ｜ 全測試：`make check` → **249 passed, ruff clean**

## A. W2 架構面交付（D6–D9，皆已併入 main）

| 交付 | 對應 | 狀態 | 證據（可重跑）|
|---|---|---|---|
| D6 Temporal Anchoring | FR-007 | ✅ | `test_temporal.py`；retriever 依季別過濾、未入庫季別誠實回「資料不足」 |
| D7 LangGraph retry | SC-006 | ✅ | `test_retry.py`、`test_traced_retry.py`、`test_planner_agent.py::TestMakePlanRetry`、`test_writer_agent.py::TestMakeDraftRetry`（暫時性重試、永久性不重試、fallback） |
| D8 LLMLingua POC | SC-006 | ✅（量測 harness）| `test_compression_*.py`；`python -m polaris.compression` 實量確定性基線省 ~7–14%；**≥50% 由本機 `[llmlingua]` extra 跑真 backend**（CI 不硬斷言，誠實不 game 假語料）|
| D9 Compliance Agent | NFR-031 / SC-003 | ✅ | `test_compliance_agent.py`、`test_compliance.py`；6 關鍵字 floor + Gemini smart 層，fail-to-floor、LLM 永不改寫/解除 |

## B. 核心不變量（W1 起持續綠）

| 準則 | 內容 | 狀態 | 證據 |
|---|---|---|---|
| SC-001/002 | e2e 0 介入產出 answer+citations、trace 列 5 節點 | ✅ | `test_workflow_e2e.py` |
| SC-003 | 6 關鍵字攔截 100%、最終 answer 0 買賣建議 | ✅ | `test_compliance.py`、`test_compliance_agent.py`、`test_writer_agent.py::test_llm_buysell_draft_still_blocked_by_compliance` |
| SC-005 | 換節點 → workflow.py diff = 0 行 | ✅ | `test_node_swap.py`（hash 不變；D6–D9 僅換 stubs/新增模組，workflow.py 未動）|
| SC-006 | 同問題 3 次結果完全相同 | ✅ | `test_workflow_e2e.py::TestE2EDeterminism` |
| SC-007 | 空輸入只跑 Planner、固定錯誤訊息 | ✅ | `test_workflow_edges.py` |

## C. 上雲「管路」煙測（D10 非阻塞部分）

指令：`make bq-smoke`／`python -m polaris bq-smoke`（harness：`diagnostics.bigquery_smoke`，`test_bq_smoke.py` 背書）。

| 步驟 | 檢查 | 現況 |
|---|---|---|
| config | backend / gcp_project / bq_dataset 接線 | ⚠️ 本機 `.env` 的 `GCP_PROJECT=` **空** → 報 fail（action item，見 D）|
| connectivity | `BigQueryStore.health_check()`（SELECT 1）| ⏳ **pending R4**（health_check 仍 NotImplementedError）；且需 GCP 金鑰才打網路，否則 skipped |

**本機實跑輸出**（誠實反映未配置狀態）：
```
== Polaris Desk — BigQuery 雲端管路煙測 (bq-smoke) ==
  config        ❌ fail     gcp_project 未設定（無法連 BigQuery）
  connectivity  ⏭️ skipped  無 GCP 金鑰：設 GOOGLE_APPLICATION_CREDENTIALS 或 gcloud auth application-default login 後重跑
  overall: fail
```

> 煙測 harness 已就緒並**零接觸 R4 檔**：把 R4 尚未實作的 `health_check`（NotImplementedError）
> 歸類為 `pending`、無金鑰歸 `skipped`（皆非程式失敗）。**R4 補完 health_check + 設好 GCP_PROJECT/金鑰後，零改碼自動轉真連線煙測。**

## D. 上游依賴 / Action items（待補才會「全綠」）

| 項目 | 由誰 | 影響 |
|---|---|---|
| `BigQueryStore.{health_check, add_documents, search}` | R4 | 連線煙測現為 pending；R4 W2 補完即轉真。R2 **未碰**該檔（角色邊界）|
| 真實「入庫資料」BigQuery 煙測（Q-03） | R4 + R2 協同 | **D10 完整版**；需 R4 ingestion（SOP §4，尚未開工）|
| 本機 `.env` `GCP_PROJECT=`（空）| 各成員 | 設為 `polaris-desk-team`（PR #15 canonical）；否則 bq-smoke config fail |
| GCP ADC 金鑰 | 各成員 | `gcloud auth application-default login` 或設 `GOOGLE_APPLICATION_CREDENTIALS`；否則 connectivity skipped |
| LLMLingua ≥50% 實測 | R2（本機）| `uv pip install -e '.[llmlingua]'` + 跑 `python -m polaris.compression`，回填設計文件 §6 |
| 金鑰全員到位 + G1 站會過閘（D5 `[~]`）| 全員 | G1 出場 action item 尚未關閉 |

## E. G2 結論（R2 視角）

**W2 架構面就緒**：Temporal / retry / 壓縮量測 / Compliance Agent 四項交付全綠且有測試背書，
5 節點 e2e / 節點可換 / 確定性 / 合規攔截等核心不變量持續綠（249 passed）。**上雲管路 harness 就緒**，
並能誠實分辨 pending（待 R4）/ skipped（待金鑰）/ fail（設定錯）。

**唯一非綠（皆非 R2 架構碼問題）**：① BigQuery 真連線 + 入庫資料煙測 pending R4 ingestion；
② 本機 GCP_PROJECT/金鑰待各自配置。建議 G2 判定為 **Go（架構面）**，並把「R4 補完 BigQueryStore + 跑真資料煙測（Q-03）」「全員設 GCP_PROJECT + ADC 金鑰」列為 G2 出場 action item。
