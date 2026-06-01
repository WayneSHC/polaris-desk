---
description: "Task list for LangGraph 5-Node Skeleton (Stub Mode) — R2 W1 D1"
---

# Tasks: LangGraph 5-Node Skeleton (Stub Mode)

**Input**: Design documents from `specs/001-langgraph-skeleton/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/workflow-invoke.md ✅, quickstart.md ✅

**Tests**: Included (TDD-style — write failing tests first). Spec SC-006 requires deterministic snapshot tests; R5 will later extend.

**Organization**: Tasks grouped by user story (US1 / US2 / US3) for independent implementation and verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (Setup / Foundational / Polish have no story label)

## Path Conventions

- Single project: `src/polaris/`, `tests/` at repository root（per plan.md Structure Decision Option 1）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認 starter 環境可用、能 import 既有套件。

- [ ] T001 Verify dev environment：在 repo 根跑 `pip install -e ".[dev]"` 並驗證 `python -c "import polaris, langgraph, pydantic"` 全部成功；建空檔 `tests/conftest.py`（若不存在）讓 pytest fixture 共用

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立全 3 個 user story 共用的型別與 trace 基礎設施。沒有這層，US1/US2/US3 都無法開工。

**⚠️ CRITICAL**: T002–T005 必須先全部綠燈再開 user story 任務。

- [ ] T002 [P] Create `src/polaris/graph/state.py`：依 data-model.md 實作 `Citation`、`NodeTrace`（pydantic BaseModel）與 `ResearchState`（TypedDict，含 `Annotated[list[NodeTrace], operator.add]` reducer 與 `halt: bool`、`compliance_status` 欄位）
- [ ] T003 [P] Create `src/polaris/graph/nodes/__init__.py`（空）與 `src/polaris/graph/nodes/trace.py`：實作 `@traced(node_name: str)` 裝飾器，包住節點函式，自動 emit `NodeTrace`（含 status / input_keys / output_keys / elapsed_ms），try/except 內捕例外時設 `state["halt"]=True`、回 `NodeTrace(status="error", error_message=...)`
- [ ] T004 [P] Write `tests/test_state.py`：(a) `Citation` 必填欄位驗證 + `origin` enum 驗證；(b) `NodeTrace` 各 status 與 error_message 互斥規則；(c) `ResearchState` keys 與型別 spot-check
- [ ] T005 [P] Write `tests/test_trace_decorator.py`：(a) 包住正常函式 → trace status=ok、input/output keys 正確；(b) 包住會 raise 的函式 → trace status=error、error_message 含 exception 字串、halt=True；(c) 重複呼叫同一函式 → trace list 累加而非覆蓋

**Checkpoint**: Foundation 通過 → US1 / US2 / US3 可開工（在 7 人團隊中可分頭做）。

---

## Phase 3: User Story 1 — 隊友可送問題、拿到帶引用的假答案 (Priority: P1) 🎯 MVP

**Goal**: `app.invoke({"query": "..."})` 端到端跑通 5 節點，回 `{answer, citations, trace[5], compliance_status="passed"}`，3 次重跑結果相同。

**Independent Test**: `pytest tests/test_workflow_e2e.py::test_e2e_happy_path tests/test_workflow_e2e.py::test_e2e_determinism tests/test_workflow_e2e.py::test_e2e_runtime_under_10s tests/test_workflow_edges.py -v` 全綠。

### Tests for User Story 1（先寫，預期 FAIL）⚠️

- [ ] T006 [P] [US1] Write `tests/test_workflow_e2e.py::test_e2e_happy_path`：對「台積電 2025 Q1 營收 YoY」呼叫 `app.invoke()`，斷言 (a) `answer` 為非空 str、(b) `citations` len ≥ 1 且每筆有 source_id/snippet/origin、(c) `compliance_status="passed"`、(d) `trace` 長度 = 5 且 5 個 node_name 齊全、status 全 ok（SC-001、SC-002）
- [ ] T007 [P] [US1] Write `tests/test_workflow_e2e.py::test_e2e_determinism`：同一 query 連跑 3 次，比較 3 個 result dict，**排除每筆 trace 的 `elapsed_ms`** 後其餘 byte-identical（SC-006）
- [ ] T008 [P] [US1] Write `tests/test_workflow_e2e.py::test_e2e_runtime_under_10s`：跑一次 happy path 計時 < 10 秒（用 `time.perf_counter()`）（SC-004）
- [ ] T009 [P] [US1] Write `tests/test_workflow_edges.py::test_empty_query_halts`：`app.invoke({"query": ""})` 與 `app.invoke({"query": "   "})` → 斷言 `halt=True`、`answer="請提供具體問題。"`、`trace` 只有 1 筆 planner status=error（SC-007、FR-008）
- [ ] T010 [P] [US1] Write `tests/test_workflow_edges.py::test_node_exception_halts_downstream`：用 monkeypatch 把 `nodes.stubs.retriever` 換成會 `raise RuntimeError("boom")` 的版本 → 斷言 (a) `app.invoke()` 不拋例外、(b) `halt=True`、(c) `trace` 只含 planner ok + retriever error **共 2 筆**（halt 後條件邊直接跳 terminal，下游 calculator/writer/compliance **不出現在 trace**，對齊 SC-007 精神）（FR-009）

### Implementation for User Story 1

- [ ] T011 [US1] Create `src/polaris/graph/nodes/stubs.py`：實作 5 個確定性 stub 函式（`planner` / `retriever` / `calculator` / `writer` / `compliance`），每個都用 `@traced("xxx")` 裝飾；planner 在 query 為空時 raise 觸發 halt；writer 預設回合規假草稿（含 ≥ 1 條 `Citation(origin="stub")`）；compliance 暫時直接 passthrough（US2 才接 `apply_compliance()`）
- [ ] T012 [US1] Refactor `src/polaris/graph/workflow.py`：(a) 從 `polaris.graph.nodes.stubs` import 5 個節點函式；(b) 既有 `add_node`/`add_edge` wiring 保留不動；(c) 加 `should_continue(state)` 條件函式 + 一個 `terminal` 節點（回固定 halt 訊息），讓任一節點 halt=True 後直接跳 END；(d) 既有 `__main__` block 與 starter `{"query": "..."}` 呼叫慣例不破
- [ ] T013 [US1] Create `src/polaris/cli.py`：用 stdlib `argparse` 寫 `python -m polaris.cli ask "<query>"`，輸出 query/answer/citations/compliance/trace 表格（依 quickstart.md §3 範例格式）；保留 `--stub-buysell` flag（US2 會用到，本任務只先讓 flag 存在但不接行為）；同時加 `src/polaris/__main__.py` 讓 `python -m polaris ...` 也能跑 CLI
- [ ] T014 [US1] Run T006–T010 全 5 個測試直到綠燈；任何 fail 就回去修對應節點/wiring，不修測試（測試是 SC 的執行版）

**Checkpoint**: US1 完成 = MVP 達成（spec G1 閘門對應交付物 1「5 節點端到端跑通」即達標）。可獨立 demo / PR。

---

## Phase 4: User Story 2 — Compliance 攔下任何疑似買賣建議的草稿 (Priority: P1)

**Goal**: Writer 草稿含「建議買進/賣出/加碼/減碼/看多/看空」任一關鍵字時，最終 `answer` 必為固定安全訊息、`compliance_status="blocked"`，且 6 條測試輸入 100% 攔截。

**Independent Test**: `pytest tests/test_compliance.py tests/test_workflow_e2e.py::test_e2e_compliance_blocks_buy_sell -v` 全綠。

### Tests for User Story 2（先寫，預期 FAIL）⚠️

- [ ] T015 [P] [US2] Write `tests/test_compliance.py`：對 6 條關鍵字各構造一個含該字眼的 draft，斷言 `apply_compliance(draft)` 回 `("本系統不提供買賣建議，僅描述事實與引用來源。", "blocked")`；對 3 條合規 draft（純事實描述）斷言回 `(draft, "passed")` 原封不動；SC-003 = 100% 攔截率
- [ ] T016 [P] [US2] Write `tests/test_workflow_e2e.py::test_e2e_compliance_blocks_buy_sell`：用 CLI flag `--stub-buysell`（或 monkeypatch writer stub）讓 writer 回「建議買進台積電」，跑 e2e 後斷言 (a) `compliance_status="blocked"`、(b) `answer` 中**不含** 6 關鍵字任一、(c) `trace` 仍 5 筆 status=ok（compliance 節點被執行了，只是回攔截結果，非 error）

### Implementation for User Story 2

- [ ] T017 [US2] Create `src/polaris/graph/compliance.py`：純函式 `apply_compliance(draft: str) -> tuple[str, Literal["passed","blocked"]]`，常數 `BUYSELL_KEYWORDS = ("建議買進","建議賣出","加碼","減碼","看多","看空")`，命中任一 substring → 回固定安全訊息；無 import LangGraph / pydantic，純字串處理便於單元測試
- [ ] T018 [US2] Update `src/polaris/graph/nodes/stubs.py` 的 `compliance` 節點：從 `polaris.graph.compliance` import `apply_compliance`，呼叫 `(final, status) = apply_compliance(state["draft"])`，set `state["answer"]=final`、`state["compliance_status"]=status`
- [ ] T019 [US2] Update `src/polaris/cli.py`：把 `--stub-buysell` flag 實際接上（透過環境變數或 ctx 旗標讓 writer stub 切換 draft 內容）；更新 README/quickstart 範例輸出
- [ ] T020 [US2] Run T015–T016 直到綠燈；額外跑一次完整 `pytest -v` 確認 US1 測試沒被打破

**Checkpoint**: US2 完成 = 憲法 Principle I（NFR-031）的最小可演示版本上線。

---

## Phase 5: User Story 3 — 任一節點可獨立替換而不動 workflow 定義 (Priority: P2)

**Goal**: 把 5 個節點之一的 stub 換成行為不同的版本，**`workflow.py` diff = 0 行**，最終輸出反映新節點行為。

**Independent Test**: `pytest tests/test_node_swap.py -v` 全綠。

### Tests for User Story 3（先寫，預期 FAIL）⚠️

- [ ] T021 [P] [US3] Write `tests/test_node_swap.py::test_swap_planner_stub_no_workflow_diff`：(a) 用 monkeypatch 把 `polaris.graph.nodes.stubs.planner` 換成回 `["v2 step A","v2 step B"]` 的版本；(b) 跑 `app.invoke()` 斷言 `result["plan"] == ["v2 step A","v2 step B"]`、`result["trace"][0].node_name=="planner"`；(c) 額外用 `pathlib.Path("src/polaris/graph/workflow.py").read_text()` 在測試前後 hash 比對，確認檔案內容未變

### Implementation for User Story 3

- [ ] T022 [US3] Run T021 直到綠燈。**正常情況不需要新 code**——US1 的 T011/T012 已把 wiring 與節點實作分離；若 T021 fail，必須回頭調整 T012 的 import 結構讓 monkeypatch 生效，**不可**靠改 `workflow.py` 來通過

**Checkpoint**: US3 完成 = SC-005 達標。R3 在 W1 D2+ 推真 agent 進來時的契約已驗證。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 收尾，讓骨架交付物可被隊友直接 onboard。

- [ ] T023 [P] Update `README.md`：在 §6（規格文件）新增一段「W1 D1 已交付：001 LangGraph 骨架（stub mode）→ 跑法見 specs/001-langgraph-skeleton/quickstart.md」
- [ ] T024 [P] Run `ruff check src tests` 與 `mypy src/polaris/graph src/polaris/cli.py` 並修掉新檔的 error/warning（既有檔的歷史問題不在本 PR 處理）
- [ ] T025 跟 quickstart.md 一步步走一次，確認指令真的能跑、輸出格式對得起來；若有 drift 就更新 quickstart.md 而非埋忽略
- [ ] T026 跑 `/speckit-analyze`（spec-kit 內建）做 spec/plan/tasks 跨產物一致性檢查；任何 finding 解掉或登 follow-up issue

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：T001，無外部依賴，可即時開始
- **Foundational (Phase 2)**：T002–T005，全部依賴 T001 完成；BLOCKS 所有 user story
- **US1 (Phase 3)**：T006–T014，依賴 Phase 2 全綠
- **US2 (Phase 4)**：T015–T020，依賴 Phase 2 全綠（與 US1 平行；T018 改 `stubs.py`，與 T011 同檔，建議 US1 先合 main 再做 US2 以避免衝突）
- **US3 (Phase 5)**：T021–T022，依賴 US1 T011+T012 完成（必須先有 `stubs.py` + 重構過的 `workflow.py`）
- **Polish (Phase 6)**：T023–T026，依賴 3 個 user story 全綠

### Within Each Story

- 先寫測試（T006–T010 / T015–T016 / T021）→ 跑一次確認 FAIL → 寫實作 → 再跑直到 PASS
- 同 story 內 `[P]` 標記的測試任務可平行寫
- 實作任務若改同一檔（如 T011 與 T018 都改 `stubs.py`），必須序列化

### Parallel Opportunities

- Phase 2 所有 `[P]` 任務（T002, T003, T004, T005）可 4 條並行
- Phase 3 測試（T006–T010）可 5 條並行寫
- Phase 4 測試（T015, T016）可 2 條並行寫
- US1 與 US2 在 Phase 2 完成後可由不同人並行（注意 stubs.py 同檔衝突 → 建議 US1 先 merge）
- Polish 中 T023 與 T024 可並行

---

## Parallel Example: User Story 1（TDD batch）

```bash
# 一次寫齊 US1 所有測試（5 個測試函式，分散在 2 個檔，平行寫）：
Task: "Write tests/test_workflow_e2e.py::test_e2e_happy_path"
Task: "Write tests/test_workflow_e2e.py::test_e2e_determinism"
Task: "Write tests/test_workflow_e2e.py::test_e2e_runtime_under_10s"
Task: "Write tests/test_workflow_edges.py::test_empty_query_halts"
Task: "Write tests/test_workflow_edges.py::test_node_exception_halts_downstream"

