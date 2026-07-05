# Feature Specification: Eval Pipeline（Ragas 評測管線）

**Feature Branch**: `r5/004-eval-pipeline`
**Created**: 2026-06-10
**Status**: Phase 1 + Phase 2 implemented（smoke 達標率 + Ragas 真分 + 三方 Judge gate；SDD plan/tasks 於 2026-07-04 回補，見 [plan.md](plan.md) / [tasks.md](tasks.md)）
**Owner**: R5（Eval Lead）；R2 代鋪管線骨架
**上位文件**: 憲法 §IV（Eval 即品質門檻）、`docs/R5_eval_開工指南.md`、R5 角色 spec

---

## 一句話

題庫 CSV → 每題跑 workflow / Deep Research → 收齊 Ragas 四件套 →
smoke 達標率（CI、token=0）+ Ragas CP/Faithfulness/AR（`[eval]` extra、閘門才跑）。

---

## User Stories

### US1 — R5 對任一題收齊 Ragas 四件套（P1，MVP）

`run_item(item)` 回 `EvalRecord`：question / answer / contexts / ground_truth
＋ compliance_status / citation_count。場景 2 自動走 Deep Research。

### US2 — smoke 達標率（P1）

`python -m polaris.eval` 跑全題庫印達標率與不及格清單；
報告**誠實標註「pipeline 煙測分、非 G3 真分」**（stub 語料階段）。

### US3 — Ragas 真分（P2，Phase 2 ✅ 已實作）

裝 `[eval]` extra + 金鑰後跑 CP ≥0.85 / Faithfulness ≥0.90 / AR ≥0.85；
未裝即誠實回 None，**絕不假分**。`gate` 模式另加 Claude/GPT/Gemini 三方 Judge
2/3 投票（`judges.py`）。實作見 `score.py::ragas_score` / `_evaluate_ragas`
（judge 模型預設 `gemini-3-flash-preview`；`ragas` 固定 `>=0.2,<0.3`，見 pyproject 註解）。

---

## Functional Requirements

| FR | 描述 |
|----|------|
| FR-E-001 | 題庫 CSV 欄位 = `題號,場景,問題,golden_answer,公司,季別,類別,是否紅隊`（缺欄即拋）|
| FR-E-002 | 場景 2 走 `run_deep_research`，其餘走 `app.invoke`；R4 真檢索後 runner 零改動 |
| FR-E-003 | smoke 檢查分三型：一般（answer+contexts+引用+compliance）、紅隊（0 關鍵字）、誠實邊界（「資料不足」）|
| FR-E-004 | 紅線 exit code：任何題出現買賣建議關鍵字 → CLI 回 1 |
| FR-E-005 | Ragas 依賴只進 `[eval]` extra；CI 不裝、不跑 judge（token 紀律 §IV）|
| FR-E-006 | 報告含不及格清單（R5 只出分不修題，回報 owner）|
| FR-E-007 | 紅隊與誠實邊界題在 **flash/gate 亦不套** RAGAS 三指標門檻（contexts 合法為空），只走 deterministic 檢查＋Judge 對照 golden；否則正確拒答／「資料不足」會被 `unscorable_empty_contexts` 誤殺。分類與 smoke 共用 `score.py::_item_kind`（單一事實來源、防漂移）|

## Non-Functional

- NFR-E-001：CI 全程 token=0、確定性（同題庫兩跑同分）。
- NFR-E-002：報告必標「煙測分 vs 真分」，防止 G1 階段誤判 G3 已過。

## 題庫 roadmap（R5 開工指南 §4）

- **W1（本 PR）**：25 題（財務基本 / 檢索 / 時間錨定 / 誠實邊界 / 同業比較 / 跨產業 / 紅隊 ×3）
- W2：75 題（R6 出財務/紅隊題 + 標 golden）
- W3：130 題（含新聞 / 跨產業），G3 真分 ≥80%

> ⚠️ **題庫覆蓋備註**：現行預設 `questions_v1.csv`（130 題）**不含任何「誠實邊界」題**
> （類別只有 財務基本 / 營收分析 / 紅隊 / 同業比較 / 圖表 ColPali / 跨產業營收拆解）。
> 這正是 FR-E-007 的 bug（flash/gate 誤殺誠實邊界題）長期沒被題庫抓到的原因。
> `Questions_v2.csv` 已補回 9 題誠實邊界＋改用真正誘導型紅隊題；該分支的誠實邊界分支
> 目前由單元測試（`test_polaris_eval_score.py`）直接涵蓋，切 v2 為預設見 tasks.md T-DEFER-1。

## Phase 2 現況（2026-07-04 更新，均已實作）

原 Phase 1「Out of Scope」三項現已完成：

- ✅ **Ragas judge 接 Gemini**：`score.py::_evaluate_ragas`（CP/Faithfulness/AR，judge 預設 `gemini-3-flash-preview`）
- ✅ **三方 Judge**：`judges.py`（Claude/GPT/Gemini 2/3 投票，只在 `gate` 模式跑）
- ✅ **eval CI job**：`.github/workflows/ci.yml` 已含 `eval-smoke`（token-free）、`eval-flash`、`eval-gate`

## 仍 Out of Scope

- 場景 3 圖表題的真視覺回答：目前走 workflow 的 visual_reader 升級節點（`escalated`＝任一 citation `origin=='vision'`），eval 只量升級率，讀圖數字回答屬後續
- eval 分數自動回灌 Watchdog / 通知中心（跨 feature）
- `Questions_v2.csv` 切為 CLI 預設題庫（現預設仍 `questions_v1.csv`，見 tasks.md T-DEFER-1）
