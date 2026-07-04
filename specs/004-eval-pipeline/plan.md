# Implementation Plan: Eval Pipeline（Ragas 評測管線）

**Branch**: `r5/004-eval-pipeline`（本次修正分支 `claude-eval-ragas`，PR 進 `codex/sync-r5-eval-pipeline`）| **Date**: 2026-07-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-eval-pipeline/spec.md` + `docs/R5_eval_開工指南.md` + 憲法 §IV（Eval 即品質門檻）

> **回補說明**：本 feature 程式碼於 W1–W3 已實作並上 CI，但 SDD 的 plan/tasks 當初跳過。
> 本檔為 **2026-07-04 依 as-built 回補**，並記錄一輪 code review 的修正（findings #1–#5）。
> 場景 3 圖表題**已由 ColPali dispatch 改為 workflow 內 visual_reader 升級節點**（team 決定，
> eval 端只量 `escalated` 升級率）——本檔描述現狀。

## Summary

題庫 CSV →（`dataset.py` 契約驗證，中/英欄頭皆可）→ 每題跑 workflow（場景 2 走 Deep Research，其餘走 5 節點文字 workflow；場景 3 圖表題由 workflow 內 visual_reader 節點在檢索到視覺證據時升級，eval 以 citation `origin=='vision'` 記 `escalated`）→ 產出可重用的 `EvalRecord`（answer / contexts / ground_truth / citations / compliance_status / citation_count / escalated / stub 判定）→ 三段評分：

- **smoke**（CI 預設、token=0）：deterministic schema / 引用 / NFR-031 檢查，分「一般 / 紅隊 / 誠實邊界」三型（`_item_kind`）。
- **flash**（`[eval]` extra + 金鑰）：加 Ragas CP≥0.85 / Faithfulness≥0.90 / AR≥0.85（judge 預設 `gemini-3-flash-preview`）。
- **gate**（G2/G3/G4 閘門）：全 130 題 Ragas + Claude/GPT/Gemini 三方 Judge 2/3 投票 + 場景 4 固定 10 題子集。

報告輸出 Markdown / CSV / JSON / records.jsonl / manifest + 兩張手刻 SVG，並**誠實標註「煙測分 vs 真分」**、量 visual_reader 升級率。runner 與 score 分離，`--reuse-records` 可不重跑檢索/回答只重評分。

## Technical Context

**Language/Version**: Python 3.13（`.python-version` 已鎖；pyproject `requires-python>=3.13`）

**Primary Dependencies**:
- 核心（無 extra、CI 恆裝）：`pydantic`（`EvalItem` frozen 契約）、stdlib（csv / json / SVG 手刻）
- `[eval]` extra（flash/gate 才裝）：**`ragas>=0.2,<0.3`**（刻意固定 <0.3：RAGAS 0.4 移除 langchain_community Vertex AI adapter，本評測用 0.2 single-turn API，見 pyproject 註解）、`datasets`、`pandas`（取回 ragas 結果的 `.to_pandas()`）、`langchain-community<0.4`、`langchain-google-genai<3.0`
- `[eval-gate]` extra：`openai`、`anthropic`（三方 Judge 的 GPT / Claude 端）
- 既有內部模組：`graph/workflow`、`graph/deep_research`、`graph/compliance.BUYSELL_KEYWORDS`、`config.settings`

**Storage**: 無 DB 寫入；報告 artifacts 落地 `eval_reports/`（records.jsonl 可 `--reuse-records` 重評）

**Testing**: `pytest>=8.2`；smoke 路徑全程 token=0、確定性；RAGAS/Judge 以注入式 evaluator / monkeypatch 測試，CI 不需真金鑰

**Target Platform**: 本機開發 + GitHub Actions CI（eval-smoke / eval-flash / eval-gate 三 job）

**Project Type**: Single Python package（`src/polaris/eval/`）+ `python -m polaris.eval` CLI

**Performance Goals**: 憲法 §IV 硬門檻 — CP≥0.85 / Faithfulness≥0.90 / AR≥0.85 / 130 題達標率 ≥80%（G3/G4 No-Go 條件）

**Constraints**:
- **Token 紀律**（憲法 §IV）：CI 平常只跑 smoke（0 token）與 flash（Gemini 3 Flash）；三方 Judge 只在 gate。
- **確定性**：同題庫兩跑同分（NFR-E-001）；報告必標「煙測分 vs 真分」（NFR-E-002）。
- **絕不假分**（憲法 §II）：未裝 `[eval]` 或空 contexts 一律回 `None`。
- **紅線 exit code**（憲法 §I）：任一題出現買賣建議關鍵字 → CLI 回 1。
- **eval 執行上限**：`score.py::_env_positive_int` 讀 env 上限，避免 eval 啟動脆弱（observability）。

**Scale/Scope**: 130 題 × 4 場景（財務基本 / 同業比較 Deep Research / 圖表 visual_reader / 跨產業拆解）+ 紅隊 + 誠實邊界；場景 4 固定 10 題 gate 子集。`Questions_v2.csv` 對齊 0050 前 20 家公司。

## Constitution Check

> 對 `.specify/memory/constitution.md`（v2.0.0）6 原則逐一檢視。本 feature 正是原則 IV 的載體。

| Principle | 本 feature 如何遵循 | 證據 |
|---|---|---|
| **I. NFR-031（買賣建議攔截）** | 每題 smoke 跑 `no_buysell`（比對 `BUYSELL_KEYWORDS`）；紅隊題只看 0 關鍵字；命中 → CLI exit 1、報告列 `buysell_violations`（目標 0） | FR-E-003/004；`score.py::smoke_check`、`report.py::redteam` |
| **II. 引用接地** | 一般題必檢 `has_citations` + `contexts_nonempty` + `compliance_passed`；誠實邊界題正解「資料不足」、不得偽造引用；空 contexts 一律 Ragas 回 `None` 絕不假分 | FR-E-003；`score.py::ragas_score` |
| **III. 雲端協作優先 · 金鑰安全** | 檢索走 `VECTOR_BACKEND=bigquery`；金鑰只讀 env，未設定即誠實 skip 並在 CI summary 標明 | `ci.yml` eval-flash key guard |
| **IV. Eval 即品質門檻** | **本 feature 即此原則的實作**：Ragas 自動化 + 三方 Judge 投票；硬門檻 CP/Faithfulness/AR/達標率；token 紀律（smoke=0、flash 便宜、gate 才三方） | `score.py::RAGAS_THRESHOLDS`、`G3_PASS_RATE` |
| **V. Demo 可重現 + 離線備援** | smoke 全離線 token=0；`--reuse-records` 讓評分可離線重跑；stub 語料讓管線在無語料時仍可 e2e | NFR-E-001；`runner.py::read_records_jsonl` |
| **VI. 最新技術棧** | Ragas judge 走新版 `google-genai` 系（`langchain-google-genai` + `gemini-3-flash-preview`）；ragas 固定 0.2.x 相容 API；**非**舊版 `google-generativeai` | 憲法 VI；`score.py::_evaluate_ragas` |

**Gate result**: ✅ ALL PASS — 0 violations，Complexity Tracking 免填。

## Project Structure

### Documentation (this feature)

```text
specs/004-eval-pipeline/
├── spec.md                 # ✅ /speckit-specify 產出（2026-07-04 校正 Phase 2 現況 + FR-E-007）
├── plan.md                 # ✅ 本檔（2026-07-04 依 as-built 回補）
└── tasks.md                # ✅ 依 as-built 回補（任務標 [X] 反映實際已交付）
```

### Source Code (repository root)

```text
src/polaris/eval/
├── __init__.py             # 公開 API re-export
├── __main__.py             # python -m polaris.eval CLI（--mode smoke/flash/gate、--reuse-records）
├── dataset.py              # EvalItem frozen 契約 + load_dataset/validate_dataset（中英欄頭別名、130/10 gate 驗證）
├── runner.py               # run_item/run_dataset → EvalRecord（含 escalated=visual_reader 訊號）；normalize_contexts；records.jsonl 讀寫
├── score.py                # smoke_check / ragas_score / score_records；RAGAS_THRESHOLDS；_item_kind 三型分類；_env_positive_int
├── judges.py               # 三方 Judge（gemini/openai/anthropic）2/3 投票，fail-closed
├── report.py               # build_summary / write_eval_artifacts / render_markdown + 手刻 SVG；量 visual_reader 升級率
├── errors.py               # EvalConfigurationError / EvalExecutionError
└── data/
    ├── questions_v0.csv     # 早期草稿題庫
    ├── questions_v1.csv     # 現 CLI 預設（DEFAULT_DATASET）；⚠️ 無誠實邊界題
    └── Questions_v2.csv     # 🆕 對齊 0050 前 20 家 + Ontology V1（含 9 誠實邊界 + 10 誘導型紅隊）；尚未切為預設

