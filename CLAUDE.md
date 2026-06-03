<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-langgraph-skeleton/plan.md`
<!-- SPECKIT END -->

# Polaris Desk — 給 coding agent 的專案守則

> 跨工具單一事實來源＝ [`AGENTS.md`](./AGENTS.md)（Codex / Antigravity / Cursor 讀它）。
> 本檔為 **Claude Code** 鏡像；改規則時請同步 `AGENTS.md`（與 `GEMINI.md`）。

**權威規格**：repo 內 `.specify/memory/constitution.md`（憲法）；團隊完整規格在
Google Drive `Polaris Desk/03_規格書_PRD/spec-kit/`（專題 spec + 7 角色 spec）。

**硬約束（憲法，違反 = No-Go）**：
- 🔴 **NFR-031**：不得產出任何買賣建議（投顧執照風險）。
- 🔑 **金鑰**只放 `.env` / Secret Manager，永不 commit（`.env` 已 gitignore）。
- **引用接地**：每句結論 / 每個數字都要有來源。
- **技術棧**：`google-genai` 新 SDK + `gemini-3-*-preview` + `gemini-embedding-2`（768/cosine），**非**舊版 `google-generativeai`。
- **向量庫**：**預設 `VECTOR_BACKEND=bigquery`**（共用 canonical `polaris_core`，2026-06-02 起）；pgvector 為離線 / Demo fallback（一個 env 切換，**別改回預設**）。寫入只進自己的 `polaris_dev_<name>`、**不可寫 `polaris_core`**；pgvector fallback 查詢用 `<=>`。詳見 `docs/開發環境_BigQuery.md`。
- **🐍 Python 3.13**：開發 / CI 一律用 **Python 3.13**（已鎖在 `.python-version`，`pyproject.toml` 也設 `requires-python>=3.13`）。建環境：`uv venv --python 3.13 && uv pip install -e ".[dev]"`。**不要**用其他版本起 venv。

**Spec Kit 指令**：`/speckit-constitution`、`/speckit-specify`、`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`（選用：`/speckit-clarify`、`/speckit-analyze`、`/speckit-checklist`）。
