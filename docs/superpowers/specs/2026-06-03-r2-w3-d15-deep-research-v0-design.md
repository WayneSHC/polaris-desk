# R2 W3 D15 — Deep Research v0（ReAct loop 跑通）設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：FR-004（Deep Research ReAct agent）、Deep Research v1 驗收（≤6 迴圈 / ≥3 引用 / 句句可溯源 / 0 買賣建議＝D16）、R2 spec §3 W3 D15
**前置**：D11（AQ-03＝自寫 ReAct loop + 狀態設計）、D13（`react.py` prompt/工具/parser + 中央 prompt registry）、D7 retry、D9 Compliance Agent
**編排決策**：用戶選**純 Python bounded loop**（v0 跑通優先；可後續包成 LangGraph node）

---

## 1. 目的

讓 Deep Research ReAct loop **端到端跑通**：reason → act → observe → should_continue ↺ / finalize。
smart(LLM) + 確定性 fallback 雙路徑（同 planner/writer/compliance 模式），CI token-free。
嚴格 ≤6/≥3/可溯源**驗收**是 D16；v0 已尊重 ≤6 上限並累積 evidence。

---

## 2. `graph/deep_research/state.py`（新）

- `ReActStep(BaseModel, frozen)`：`thought / action / action_input / observation`（str，預設 ""）。
- `dedup_evidence(existing, new) -> list[Citation]`：合併 + 依 `source_id` 去重、保序（evidence 累積器）。
- `should_continue(state, *, max_loops=6) -> bool`：`status=="answered"` 或 `iteration >= max_loops` → False（硬 ≤6 上限）；否則 True。
  - 註：D11 文件 signature 帶 `min_citations`，但其判斷屬「何時 finish」（agent 職責），非 loop 守門；故移到 `run_deep_research` 參數，`should_continue` 只管 status + 迴圈上限（純函式、好測）。
- `DeepResearchResult`（dataclass）：`question / final_answer / evidence / react_steps / iterations / status / compliance_status`。

---

## 3. `graph/deep_research/agent.py`（新）

- `stub_search(query) -> list[Citation]`：確定性、token-free；`source_id` 由 query 衍生（不同 query → 不同 evidence），`origin="stub"`。**可注入 seam** —— R4 真實 `VectorStore.search` 之後接這。
- `run_deep_research(question, *, client=None, search=stub_search, max_loops=6, min_citations=3) -> DeepResearchResult`：
  1. `state = {iteration:0, status:"running", react_steps:[], evidence:[]}`
  2. while `should_continue(state, max_loops=max_loops)`：
     - **decide**：
       - smart（有 client）：`build_react_prompt(question, steps, DEFAULT_TOOLS)` → `call_with_retry(client.generate(flash=True, system_instruction=REACT_SYSTEM_PROMPT))` → `parse_react_action`。**LLM 例外 → 退確定性 decide**（fail-to-deterministic）。
       - 確定性 fallback（無 client）：facet 政策 —— 以 `"{q} 營收/毛利率/風險"` 輪流 search，直到 `len(evidence) >= min_citations` 才 finish。
     - **act**：
       - `search` → `evidence = dedup_evidence(evidence, search(input or question))`；observation = 證據摘要；記 `ReActStep`。
       - `finish`（或未知工具，安全當 finish）→ `final_answer`（LLM 給的 tool_input，否則 `_synthesize`）、`status="answered"`、記 `ReActStep`。
     - `iteration += 1`
  3. **finalize**：迴圈用盡仍未 answered → `status="exhausted"`、`final_answer=_synthesize(..., exhausted=True)`（證據 < min 則誠實標「資料不足、結論暫定」）。
  4. **compliance**：`final_answer` 一律過 D9 `compliance_agent.review(final_answer, client)` → `(answer, compliance_status)`（NFR-031；中途 thought 不外洩）。
  5. 回 `DeepResearchResult`。
- `_synthesize(question, evidence, *, exhausted=False) -> str`：確定性、引用 source_id、**不含買賣建議**。

---

## 4. 消費 / 不變量

- 消費 D13 `react.py`、D7 `call_with_retry`、D9 `compliance_agent.review`。
- **不動** `workflow.py` / `state.py`(5 節點) / `compliance.py` → node_swap + 5 節點 trace 契約不變。無新增依賴。
- 全程無金鑰可跑（確定性 fallback + stub_search）→ CI token=0。

---

## 5. 測試（TDD，red-green-refactor）

`tests/test_deep_research_state.py`：
- `ReActStep` 欄位 / frozen。
- `dedup_evidence`：合併、依 source_id 去重、保序、空輸入。
- `should_continue`：running 且未達上限→True；answered→False；`iteration>=max`→False；剛好 = max 邊界。

`tests/test_deep_research_agent.py`：
- `stub_search`：回 Citation、確定性、不同 query → 不同 source_id。
- 確定性 run（無 client）：`status="answered"`、`evidence ≥ 3`、`iterations ≤ 6`、react_steps 有記錄、final_answer 非空、compliance `passed`；同輸入可重現。
- bounded：search stub 回 [] + `max_loops=3` → `iterations==3`、`status="exhausted"`、不崩。
- smart（FakeLLM `finish`）→ 1 迴圈走 LLM 結論（過 compliance）。
- smart scripted（search→search→finish）→ 多步、evidence 累積。
- **LLM 持續拋例外 → 退確定性、loop 仍完成**（不崩）。
- **NFR-031**：finish 的 tool_input 含買賣建議 → compliance blocked（answer=SAFE_MESSAGE、status=blocked）。
- 注入式 `search` seam 被使用。

---

## 6. Constitution

- **I（NFR-031）**：最終結論過 D9 Compliance；`_synthesize` 不產買賣建議。
- **VI / III**：Gemini 走 `active_llm()`/google-genai（Flash）；金鑰沿用既有路徑。
- **成本紀律**：無金鑰 → 確定性 fallback ReAct + stub_search，CI token=0。

---

## 7. 交付物

程式 + 測試（TDD）· 本設計文件 · R2 spec D15 → `[x]`（repo + Drive mirror）· 專案記憶更新 · PR + admin-merge。D16 接「過驗收」。
