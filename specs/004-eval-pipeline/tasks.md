# Tasks: Eval Pipeline（Ragas 評測管線）

**Input**: Design documents from `specs/004-eval-pipeline/`
**Prerequisites**: spec.md ✅, plan.md ✅（均於 2026-07-04 依 as-built 回補）
**Tests**: 含測試任務（repo 慣例全程 TDD；憲法 §IV 要求 smoke 路徑 0 token / 確定性）

> **回補說明**：本 feature 程式碼於 W1–W3 已交付並上 CI，本 tasks.md 為 **依 as-built 回填**，
> 已交付任務標 `[X]`。Phase 6（維護修正 #1–#5）於 2026-07-04（分支 `claude-eval-ragas`）完成；
> Phase 7 為尚未決策的延後項（`[ ]`）。任務編號為回補整理，非當初逐日順序。

## Phase 1: Setup

- [X] T001 `pyproject.toml` 新增 `[eval]`（`ragas>=0.2,<0.3` + datasets/pandas/langchain 相容棧）與 `[eval-gate]`（openai/anthropic）extras；核心不含 ragas，CI 恆裝的只有核心
- [X] T002 `src/polaris/eval/` package 骨架 + `errors.py`（`EvalConfigurationError` / `EvalExecutionError`）；`__init__.py` 公開 API re-export

## Phase 2: Foundational（阻塞所有 user story）

- [X] T003 [P] 測試先行：`tests/test_polaris_eval_dataset.py` — 130 題唯一、場景 4 gate 固定 10 題、中英欄頭別名、缺欄 raise、非法紅隊值 raise
- [X] T004 實作 `src/polaris/eval/dataset.py` — `EvalItem` frozen 契約 + `_ALIASES` 中英欄頭 + `load_dataset` / `validate_dataset`（FR-E-001）
- [X] T005 建題庫 `data/questions_v0.csv` → `questions_v1.csv`（W1 25 題 → W3 130 題）

## Phase 3: User Story 1 — 收齊 Ragas 四件套（P1）🎯 MVP

**Goal**: `run_item(item)` 回結構化 `EvalRecord`；場景 2 走 Deep Research；場景 3 圖表題經 visual_reader 升級（記 `escalated`）；records.jsonl 可重用。
**Independent Test**: 注入 FakeApp 跑一題 → `EvalRecord` 欄位齊全、contexts 正規化、stub 正確標記、jsonl 往返一致。

- [X] T006 [P] [US1] 測試先行：`tests/test_polaris_eval_runner.py` — `normalize_contexts`、注入 workflow 只 build 一次、stub 判定、records.jsonl 往返
- [X] T007 [US1] 實作 `src/polaris/eval/runner.py` — `run_item` / `run_dataset`（場景 2→Deep Research、其餘→workflow）、`EvalRecord`（含 `escalated` visual_reader 訊號、`citation_count`）、`write/read_records_jsonl`（FR-E-002）

**Checkpoint**: 注入式 e2e 可獨立驗收 — `pytest tests/test_polaris_eval_runner.py` 全綠。

## Phase 4: User Story 2 — smoke 達標率（P1）

**Goal**: `python -m polaris.eval` 跑全題庫印達標率 + 不及格清單；報告誠實標「煙測分、非 G3 真分」；紅線 → exit 1。
**Independent Test**: token=0 跑全題庫 → 印達標率、含 owner 的不及格清單、artifacts 落地；紅隊誘導題出現關鍵字 → exit 1。

- [X] T008 [P] [US2] 測試先行：`tests/test_polaris_eval_score.py`（smoke 部分）— 三型分類、`no_buysell`、空 contexts、達標率
- [X] T009 [US2] 實作 `src/polaris/eval/score.py::smoke_check` / `smoke_score` — 一般 / 紅隊 / 誠實邊界三型 deterministic 檢查（FR-E-003）
- [X] T010 [P] [US2] 實作 `src/polaris/eval/report.py` — summary.md / cases.csv / json / jsonl / manifest + 2 張手刻 SVG；含不及格清單 + owner（FR-E-006）；`SMOKE_WARNING`（NFR-E-002）；量 visual_reader 升級率
- [X] T011 [US2] 實作 `src/polaris/eval/__main__.py` CLI + `make eval-smoke` + CI `eval-smoke` job；紅線 exit code（FR-E-004）
- [X] T012 [US2] e2e：`tests/test_eval_pipeline.py` — runner→score→report→artifacts 全鏈；確定性重跑同分（NFR-E-001）

**Checkpoint**: `make eval-smoke` 綠、token=0、紅線守住 —— G1 階段可用的 MVP。

## Phase 5: User Story 3 — Ragas 真分 + 三方 Judge（P2，Phase 2）

