# Research: LangGraph 5-Node Skeleton (Stub Mode)

> 解決 plan.md 中提到的 4 個技術選擇。沒有 NEEDS CLARIFICATION 殘留。

## 1. 節點實作擺哪：搬到 `nodes/stubs.py` 模組

**Decision**：把 5 個節點函式從既有 `workflow.py` 搬到 `src/polaris/graph/nodes/stubs.py`，`workflow.py` 只保留 `build_workflow()` 的 wiring（`add_node` + `add_edge`）與 `PolarisState`/import 別名。

**Rationale**：
- 直接對應 **FR-007 / SC-005**「工作流結構與節點實作分離 → 換節點 diff = 0 行」。
- R3 在 W1 D2+ 把 Planner / Calculator / Writer 真 agent 推進來時，只動 `nodes/` 底下檔案；wiring 不動。
- `workflow.py` 變短，wiring 邏輯一目了然，閘門 review 容易。

**Alternatives considered**：
- *inline 函式（既有狀態）*：W1 D1 跑得起來，但 D2 R3 一動就會跟 wiring 撞 diff，FR-007 顯然不過。Rejected。
- *每個節點獨立檔（`planner.py`、`retriever.py`...）*：未來會走到這一步，但 W1 D1 5 顆都還是 stub，拆 5 檔太細，rename 成本高。先放同一檔 `stubs.py`，等真 agent 換進來時再依角色拆。Deferred to W1 D2+。

## 2. NodeTrace 怎麼收集：裝飾器自動 capture

**Decision**：在 `src/polaris/graph/nodes/trace.py` 寫一個 `@traced("planner")` 裝飾器，包住節點函式，自動：
- 紀錄進入時的 `state.keys()` → `input_keys`
- 跑完後算 diff → `output_keys`
- 計時 → `elapsed_ms`
- 抓例外 → `status="error"` + `error_message`
- 回傳的 state patch 中加一筆 `trace=[NodeTrace(...)]`，LangGraph 用 `Annotated[list, add]` reducer 自動串聯

**Rationale**：
- 直接對應 **FR-006**「每個節點都要有 node_name / input_keys / output_keys / status」。
- 裝飾器集中處理 = 每顆節點程式碼純粹只寫業務邏輯，不必重複寫 trace boilerplate。
- 換真 agent 進來時只要繼續用 `@traced("planner")` 包，trace 結構不會破。

**Alternatives considered**：
- *LangGraph 內建 callbacks*：可以收事件但結構比較鬆，要再 mapping 成 NodeTrace 物件。**Stretch goal**：等 W2 retry 進來時再評估是否切換。Rejected for D1。
- *節點手動 append 到 trace*：簡單但容易漏記、每顆都要重寫。Rejected。

## 3. 節點例外：裝飾器層 try/except + conditional edge 跳 END

**Decision**：
- 同一個 `@traced` 裝飾器接 `try/except Exception`，捕到例外時：
  - 寫一筆 `NodeTrace(status="error", error_message=str(e))` 入 trace
  - 回傳 state patch `{"halt": True, "compliance_status": "unknown"}`
- `build_workflow()` 在每顆節點後加 conditional edge：`should_continue(state)` 看 `state.get("halt")`，True 直接跳到 END、回固定錯誤訊息（透過一個 `terminal` 節點或 lambda）。

**Rationale**：
- 直接對應 **FR-009**「節點例外時，trace 寫入、安全中止、下游不吃 undefined 狀態」+ Edge case 4。
- 集中在裝飾器 + 一條 conditional edge，邏輯一處可看。
- W1 D1 不做 retry — 直接 halt 是最簡單也最安全的版本；W2 D7 R2 才會在這層補 retry。

**Alternatives considered**：
- *讓例外往上拋讓 LangGraph 自己處理*：LangGraph 0.6 預設會 propagate，使用者拿到 unstructured stack trace；不符合「安全中止」精神，也吃不到 trace。Rejected。
- *try/except 包在 build_workflow() 外層*：拿不到「是哪顆節點掛掉」，FR-009 過不了。Rejected。

## 4. Compliance 策略：6 關鍵字 substring 黑名單 + 攔截後回固定安全訊息

**Decision**：
- `src/polaris/graph/compliance.py` 純函式：`apply_compliance(draft: str) -> tuple[str, Literal["passed","blocked"]]`。
- 黑名單關鍵字（W1 用最小集，符合 spec FR-005）：`["建議買進", "建議賣出", "加碼", "減碼", "看多", "看空"]`。
- 命中任一個 → 回 `("本系統不提供買賣建議，僅描述事實與引用來源。", "blocked")`。
- 未命中 → 回 `(draft, "passed")`。
- 不做自動改寫（不嘗試 LLM rewrite，避免 W1 引入 LLM 成本與 prompt risk）。

**Rationale**：
- 直接對應 **FR-005** + **SC-003**「6 條已知關鍵字攔截率 = 100%、最終 answer 含買賣建議的測試案例數 = 0」。
- 純函式 / 字串輸入字串輸出 → 單元測試最容易。R6 W3 補完整集時只動關鍵字清單 + 可選 regex。
- 「攔截後回安全訊息」比「嘗試改寫」風險低非常多——投顧執照風險不容半改半留。

**Alternatives considered**：
- *regex 模糊比對（如「建議.{0,3}買進」）*：W1 D1 不需要，R6 W3 收完整關鍵字集再補。Deferred。
- *Compliance 用 LLM 判斷*：成本高、非確定性（破 SC-006）、可被 prompt injection 繞過。Rejected。
- *只改寫不攔截*：對 NFR-031 風險過高（萬一改寫沒改乾淨）。Rejected。

---

## 結論

四個決策都倒向「最少程式碼 + 確定性 + 跟 spec 1:1 對齊」。所有 NEEDS CLARIFICATION = 0。可進 Phase 1。
