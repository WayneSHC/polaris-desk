<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-langgraph-skeleton/plan.md`
<!-- SPECKIT END -->

# Polaris Desk — 給 coding agent 的專案守則

**權威規格**：repo 內 `.specify/memory/constitution.md`（憲法）；團隊完整規格在
Google Drive `Polaris Desk/03_規格書_PRD/spec-kit/`（專題 spec + 7 角色 spec）。

**硬約束（憲法，違反 = No-Go）**：
- 🔴 **NFR-031**：不得產出任何買賣建議（投顧執照風險）。
- 🔑 **金鑰**只放 `.env` / Secret Manager，永不 commit（`.env` 已 gitignore）。
- **引用接地**：每句結論 / 每個數字都要有來源。
- **技術棧**：`google-genai` 新 SDK + `gemini-3-*-preview` + `gemini-embedding-2`（768/cosine），**非**舊版 `google-generativeai`。
- **向量庫**：`VECTOR_BACKEND=pgvector`（本地，W1-W3）→ `bigquery`（W4 上雲），介面已抽象；pgvector 查詢用 `<=>`。

**Spec Kit 指令**：`/speckit-constitution`、`/speckit-specify`、`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`（選用：`/speckit-clarify`、`/speckit-analyze`、`/speckit-checklist`）。
