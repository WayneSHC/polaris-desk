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

然後：① 打開 `.env` 填 `GEMINI_API_KEY`（**金鑰自己填，agent 不要碰**）② `make db-up`（起本地 pgvector）③ `make test`（基準：70 passed）。

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
- **向量庫**：`VECTOR_BACKEND=pgvector`（本地，W1–W3）→ `bigquery`（W4 上雲），介面已抽象；pgvector 查詢用 `<=>`（不要用 `<->` / `<#>`）。

## 協作流程

- **不直接推 `main`**：開分支 → PR → 1 人 review → 合（`main` 已設分支保護）。
  ```bash
  git switch -c r3/retriever-v0
  git push -u origin r3/retriever-v0   # 再到 GitHub 開 PR
  ```
- 權威規格：`.specify/memory/constitution.md`（憲法）；完整角色 / 專題 spec 在 `docs/spec-kit/`。
- Spec Kit 指令（Claude Code）：`/speckit-specify`、`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`（選用 `/speckit-clarify`、`/speckit-analyze`、`/speckit-checklist`）。