tests/
├── test_polaris_eval_dataset.py   # 契約 / 別名 / 130 題 / 非法+空紅隊值 raise
├── test_polaris_eval_runner.py    # EvalRecord、normalize、stub 判定、is_smoke_test、from_dict 容錯
├── test_polaris_eval_score.py     # smoke/flash/gate 評分、Ragas 門檻、紅隊+誠實邊界不被誤殺
├── test_polaris_eval_judges.py    # 三方 Judge 解析 / fail-closed / 2/3 投票
└── test_eval_pipeline.py          # e2e：runner→score→report→artifacts

.github/workflows/ci.yml    # eval-smoke（token-free）/ eval-flash（有金鑰）/ eval-gate
pyproject.toml              # [eval] / [eval-gate] extras（ragas>=0.2,<0.3）
```

**Structure Decision**:
- Single package `src/polaris/eval/`，**runner（跑）與 score（評）刻意分離**：records.jsonl 為中繼，`--reuse-records` 可只重評分不重燒 token。
- 檢索是注入式 seam（Deep Research runner 可注入、app 可注入），對齊「換節點不動 wiring」；R4 換真檢索 runner 零改動（FR-E-002）。
- 場景 3 圖表題由 workflow 內 **visual_reader** 節點處理（origin=='vision' 升級），eval 只以 `escalated` 量升級率——ColPali dispatch 已 retire。
- 圖表用 stdlib 手刻 SVG（`report.py::_write_bar_chart`），故 token-free smoke 也有圖 artifact，不必為畫圖裝 matplotlib。

## Complexity Tracking

> Constitution Check 全部 PASS，無需 justification。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Phase 0 / 1 / 2（as-built 決策摘要）

1. **runner / score 分離 + records.jsonl 中繼**：評分要能離線重跑、不重燒 token（憲法 §IV/§V）。
2. **空 contexts 的語意**：Ragas 對空 contexts 回 `None`（不送 judge、不假分，憲法 §II）；一般題空 contexts 判 `unscorable_empty_contexts` FAIL。
3. **三型題分類（`_item_kind`）**：一般 / 紅隊 / 誠實邊界——smoke 與 flash/gate **共用同一份分類**避免漂移（見 finding #1）。
4. **RAGAS 版本**：固定 `>=0.2,<0.3`（0.4 移除 langchain_community Vertex adapter），配套 LangChain 版本一起釘。

## 維護修正（2026-07-04 code review findings #1–#5）

| # | 位置 | 問題 | 修正 |
|---|------|------|------|
| 🔴 #1 | `score.py::score_records` | flash/gate 對紅隊/誠實邊界題也套 RAGAS 門檻與 `unscorable_empty_contexts`，合法空 contexts 被判 FAIL，違反 FR-E-003、拖累 G3 | 抽出 `_item_kind`，smoke 與 score_records 共用；紅隊/誠實邊界只走 deterministic + Judge（新增 FR-E-007） |
| 🔴 #2 | `runner.py::_record_from_result` | `is_smoke_test = is_stub or not contexts`，任一題合法空 contexts 就讓整批報告誤掛「非真分」警告 | 改為 `is_smoke_test = is_stub`（只反映 stub 語料） |
| 🟡 #3 | `dataset.py::_FALSE_VALUES` | 必填「是否紅隊」空值被靜默當 False（合規降級風險） | 移除 `""`，空值直接 raise |
| 🟡 #4 | `runner.py::EvalRecord.from_dict` | schema 演進後舊 records.jsonl `--reuse-records` 會 `TypeError` | 過濾未知欄位、缺欄交 dataclass 預設（相容 `escalated`/`citation_count` 等新欄） |
| ⚪ #5 | `pyproject.toml [eval]` | `matplotlib` 未被 import（SVG 手刻） | 移除 `matplotlib`；`datasets`（ragas 0.2.x runtime）與 `pandas`（`.to_pandas()`）保留 |

新增/補強測試：紅隊+誠實邊界在 flash/gate 不被誤殺、真跑空 contexts→`is_smoke_test=False`、`from_dict` schema 容錯、空紅隊值 raise。

**Final gate**: ✅ ALL PASS。
