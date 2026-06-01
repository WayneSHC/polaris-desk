# Implementation Plan: LangGraph 5-Node Skeleton (Stub Mode)

**Branch**: `r2/001-langgraph-skeleton` | **Date**: 2026-05-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-langgraph-skeleton/spec.md`

## Summary

把現有 starter 的 5 節點 LangGraph 骨架（`src/polaris/graph/workflow.py`）擴充成符合 spec 的 deterministic stub 模式：補上 `Citation` / `NodeTrace` 型別、Compliance 關鍵字攔截、空輸入守門、節點例外安全中止、與一個可以 reproduce 的 e2e 測試。**不呼叫任何 LLM、不連任何 DB**，所有節點回固定假資料，token cost = $0，跑 3 次結果完全相同。這層骨架是 R3/R4/R6 之後把真 agent / retriever / 規則一顆顆換進去的整合契約，也是 R5 寫 e2e 驗收與 snapshot 測試的對象。

## Technical Context

**Language/Version**: Python 3.11+ (pyproject 已釘 `requires-python = ">=3.11"`)

**Primary Dependencies**:
- `langgraph >= 0.6`（StateGraph 編排）
- `pydantic >= 2.7`（Citation / NodeTrace dataclass，與 LangGraph state 共用）
- W1 D1 stub mode **不引入** `google-genai`、`cohere`、`psycopg`、`rank-bm25`（已在 pyproject 但這顆 feature 不 import）

**Storage**: N/A — 純 in-memory state，stub 模式無持久化

**Testing**: `pytest >= 8.2` + snapshot-style assertion（不引入額外 snapshot 套件，用 `==` 比對固定 fixture）

**Target Platform**: macOS / Linux 本機開發；W4 後上 Cloud Run（不在本 feature scope）

**Project Type**: Single Python package (`src/polaris/`)

**Performance Goals**: SC-004 — 端到端 < 10 秒（stub 無 LLM、無 I/O，實測應 < 100ms；上限寬鬆是給未來節點 hook 升級用）

**Constraints**:
- Deterministic — 同問題重跑 3 次結果完全相同（SC-006）
- 工作流結構與節點實作分離 — 換節點不改 workflow 定義檔（FR-007 / SC-005）
- 不得有任何 LLM / DB 呼叫（Constitution III 本地優先 + W1 D1 cost = $0）

**Scale/Scope**: 1 範例問題 × 3 重跑驗證；Compliance 攔截 6 關鍵字 × 雙向（含/不含）測試案例

## Constitution Check

> 對 `.specify/memory/constitution.md` 6 原則逐一檢視。

| Principle | 本 feature 如何遵循 | 證據 |
|---|---|---|
| **I. NFR-031（買賣建議攔截）** | Compliance 節點以關鍵字清單攔截 Writer 草稿，最終輸出 0 買賣建議 | spec FR-005、SC-003；本 plan §Phase 1 `compliance.py` |
| **II. 引用接地** | `answer` 每次回傳必含 `citations` 欄位（W1 stub citation 含 source_id + snippet），為後續 grounding metric 留位 | spec FR-004、Key Entities `Citation` |
| **III. 本地優先 · 金鑰安全** | W1 D1 stub 模式 0 LLM / 0 DB → 0 金鑰需求；測試在本機 pytest 跑完 | 不 import `google-genai`、`psycopg` |
| **IV. Eval 即品質門檻** | SC-006 確定性 → R5 可寫 snapshot 測試，CI 跑 1 個確定性 fixture 不花 token | quickstart.md 跑法 |
| **V. Demo 可重現 + 離線備援** | Stub mode 本身就是「斷網可跑」的離線備援雛形 | 整個 feature 不需網路 |
| **VI. 最新技術棧** | 用 LangGraph `StateGraph`（pyproject 0.6+）；無 LLM 呼叫 → 不會誤用舊版 Gemini SDK | pyproject 已釘版本 |

**Gate result**: ✅ ALL PASS — 0 violations, no entries in Complexity Tracking needed.

**Post-Phase 1 re-check**: 設計後 6 原則仍全部 PASS（見本檔末尾「Re-check after Phase 1」段）。

## Project Structure

### Documentation (this feature)

```text
specs/001-langgraph-skeleton/
├── spec.md                     # ✅ /speckit-specify 產出
├── plan.md                     # ✅ 本檔（/speckit-plan 產出）
├── research.md                 # ✅ Phase 0 產出
├── data-model.md               # ✅ Phase 1 產出
├── quickstart.md               # ✅ Phase 1 產出
├── contracts/
│   └── workflow-invoke.md      # ✅ Phase 1 產出
├── checklists/
│   └── requirements.md         # ✅ /speckit-specify 產出
└── tasks.md                    # ⏳ 由 /speckit-tasks 產出（不在本指令）
```

### Source Code (repository root)

```text
src/polaris/
├── graph/
│   ├── __init__.py
│   ├── state.py                # 🆕 ResearchState / Citation / NodeTrace（pydantic + TypedDict）
│   ├── workflow.py             # 🔧 既有檔擴充：edges 不變、節點 import 改指向 nodes/
│   ├── nodes/
│   │   ├── __init__.py         # 🆕
│   │   ├── stubs.py            # 🆕 5 個確定性 stub 節點（planner/retriever/calculator/writer/compliance）
│   │   └── trace.py            # 🆕 NodeTrace 共用裝飾器：自動記 status/input_keys/output_keys/error
│   └── compliance.py           # 🆕 純函式：apply_compliance(draft) → (final_text, status)
├── llm/                        # （未動 — W1 D2+ R3 使用）
├── retrieval/                  # （未動 — W1 D3+ R3 使用）
├── vectorstore/                # （未動 — R4 W1）
├── config.py                   # （未動）
└── cli.py                      # 🆕 `python -m polaris.cli ask "問題"` 入口

