# R2 W4 — thin FastAPI（/ask + /research）+ D19–20 部落格內容 — 設計

**日期**：2026-06-04 **角色**：R2 架構師 **對應**：R2 spec D20–22（上雲 / R7 對接）、D19–20（部落格）
**範圍決策**：使用者選「`/ask` + `/research` 都做」（完整實作 R7 已公布契約）。

## A. Thin FastAPI 後端 `src/polaris/api.py`

### 問題
W4 上雲 prep（PR #44）已備好部署機制 + 健康骨架，但容器只回 `/healthz`、不服務產品。R7 前端（Vercel）要對接 HTTP，且 **R7 開工指南 §2 已公布契約**（`POST /ask`、`POST /research`，欄位名鎖定）。需把既有引擎包成符合該契約的 HTTP。

### 設計
- **相依**：`fastapi` + `uvicorn` 進 `[project.dependencies]`（純 Python、無 torch → CI 仍 token-free）。
- **端點（欄位一字不差對齊 R7 §2）**：
  - `GET /healthz` → 重用 `polaris.server.health_payload()`（DRY，不重複健康邏輯）。
  - `POST /ask` `{query}` → `build_workflow().invoke({"query": query})` → `{answer, compliance_status, citations[], trace[]}`。
  - `POST /research` `{question}` → `run_deep_research(question)` → `{final_answer, evidence[], react_steps[], status, compliance_status}`。
- **模型**：回應重用引擎既有 pydantic 型別 `Citation`/`NodeTrace`/`ReActStep` → 序列化不會與引擎漂移；`DeepResearchResult`（dataclass）映射進 `ResearchResponse`。
- **入口**：`main()` 跑 uvicorn 於 `resolve_port()`（重用 `server.py`）；`python -m polaris.api`。Dockerfile `CMD` → `python -m polaris.api`。
- **薄轉接**：只做「HTTP ↔ 既有函式」，**不碰** graph/state/compliance/Deep Research 本體。無金鑰走 fallback → API 仍可端到端回應。
- **`server.py` 保留**為 stdlib 零依賴的離線健康檢查 + 共用 helper（`resolve_port`/`health_payload`）來源。

### 測試（TDD）
`tests/test_api.py`（FastAPI `TestClient`、token-free）：`/healthz` 200；`/ask` 回契約鍵 + 合法 `compliance_status` + citation 欄位 + trace node_name/status；`/research` 回 §2b 契約鍵 + `status∈{answered,exhausted}` + react_steps thought/action；缺 body→422；未知路徑→404。第三方 `StarletteDeprecationWarning` 以 `filterwarnings` 濾掉保持輸出乾淨。

### 不變量 / 安全
不碰 graph/workflow/state/stubs/compliance/R4（5 節點 trace + node_swap 不變）；CI token-free；無金鑰 fallback 可回應。

## B. D19–20 部落格內容 `docs/blog/`

兩篇技術部落格（繁中、house style、引用真實 repo 碼、誠實不浮誇、NFR-031-aware）：
1. **`01_workflow_vs_agent.md`**：Anthropic「Building Effective Agents」的 workflow vs agent 區分；Polaris Desk 為何主路徑用確定性 5 節點 Workflow（Orchestrator–Workers）、開放式研究用真自主 Agent（Deep Research ReAct）；共用 Compliance 閘；hybrid 取捨。源：PRD v1.1 agentic audit + AQ-03。
2. **`02_deep_research_agent.md`**：自寫 ReAct loop（為何棄 prebuilt `create_react_agent`，AQ-03）、bounded ≤6 迴圈 + ≥3 引用（FR-004）、evidence 去重、verify-or-synthesize 接地（D16）、fail-to-deterministic、NFR-031。源：D11/D13/D15/D16 設計文件。

## 交付
單一 PR（API + blog + 連動 Dockerfile/compose/runbook/Makefile + 本設計文件），API 走 TDD，含 `python -m polaris.api` 的 Docker 煙測。R2 spec D19–20 `[x]`、D20–22 註記更新（repo + Drive 鏡像）；memory 更新。
