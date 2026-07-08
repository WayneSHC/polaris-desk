# 測試指南（無 UI）— 給人 + AI agent 共用

> **目的**：UI（R7）還沒好之前，怎麼驗證「整條流程是對的」。
> 整個系統 **CLI / API 優先** 設計，不需要前端就能端到端測。
> **本檔可直接餵給 coding agent**（Claude Code / Codex / Antigravity）執行 —— 已標好
> 「🤖 AGENT 可自動跑」與「🧑 HUMAN 必須親自做」的分界。

---

## 給 AI agent 的執行守則（先讀這段）

你可以**自動執行**所有 `🤖` 步驟，並用每步附的「預期輸出」自我驗證通過與否。
遇到 `🧑 HUMAN STEP` **必須停下、把指示貼給使用者、等他完成後再繼續** —— 原因：

- **金鑰**（`GEMINI_API_KEY` 等）你沒有，且憲法規定金鑰**永不 commit / 永不寫進 git**。
  你只能偵測「缺金鑰」並請使用者填，**絕不可**把任何 key 寫死或猜測。
- `gcloud auth application-default login` 是互動式瀏覽器登入，你無法完成。
- `DEV_DATASET=<name>` 要填使用者本人的英文名，你不知道。

任何一步「預期輸出」對不上 → **停下回報**，別硬跑下一步。

---

## 前置需求

- macOS / Linux，已裝 `uv`（沒有：`brew install uv` 或見 README）
- Python 3.13（`make setup` 會依 `.python-version` 自動抓；硬約束，別用其他版本）
- 在 repo 根目錄執行所有指令

---

## Step 0 —— 建環境　🤖（含 1 個 🧑 子步驟）

```bash
make setup
```
**預期輸出**：結尾出現 `✅ 環境就緒（Python 3.13）`，且產生 `.venv/` 與 `.env`。

### 🧑 HUMAN STEP — 填 `.env`（agent 在此停下）
打開 `.env`，完成三件事：
1. `GEMINI_API_KEY=` 後面貼上你的 key（**必填**才有真答案；只跑 smoke/單元測試可暫時留空）
2. `DEV_DATASET=polaris_dev_<name>` 把 `<name>` 換成你的英文名
3. 預設後端是 BigQuery，登入 ADC：
   ```bash
   gcloud auth application-default login
   ```
> 🔌 **離線 / 無雲端**：把 `.env` 改成 `VECTOR_BACKEND=pgvector`，再 `make db-up`，
> 即可跳過 `gcloud` 登入。其餘步驟不變。

---

## Step 1 —— 驗證骨架（無雲端、無金鑰、確定性）　🤖

先跑這個；這關不過，後面都不用看。

```bash
make test          # pytest stub 模式，token=0、確定性
make check-keys    # = python -m polaris doctor，列出哪些金鑰已設（G1 閘門）
```
**預期輸出**：
- `make test` → 全綠，結尾 `passed`，無 `failed` / `error`
- `make check-keys` → 一張金鑰清單；缺 `GEMINI_API_KEY` 會標未設（這在純骨架測試 OK）

❌ 若 `make test` 紅 → 停下回報，這是環境或程式碼問題，不是測資問題。

---

## Step 2 —— 單題跑真 workflow　🤖（要真答案需先完成 Step 0 的 🧑 金鑰）

最小的「流程對不對」檢查：

```bash
python -m polaris.cli ask "台積電 2025 Q1 營收 YoY"
```
**預期輸出**：一段含 **answer + compliance_status + citations** 的結果。
人工 sanity check：
- 每個數字 / 結論都有 citation（引用接地）
- **沒有**任何買賣建議字眼（NFR-031 紅線）
- 同業比較類問題會自動改走 Deep Research

邊界 demo：
```bash
python -m polaris.cli ask ""                    # 空輸入守門
python -m polaris.cli ask "..." --stub-buysell  # 紅線偵測 demo
```

---

## Step 3 —— 整條 pipeline 跑題庫（核心正確性閘門）　🤖

把題庫每一題都送進**和 UI 相同的引擎**（`app.invoke` / `run_deep_research`）。

```bash
make eval-smoke         # 前 5 題、token=0；出現買賣建議 → exit code 1
python -m polaris.eval  # 全題庫 → 達標率 + 不及格清單（Markdown 報告）
```
**怎麼讀報告**：
- 報告會標 **「煙測分、非 G3 真分」** —— 綠燈代表*管路接通*，**不是**答案品質過關，別混淆。
- 看「不及格清單」對應的**題號**找出哪題壞了。
- exit code = `1` → 某題踩到買賣建議紅線，**必須修**。

### 要 Ragas 真分（CP/Faithfulness/AR）
```bash
uv pip install -e '.[eval]'    # 加裝 ragas + langchain-google-genai
# 確認 GEMINI_API_KEY 已設，然後：
python -m polaris.eval
```
門檻：CP ≥0.85 / Faithfulness ≥0.90 / AR ≥0.85。
沒裝 extra 或沒金鑰 → 誠實印 `None`，**絕不假分**。