# 一次跑全部，看 5 個都 FAIL（紅燈）→ 進實作

# 實作 stubs + workflow refactor + cli 必須序列化（同檔/有依賴）：
T011 → T012 → T013 → T014（rerun until green）
```

---

## Implementation Strategy

### MVP First（建議今天 W1 D1 跑到這）

1. **Phase 1**：T001（15 分鐘）
2. **Phase 2**：T002–T005（1.5 小時，含 trace 裝飾器要小心 LangGraph reducer）
3. **Phase 3 (US1)**：T006–T014（2–3 小時）
4. **STOP & VALIDATE**：跑 quickstart.md §3 範例，看 CLI 印出 5 節點 trace 與假答案

→ **此時 G1 閘門的核心交付物已達標**，可以 commit + push + 開 PR；US2 / US3 留到明天。

### Incremental Delivery

1. Setup + Foundational + US1 → 第 1 個 PR（MVP）
2. US2（compliance 攔截）→ 第 2 個 PR
3. US3（節點替換驗證）+ Polish → 第 3 個 PR
4. 每個 PR 獨立可 review、可 deploy

### Parallel Team Strategy（W1 D2 之後）

- 你（R2）：US1 / US3（骨架與替換契約）
- R6 金融品質：US2（compliance 邏輯與關鍵字審）
- R3 Agent：W1 D2+ 起在 US1 完成的 `stubs.py` 上一顆顆換真 agent
- R5 Eval：用 US1 確定性 e2e 寫第一個 snapshot 測試

---

## Notes

- `[P]` 標記只在不同檔且無前置依賴時加
- `[Story]` 標記讓 PR 標題可以直接引用（例：`feat(US1): end-to-end happy path`）
- 每個 story 各自完整可獨立測試 — 不要在 US1 任務裡偷做 US2
- Verify tests fail before implementing — 否則測試本身可能寫錯
- Commit 粒度 = 一個 task 或一組緊密相關 task；commit message 帶 `[T0xx]` 標記
- Stop at any checkpoint to validate 該 story 獨立可運作
- Avoid：vague tasks、同檔衝突、cross-story dependencies that break independence
