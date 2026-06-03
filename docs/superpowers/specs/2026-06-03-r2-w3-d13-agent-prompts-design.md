# R2 W3 D13 — Agent prompt 優化（中央 prompt registry + Deep Research ReAct prompt）設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：FR-004（Deep Research ReAct agent）、NFR-031（無買賣建議）、接地/引用、R2 spec §3 W3 D13
**前置**：D11（AQ-03 決策＝自寫 ReAct loop + 狀態設計）、planner/writer/compliance agent（D2/D3/D9）
**範圍**：用戶選「兩者都做」＝① 中央化 + 精煉現有 prompt；② 新增 Deep Research ReAct prompt 機制

---

## 1. 目的

D13 在 Deep Research 序列（D11 狀態 → **D13 prompt** → D15 loop → D16 驗收）中，交付 D15 ReAct loop 要消費的 prompt + 工具協定 + action parser；同時把散落 3 個 agent 模組的 system prompt 中央化，消除 NFR-031「無買賣建議」「接地」語句的重複（易 drift）。

---

## 2. Part A — 中央 prompt registry `src/polaris/graph/prompts.py`

leaf 模組（只用 stdlib，不 import 任何 agent → 無循環）。

### 共用片段（single source of truth）
- `NO_ADVICE_CLAUSE`：NFR-031 —— 嚴禁任何買賣建議（建議買進/賣出、加減碼、看多看空、進場時機等）。
- `GROUNDING_CLAUSE`：每個關鍵數字/主張標註對應來源 `source_id`；找不到依據就明說資料不足、不臆測。

### 四個 system prompt（由片段組成、精煉、**保留原意/行為**）
- `PLANNER_SYSTEM_PROMPT`（規劃：拆 2–5 步、最後一步指向引用接地）
- `WRITER_SYSTEM_PROMPT`（撰寫：依 contexts、逐句標 source_id）
- `COMPLIANCE_SYSTEM_PROMPT`（**偵測器**：判斷文字是否含顯性/隱性買賣建議；與生成型 prompt 不同框架）
- `REACT_SYSTEM_PROMPT`（Deep Research：think→act→observe 協定 + 接地 + 無建議 + ≤6 迴圈/≥3 引用意識 + 可解析 action 格式）

### 既有模組重構（零行為變更）
`planner_agent` / `writer_agent` / `compliance_agent` 改 `from polaris.graph.prompts import ... as SYSTEM_PROMPT`，並**重新導出**原常數名（`SYSTEM_PROMPT` / `COMPLIANCE_SYSTEM_PROMPT`）→ backward-compat。`flash=` / `system_instruction=` 呼叫不動 → 既有測試（只檢查 system_instruction 非空）全過。

---

## 3. Part B — Deep Research ReAct prompt 機制 `src/polaris/graph/deep_research/react.py`

新套件 `graph/deep_research/`（D15 的 `state.py` 也會放這）。

- `ReActTool(name, description, input_hint)` + `DEFAULT_TOOLS`（v0：`search` 檢索接地、`finish` 收尾）+ `render_tools(tools) -> str`。
- `build_react_prompt(question, react_steps, tools=DEFAULT_TOOLS) -> str`：user-content 組裝 —— 工具目錄 + scratchpad（逐輪 thought/action/observation）+ 問題 + 「請輸出下一個 Thought / Action」。
- `ReActAction(tool, tool_input, is_finish)` + `parse_react_action(text) -> ReActAction`：
  - 解析 `Action: <tool>` / `Action Input: <...>`；
  - `finish` → `is_finish=True`（收斂）；
  - **格式錯誤 / 解析不到 → 安全退 `finish`**（loop 必能優雅終止，不會卡死）。
- `REACT_SYSTEM_PROMPT` 由 registry import（不重複定義）。

> D13 只定 prompt + 協定 + parser（contract）；**真正的 ReAct loop（呼叫 LLM、執行工具、組 ReActStep、跑 should_continue）於 D15 以 TDD 實作**。

---

## 4. 測試（TDD，red-green-refactor）

`tests/test_prompts.py`：
- `NO_ADVICE_CLAUSE` 出現在 planner / writer / react 三個生成型 prompt（NFR-031 跨 prompt 不變量）。
- `GROUNDING_CLAUSE` 出現在 writer / react。
- 四個 prompt 皆非空；`planner_agent.SYSTEM_PROMPT` / `writer_agent.SYSTEM_PROMPT` / `compliance_agent.COMPLIANCE_SYSTEM_PROMPT` 仍可 import（backward-compat）。

`tests/test_deep_research_react.py`：
- `render_tools` 列出各工具名；`build_react_prompt` 含 question / 工具 / 先前 steps 的 scratchpad。
- `parse_react_action`：解析 search + input；finish；malformed → finish；大小寫/空白魯棒。

---

## 5. 不變量

- planner/writer/compliance 的 LLM 呼叫**行為不變**（只移 prompt 來源 + 精煉文字）。
- `workflow.py` / `state.py` / `compliance.py`（floor）不動。無新增依賴。
- 既有 249 測試保持綠。D15 消費 `react.py`。

---

## 6. Constitution

- **I（NFR-031）**：`NO_ADVICE_CLAUSE` 單一來源、跨生成型 prompt 強制（有測試背書）。
- **VI / III**：prompt 不改 LLM/金鑰路徑（仍走 `active_llm()` / google-genai）。

---

## 7. 交付物

程式 + 測試（TDD）· 本設計文件 · R2 spec D13 → `[x]`（repo + Drive mirror）· 專案記憶更新 · PR + admin-merge。