**Goal**: 裝 `[eval]` + 金鑰後跑 CP≥0.85 / Faithfulness≥0.90 / AR≥0.85；`gate` 加三方 Judge 2/3 投票；未裝即回 None 絕不假分。
**Independent Test**: 注入 evaluator 回門檻值 → passed；回 NaN/None → FAIL；空 contexts 不送 judge；gate 三方 2/3 通過才 pass。

- [X] T013 [P] [US3] 測試先行：`tests/test_polaris_eval_score.py`（flash/gate 部分）— Ragas 門檻邊界、NaN→FAIL、空 contexts unscorable、gate 2/3 投票、runtime 上限預設
- [X] T014 [US3] 實作 `score.py::ragas_score` / `_evaluate_ragas` / `score_records` — CP/Faithfulness/AR 門檻；judge 預設 `gemini-3-flash-preview`（憲法 §VI）；`_env_positive_int` 執行上限
- [X] T015 [US3] 實作 `judges.py` + `tests/test_polaris_eval_judges.py` — 三方共用 JSON 契約、fail-closed、`majority_passed`；CI `eval-flash` / `eval-gate` job（FR-E-005 token 紀律）

**Checkpoint**: `eval-flash`（有金鑰）/ `eval-gate` 綠；未裝 extra 誠實回 None。

## Phase 6: 維護修正（2026-07-04 code review findings #1–#5）

**Goal**: 修正影響 G3/G4 真分正確性的評分缺陷，並補齊當初缺的 flash/gate 紅隊+誠實邊界測試覆蓋。

- [X] T016 [P] 測試先行（紅）：`test_polaris_eval_score.py` 加紅隊/誠實邊界在 flash/gate 下的案例；`test_polaris_eval_runner.py` 加真跑空 contexts→`is_smoke_test=False`、`from_dict` schema 容錯；`test_polaris_eval_dataset.py` 加空紅隊值→raise
- [X] T017 修 #1（🔴）：`score.py` 抽 `_item_kind`（smoke 與 score_records 共用單一分類），flash/gate 對紅隊/誠實邊界**不套** RAGAS 門檻與 `unscorable_empty_contexts`（新增 FR-E-007）
- [X] T018 修 #2（🔴）：`runner.py::_record_from_result` `is_smoke_test = is_stub`（移除 `or not contexts`）
- [X] T019 修 #3（🟡）+ #4（🟡）：`dataset.py::_FALSE_VALUES` 移除 `""`（空紅隊值 raise）；`runner.py::EvalRecord.from_dict` 過濾未知欄位、缺欄補預設（相容 `escalated`/`citation_count`）
- [X] T020 修 #5（⚪）：`pyproject.toml [eval]` 移除未 import 的 `matplotlib`；保留 `datasets`（ragas 0.2.x runtime）與 `pandas`（`.to_pandas()`）
- [X] T021 加 `Questions_v2.csv`：對齊 0050 前 20 家 + Ontology V1，補回 9 誠實邊界 + 10 誘導型紅隊；過 `load_dataset` 契約（130/10）
- [X] T022 回歸：`pytest` eval 全綠（25 題）、`make eval-smoke` 綠且 stub run 仍正確顯示 smoke 警告

**Checkpoint**: 紅隊/誠實邊界題在 flash/gate 不再被 `unscorable_empty_contexts` 誤殺；真分報告不再誤掛「非真分」。

## Phase 7: 延後 / 待決策（NOT done）

- [ ] T-DEFER-1 `Questions_v2.csv` 切為 CLI 預設題庫：`__main__.py::DEFAULT_DATASET` 現仍指向 `questions_v1.csv`。切換需先在 R4 真 BigQuery 環境跑一次 gate 驗證 v2 語料覆蓋（20 家 × 2025Q1/Q2 ≥80%），並更新 `test_polaris_eval_dataset.py` 的 `DATASET` 常數。**需 R5/R4 確認後再切**。

## Dependencies & Execution Order

- **Phase 1 → 2 → 3**：Setup → dataset 契約/題庫 → runner（MVP 前置）。
- **US2（Phase 4）依賴 US1 的 runner/EvalRecord**；US1+US2 = G1 可用最小整體。
- **US3（Phase 5）依賴 US1+US2**；`[eval]` extra 才啟用。
- **Phase 6 維護修正**依賴 US2/US3 已就位（修的正是 score/runner/dataset）。
- 標 [P] 的任務檔案不相交、可並行。

```text
Setup(T001-002) → Foundational(T003-005) → US1(T006-007) → US2(T008-012) → US3(T013-015)
                                                                              └─→ 維護(T016-022) → 延後(T-DEFER)
```

## Implementation Strategy

- **MVP = US1 + US2**（收齊 record + smoke 達標率 + 紅線；G1 階段用 stub 語料，報告誠實標「煙測分」）。
- **Phase 2 = US3**（真分）：`[eval]` 環境 + 金鑰才跑；CI 依 token 紀律拆 smoke / flash / gate 三 job。
- 維護修正走 TDD：先寫會紅的測試（T016）再轉綠（T017–T021）。
