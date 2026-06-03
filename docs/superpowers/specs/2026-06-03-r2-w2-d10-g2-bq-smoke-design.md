# R2 W2 D10（非阻塞部分）— G2 架構面自評 + BigQuery 雲端管路煙測 設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：R2 spec §3 W2 D10「G2 驗收（架構面）／協同 R4 跑 BigQuery 煙測（Q-03）」、SC-004/G4 上雲、§5 風險「Day 10 先 BigQuery 煙測、不留到 Demo 前夜」
**前置**：W1 D5 G1 readiness 模式（`doctor` / `check-keys` / `G1_readiness.md`）、D6–D9（已併入 main）

---

## 1. 目標與範圍

D10 完整版＝G2 架構面 + **協同 R4 跑 BigQuery 煙測**。R4 的入庫資料是 show-stopper（R4 尚未開工 SOP §4 ingestion）。本任務只做**不被 R4 阻擋**的部分：

1. **獨立 BigQuery「雲端管路」煙測** —— 驗證上雲管路（設定 / 接線 / 連線），**不需 R4 的入庫資料**。
2. **G2 架構面自評**（`docs/G2_readiness.md`，鏡像 `G1_readiness.md`）。

直接服務 §5 風險：第一次上雲不留到 Demo 前夜，Day 10 先把管路 de-risk。

### Out of scope（show-stopper，本任務不碰）
- `BigQueryStore.{health_check, add_documents, search}`（檔頭標 **@R4 W2**；本任務**零接觸**該檔）。
- 真實「入庫資料」煙測（需 R4 的 ingestion）。

---

## 2. 角色邊界決策

煙測的真連線需要 `health_check()`（目前 `NotImplementedError`、標「@R4」）。經詢問用戶：**不碰 BigQueryStore**。
→ 煙測**呼叫** `health_check()`，把現況的 `NotImplementedError` 歸類為 **`pending R4`**（非失敗）。管路 harness 就緒，**R4 補完 health_check 後零改碼自動轉真**。

---

## 3. 元件

| 元件 | 內容 |
|---|---|
| `diagnostics.bigquery_smoke(settings=None, *, store=None, creds_available=None)` | 回 `SmokeReport`（`list[SmokeStep]` + `.overall`）。`store`/`creds_available` 可注入 → 全離線可測。 |
| CLI `python -m polaris bq-smoke` | 鏡像 `doctor`：印各步驟 + overall。退出碼 0，除非硬 `fail`（`pending`/`skipped` 是 pre-R4 / pre-creds 的預期狀態、非失敗）。 |
| `make bq-smoke` | `.venv/bin/python -m polaris bq-smoke`（鏡像 `check-keys`）。 |
| `docs/G2_readiness.md` | G2 架構面自評，鏡像 `G1_readiness.md`。 |

### 煙測步驟
1. **config / wiring**（離線、必跑）：報 `vector_backend` / `gcp_project` / `bq_dataset`；`gcp_project` 缺 → `fail`。
2. **connectivity**（creds-gated）：`BigQueryStore(s).health_check()` →
   - `True` → `ok`
   - `NotImplementedError` → **`pending`**（待 R4；管路就緒）
   - 其他例外 / `False` → `fail`
   - 無 GCP 金鑰 → `skipped`

`overall` 取最差（precedence `fail > pending > skipped > ok`）。

### creds gate
`_gcp_creds_available()` = `GOOGLE_APPLICATION_CREDENTIALS` env 是否設定（確定性；CI 未設 → `skipped`）。文件註明 ADC 替代（`gcloud auth application-default login`）。

---

## 4. 今日誠實狀態

R4 的 `health_check` 仍 `NotImplementedError` → connectivity 步驟報 **`pending`**（非 `fail`），如實反映「管路接好、等 R4」。一條測試實例化**真實** `BigQueryStore` 鎖定 harness 能優雅處理 pending 狀態。

---

## 5. 不變量

只新增程式（`diagnostics.py` 增補、CLI 子命令、Makefile target、doc）+ 測試。
`bigquery_store.py` / `workflow.py` / `state.py` / `compliance.py` **不動**。無新增 runtime 依賴。

---

## 6. 測試（TDD，red-green-refactor）

`tests/test_bq_smoke.py`：
- config：ok（有 project）／ fail（project 空）。
- connectivity：no-creds → `skipped`；注入 store `health_check` 拋 `NotImplementedError` → `pending`；回 `True` → `ok`；拋其他例外 → `fail`。
- **真實 `BigQueryStore` → `pending`**（不碰該檔、驗證 harness 處理現況）。
- `overall` precedence。
- CLI：無 creds → 退出碼 0、輸出含步驟名。

---

## 7. R2 spec 勾選

D10 **維持 `[ ]` 未勾**（完整 G2 需 R4 的入庫資料煙測），但加註：架構面自評 + 管路煙測 harness 已完成，real-data 煙測 pending R4。

---

## 8. 交付物

程式 + 測試 · `docs/G2_readiness.md` · 本設計文件 · R2 spec D10 加註 · 專案記憶更新 · PR + admin-merge（沿用 #11/#12/#14/#18/#19 模式）。
