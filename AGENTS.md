# Polaris Desk — AI Agent 跨工具守則（AGENTS.md）

> **這是跨工具的「單一事實來源」(single source of truth)。**
> OpenAI **Codex**、Google **Antigravity**（≥ v1.20.3）、**Cursor** 等都會自動讀本檔。
> Claude Code 讀 `CLAUDE.md`、Antigravity 另讀 `GEMINI.md` —— 那兩個是本檔的鏡像／指標。
> **要改規則，請改這裡（AGENTS.md），再同步另外兩個檔。**

## 🚀 一鍵建環境（Setup）

第一次進專案（**人或 AI agent 都一樣**），在 repo 根目錄跑：

```bash
make setup     # 建 Python 3.13 venv + 裝依賴 + 產生 .env 範本（idempotent，可重跑）
```

然後：① 打開 `.env` 填 `GEMINI_API_KEY`（**金鑰自己填，agent 不要碰**）② `gcloud auth application-default login`（預設後端 BigQuery；確認 `.env` 的 `GCP_PROJECT`/`BQ_DATASET`/`DEV_DATASET`）③ `make test`（基準：70 passed，stub 模式免雲端）。離線 fallback 才需 `make db-up` 起 pgvector。

> `make test` / `make lint` 走 `uv run`，**不需先 `activate` venv**。沒有 `make` 時的等效手動指令見下方「Python 3.13」段。

## 🐍 Python 3.13（最重要的環境約束）

- 開發 / CI 一律用 **Python 3.13**。版本已鎖在 `.python-version`（uv / pyenv 會自動選），`pyproject.toml` 也設 `requires-python>=3.13`。
- 建環境（建議用 uv）：
  ```bash
  uv venv --python 3.13          # uv 也會自動讀 .python-version
  uv pip install -e ".[dev]"
  uv run pytest                  # 70 passed 為基準
  ```
- **不要**用其他 Python 版本起 venv；沒裝 3.13 用 `brew install python@3.13` 或 `uv python install 3.13`。

## 硬約束（憲法，違反 = No-Go）

- 🔴 **NFR-031**：不得產出任何買賣建議（投顧執照風險）。新聞 / 分析只描述、標證據、標矛盾。
- 🔑 **金鑰**只放 `.env` / Secret Manager，**永不 commit**（`.env` 已 gitignore；只有 `.env.example` 範本進 git）。
- **引用接地**：每句結論 / 每個數字都要有來源。
- **技術棧**：`google-genai` 新 SDK + `gemini-3-*-preview` + `gemini-embedding-2`（768 維 / cosine），**非**舊版 `google-generativeai`。
- **向量庫**：**預設 `VECTOR_BACKEND=bigquery`**（共用 canonical `polaris_core`；2026-06-02 起為開發後端）。pgvector 改為離線 / Demo fallback（一個 env 切換）。**不要把預設改回 pgvector。** 寫入一律進自己的 `polaris_dev_<name>`、**不可寫 `polaris_core`**（例外：2026-06-08 起經 PM 同意，R1／R4 帳號 + R4 GCE 預設 SA 有 `polaris_core` WRITER 做 ingestion；一般開發者與 agent 仍不可寫，schema/index 變更走 SOP §7 PR — 別自行「修正」這份 ACL）。pgvector fallback 查詢用 `<=>`（不要用 `<->` / `<#>`）。完整做法見 `docs/開發環境_BigQuery.md` + `docs/協作開發環境_SOP_v1.md` §3.4。

## 協作流程

- **不直接推 `main`**：開分支 → push → 開 PR。**不要自己按 Merge** —— 由 code owner（**R2**）審核批准、且 **CI 測試綠燈**後才放行（`main` 已設分支保護 + CODEOWNERS + 必過 CI）。
  ```bash
  git switch -c r3/retriever-v0
  git push -u origin r3/retriever-v0   # 再到 GitHub 開 PR，等 R2 review + CI 過
  ```
- 權威規格：`.specify/memory/constitution.md`（憲法）；完整角色 / 專題 spec 在 `docs/spec-kit/`。
- Spec Kit 指令（Claude Code）：`/speckit-specify`、`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`（選用 `/speckit-clarify`、`/speckit-analyze`、`/speckit-checklist`）。
