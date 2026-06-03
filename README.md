# Polaris Desk — Starter Repo 骨架

> 給 **R2 / 全員** 的開工骨架。設計原則：① 設定全走 `.env`　② 資料庫包一層 `VectorStore` 介面（換後端只改一行設定）。
>
> **🔁 2026-06-02 起：開發預設後端＝BigQuery（共用 canonical `polaris_core`）**，pgvector 改為離線 / Demo fallback。完整做法見 [`docs/開發環境_BigQuery.md`](docs/開發環境_BigQuery.md)。
>
> 這是**起手式**，不是完成品。每個 stub 都標了 `TODO` 給對應角色填。

---

## 0. 這個骨架解決什麼問題？

團隊在同一份共用資料（BigQuery `polaris_core`）上協作，個人實驗寫進自己的 scratch。本骨架讓你：

- **預設 BigQuery**：`.env` 預設 `VECTOR_BACKEND=bigquery`，讀共用 canonical `polaris_core`、寫自己的 `polaris_dev_<name>`（見 [SOP](docs/協作開發環境_SOP_v1.md)）
- **離線 fallback**：`.env` 把 `VECTOR_BACKEND` 改成 `pgvector`（Docker 一鍵起），**程式不動**——Demo Day 斷網或無雲端時用
- **W4 部署**：`Dockerfile` 已備好，推 Cloud Run

關鍵就在 `src/polaris/vectorstore/` —— 一個介面、兩個實作、一個工廠（換後端只改一個 env）。

---

## 1. 本地起步（5 步）

> **🐍 需求：Python 3.13**（團隊統一版本，已鎖在 `.python-version`）。
> 用 `uv` 會自動依 `.python-version` 抓 3.13；手動指定：`uv venv --python 3.13`。
> 沒裝 3.13 的話：`brew install python@3.13`（或 `uv python install 3.13`）。

**懶人一鍵**：`make setup`（建 3.13 venv + 裝依賴 + 產生 `.env` 範本），填 `.env` → `gcloud auth application-default login` → `make test`。下面是手動逐步版：

```bash
# 0) 建立 Python 3.13 虛擬環境（uv 會讀 .python-version）
uv venv --python 3.13

# 1) 複製設定檔
cp .env.example .env
#   填 GEMINI_API_KEY；BigQuery 預設值已填好，把 DEV_DATASET 的 <name> 換成你的英文名

# 2) 安裝相依套件（建議用 uv，沒有就用 pip）
uv sync           # 或：pip install -e ".[dev]"

# 3) 預設後端 BigQuery：登入 ADC（權限已由 SOP 開好）
gcloud auth application-default login
gcloud config set project polaris-desk-team
#   建自己的 scratch + 驗證讀取，見 docs/協作開發環境_SOP_v1.md §5
#   （離線 fallback 改走 pgvector：.env 切成 VECTOR_BACKEND=pgvector，再 make db-up）

# 4) 跑測試確認骨架正常（stub 模式，免雲端）
make test

# 5) 確認 VectorStore 工廠能依設定切換後端
python -c "from polaris.config import settings; from polaris.vectorstore.factory import get_vector_store; print('backend =', settings.vector_backend); print(type(get_vector_store()).__name__)"
```

---

## 2. 目錄結構

```
polaris-desk-starter/
├── .env.example              # 所有設定 / 金鑰範本（複製成 .env）
├── pyproject.toml            # 相依套件（uv / pip）
├── Dockerfile                # 上雲容器化（W4 用）
├── docker-compose.yml        # 本地 Postgres+pgvector
├── Makefile                  # 常用指令
└── src/polaris/
    ├── config.py             # 讀 .env（pydantic-settings）— 唯一設定來源
    ├── vectorstore/          # ★ 本地→雲端的關鍵抽象層
    │   ├── base.py           #   VectorStore 介面（抽象基底）+ 資料型別
    │   ├── pgvector_store.py #   本地實作（@R4）
    │   ├── bigquery_store.py #   雲端實作（@R4）
    │   └── factory.py        #   依 VECTOR_BACKEND 選實作
    ├── llm/gemini.py         # Gemini 用戶端封裝（@R2/@R3）
    ├── retrieval/retriever.py# 4-way 混合檢索骨架（@R3）
    └── graph/workflow.py     # LangGraph 5 節點骨架（@R2）
```

---

## 3. 各角色從哪個檔開工？