tests/
├── test_vectorstore_factory.py # （既有）
├── test_state.py               # 🆕 ResearchState / Citation / NodeTrace 序列化、欄位驗證
├── test_compliance.py          # 🆕 6 關鍵字攔截 100%、合規草稿原封不動
├── test_workflow_e2e.py        # 🆕 端到端：跑通、3 次重跑相同、5 節點 trace 齊全
└── test_workflow_edges.py      # 🆕 空輸入守門、節點拋例外時的中止行為
```

**Structure Decision**:

- 選 **Option 1: Single project** — 與既有 starter `src/polaris/` 一致，無前後端分離需求（前端 W4 R7 另起 repo / Vercel）。
- **既有 `src/polaris/graph/workflow.py` 的 5 節點 inline 函式 + `build_workflow()` 的 edges 串接結構不改**；改的是「節點實作搬到 `nodes/stubs.py`」+ workflow.py 變成純 wiring。這個拆分是 FR-007 / SC-005「換節點不動 workflow 定義」的關鍵。
- `compliance.py` 抽成獨立純函式 module，讓 R6 W3 補完整關鍵字 / 規則時不必動 LangGraph wiring，也方便單元測試。

## Complexity Tracking

> Constitution Check 全部 PASS，無需 justification。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Phase 0: Research

Research.md 產出，解決下列 4 個技術選擇：

1. **節點實作搬位置 vs inline**：搬到 `nodes/stubs.py` 模組，workflow.py 只剩 wiring。
2. **NodeTrace 怎麼收集**：用裝飾器包每顆節點函式，自動在每次 invoke 累加進 state 的 `trace` list。
3. **節點例外處理**：在裝飾器層 try/except，將 error 寫進 trace，回傳「跳到 END」訊號（LangGraph conditional edge 收掉）。
4. **Compliance 關鍵字策略**：W1 用簡單 substring 黑名單；改寫策略 = 攔截後回固定安全訊息「本系統不提供買賣建議，僅描述事實」（不嘗試自動改寫——成本高、易引入新風險）。

詳見 [research.md](research.md)。

## Phase 1: Design & Contracts

### Data model
- `Citation`（pydantic BaseModel）：`source_id: str`、`snippet: str`、`origin: Literal["stub","bm25","embedding","colpali","rerank","news"]`
- `NodeTrace`（pydantic BaseModel）：`node_name: str`、`status: Literal["ok","error","skipped"]`、`input_keys: list[str]`、`output_keys: list[str]`、`error_message: str | None`、`elapsed_ms: int`
- `ResearchState`（TypedDict，沿用 LangGraph 慣例）：擴充既有 `PolarisState`，加 `citations: list[Citation]`、`compliance_status: Literal["passed","blocked","rewritten","unknown"]`、`trace: list[NodeTrace]`，並改名 `query` → 兩個欄位都接受（`query` alias for backwards compat 給 starter `__main__`）。

詳見 [data-model.md](data-model.md)。

### Contracts
- **`workflow-invoke.md`**：`app.invoke({"query": str}) -> dict` 的輸入/輸出契約、空輸入行為、節點例外行為。

詳見 [contracts/workflow-invoke.md](contracts/workflow-invoke.md)。

### Quickstart
- 跑 `pytest tests/test_workflow_e2e.py -v`
- 跑 `python -m polaris.cli ask "台積電 2025 Q1 營收 YoY"`
- 預期 stdout 範例

詳見 [quickstart.md](quickstart.md)。

### Agent context update
- 已將 `CLAUDE.md` 的 `<!-- SPECKIT START -->` 區段更新指向本 plan.md。

## Re-check after Phase 1

| Principle | Phase 1 設計後仍 PASS？ |
|---|---|
| I. NFR-031 | ✅ `compliance.py` 純函式 6 關鍵字攔截，contracts 文件已寫明攔截後輸出 |
| II. 引用接地 | ✅ `Citation` 模型 + `citations` 欄位納入 state 與輸出契約 |
| III. 本地優先 · 金鑰安全 | ✅ 設計檔案無任何 `google-genai` / `psycopg` import |
| IV. Eval 即品質門檻 | ✅ 確定性 stub + 3 次重跑相同的測試已列入 tasks 預備 |
| V. Demo 可重現 + 離線備援 | ✅ 整顆 feature 0 網路、0 LLM |
| VI. 最新技術棧 | ✅ 只 import langgraph + pydantic + stdlib |

**Final gate**: ✅ ALL PASS — Phase 2 (`/speckit-tasks`) 可開始。