---

## Step 4 —— 端到端打 API（UI 未來對接的同一介面）　🤖

R7 的 UI 會 POST 這些 endpoint，所以現在打它們 = 測真整合邊界。

```bash
make serve-api    # FastAPI 起在 :8000（/healthz · /ask · /research）
```
另開一個終端：
```bash
curl -s localhost:8000/healthz
curl -s localhost:8000/ask \
  -H 'content-type: application/json' \
  -d '{"query":"台積電 2025 Q1 營收 YoY"}'
curl -s localhost:8000/research \
  -H 'content-type: application/json' \
  -d '{"question":"台積電 vs 聯電 毛利率比較"}'
```
**預期輸出**：
- `/healthz` → `{"status":"ok"}` 之類
- `/ask` → `{answer, compliance_status, citations, trace}`
- `/research` → `{final_answer, evidence, react_steps, status, compliance_status}`

不想寫 curl：開 `http://localhost:8000/docs`（Swagger UI）逐一點測。
通知流另有 `http://localhost:8000/demo/notifications` 可看。

### 前端本機開發要接哪個後端　🤖

雲端 `polaris-api` 已收口 `ingress=internal-and-cloud-load-balancing`（上雲 runbook
§8.1）：**從本機直打它的 run.app URL 一律被 Google 前端擋成 404**——這是刻意設計，
不是 URL 失效。所以前端本機開發一律先起本地後端：

```bash
make serve-api                 # 後端起在 :8000
cd frontend && npm run dev     # next dev 的 /api proxy 預設指向 http://localhost:8000
```

要打其他後端（例如同事的 dev 環境）就覆寫 runtime env：

```bash
BACKEND_API_URL=https://<其他後端> npm run dev
```

雲端部署（`polaris-web`）不用設：production 預設仍是 polaris-api 的 run.app URL，
經 VPC connector 視為內部流量、通得了。

---

## Step 5（選用）—— 雲端管路煙測　🤖

```bash
make bq-smoke     # 驗 BigQuery 接線（G2）；不需 R4 已入庫資料
```

---

## 建議順序

`make test` → `python -m polaris.cli ask "…"` → `make eval-smoke` → `make serve-api` + Swagger。
Step 1–4 全程不需 UI，已涵蓋端到端。

---

## 疑難排解

| 症狀 | 可能原因 | 處置 |
|------|----------|------|
| `make setup` 抓不到 Python 3.13 | 沒裝 3.13 | `uv python install 3.13` 或 `brew install python@3.13` |
| `make test` 紅 | 程式碼 / 環境問題 | 看 traceback；非測資問題，回報 owner |
| 跑測試報 `ModuleNotFoundError`（如 `rank_bm25`）但套件其實裝了 | 用了 `uv run pytest`，PATH 解析到全域 / conda 的 `pytest`（非 venv） | 改用 `make test`、`.venv/bin/pytest` 或 `uv run python -m pytest`（強制走 venv 直譯器）|
| `ask` 回空 / fallback 內容 | 缺 `GEMINI_API_KEY` 或未登入 ADC | 回到 Step 0 🧑 |
| BigQuery 權限錯 | 未 `gcloud auth application-default login` | 跑該登入；或改 `VECTOR_BACKEND=pgvector` 走離線 |
| eval 報告全綠但仍不放心 | 那是**煙測分**非真分 | 裝 `.[eval]` extra + 金鑰跑真 Ragas |
| `python -m polaris.eval` exit 1 | 某題踩買賣建議紅線 | 看不及格清單題號，回報題庫 owner（R5/R6）|
| 直接 curl 雲端 polaris-api 的 run.app URL 全路徑 404（Google 404 頁）| ingress 已收 internal（上雲 runbook §8.1），公網本來就打不到 | 非故障。本機開發走「前端本機開發要接哪個後端」；驗雲端請經 `polaris-web` 的 `/api/*` proxy |

---

## 相關文件

- **Vision-OCR（圖表/掃描頁→文字）測試與驗證**：[`docs/vision-OCR_測試與驗證指南.md`](vision-OCR_測試與驗證指南.md) —— R1 Gate1 / R5 Gate2 / R7 前端怎麼驗、怎麼確認在動
- 規格：`specs/004-eval-pipeline/spec.md`（eval pipeline）
- R5 開工：`docs/R5_eval_開工指南.md`
- 環境 / 後端切換：`README.md`、`docs/開發環境_BigQuery.md`、`docs/協作開發環境_SOP_v1.md`
- 金鑰：`docs/keys-setup.md`
- 閘門：`docs/G1_readiness.md` · `docs/G2_readiness.md` · `docs/G3_readiness.md`