| 角色 | 先看 / 先填 | W1 目標 |
|---|---|---|
| **R2 架構師** | `graph/workflow.py`、`config.py` | LangGraph 5 節點骨架跑通 |
| **R3 Agent** | `retrieval/retriever.py`、`llm/gemini.py` | Retriever v0 → 4-way |
| **R4 資料** | `vectorstore/bigquery_store.py`（`pgvector_store.py` 為 fallback）| 入庫 BigQuery `polaris_core` |
| **R5 Eval** | （另開 `eval/`） | Ragas 環境 + 題庫 |
| **R7 全端** | （另開 `web/`，Next.js / Chainlit） | 前端骨架 |

---

## 4. 後端切換：BigQuery（預設）↔ pgvector（fallback）

```bash
# 預設（雲端共用 canonical）— .env 裡：
VECTOR_BACKEND=bigquery
GCP_PROJECT=polaris-desk-team
BQ_DATASET=polaris_core            # 讀共用 canonical
DEV_DATASET=polaris_dev_<name>     # 寫自己的 scratch
#   認證：gcloud auth application-default login

# 離線 / Demo fallback — 改 .env：
VECTOR_BACKEND=pgvector
DATABASE_URL=postgresql://polaris:polaris@localhost:5432/polaris
#   先 make db-up 起本地 Postgres+pgvector
```

**程式碼一行都不用改** —— `get_vector_store()` 會自動回對的實作。這就是抽象層的價值。

> ⚠️ **金鑰永不進 git**：`.env` 已列在 `.gitignore`。雲端用 ADC 或 GCP Secret Manager，不要把 key 寫死。
> 詳細協作規則（讀 core / 寫 scratch / 成本護欄）見 [`docs/協作開發環境_SOP_v1.md`](docs/協作開發環境_SOP_v1.md) 與 [`docs/開發環境_BigQuery.md`](docs/開發環境_BigQuery.md)。

---

## 5. 上雲（W4）

```bash
# 本地建 image 測試
docker build -t polaris-desk .
docker run --env-file .env -p 8000:8000 polaris-desk

# 推 Cloud Run（示意，細節 W4 再補）
# gcloud run deploy polaris-desk --source . --region asia-east1
```

---

## 6. 規格文件（Spec Kit）

本 repo 已跑過 `specify init`，規格與指令隨 repo 走（推上 GitHub 後組員都拿得到）：

- **`docs/spec-kit/`** — 專題 spec + 7 角色 spec + `Spec Kit 導讀.html` + demo 場景草稿（**權威版**）
- **`docs/協作開發環境_SOP_v1.md`** — GCP／BigQuery 協作環境建置 + onboarding + 成本護欄 SOP（**R4 建置、全員 onboarding 必讀**）
- **`docs/開發環境_BigQuery.md`** — 「開發改用 BigQuery」一頁速懂（人 + agent 怎麼切、怎麼跑、fallback）
- **`.specify/memory/constitution.md`** — 專題憲法（`/speckit-*` 指令會讀）
- **slash 指令**（Claude Code / Cursor）：`/speckit-constitution`、`/speckit-specify`、`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`（選用 `/speckit-clarify`、`/speckit-analyze`、`/speckit-checklist`）

> 先讀 `docs/spec-kit/README.md`。改 spec 以本 repo 版為準，再同步回 Drive。

### W1 D1 已交付：`specs/001-langgraph-skeleton/`

5 節點 LangGraph 骨架（stub mode）— US1 + US2 + US3 全綠（70/70 tests）。

| 檔 | 內容 |
|---|---|
| `spec.md` | 3 個 user story、10 條 FR、7 條可量測 SC |
| `plan.md` | 技術計畫 + Constitution Check（6 原則 ALL PASS） |
| `research.md` | 4 個技術決策（節點拆分 / @traced / 例外處理 / Compliance） |
| `data-model.md` | `Citation` / `NodeTrace` / `ResearchState` |
| `contracts/workflow-invoke.md` | `app.invoke()` 對外契約 + versioning |
| `tasks.md` | 26 個任務（4 階段 + Polish）、依賴圖、平行機會 |
| **`quickstart.md`** | **5 分鐘讓任何隊友把骨架跑起來** ← 隊友從這開始 |

跑法：`pip install -e ".[dev]"` → `pytest` → `python -m polaris.cli ask "..."`。詳見 `specs/001-langgraph-skeleton/quickstart.md`。

---

_對應文件：4 週航程作戰計畫 §W1 / Notion 開工清單與本地上雲指南 / PRD v1.1.1 §18 Data Model_
