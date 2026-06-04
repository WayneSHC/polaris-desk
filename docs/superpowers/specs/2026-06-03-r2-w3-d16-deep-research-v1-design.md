# R2 W3 D16 — Deep Research v1：過驗收（≤6 / ≥3 / 句句可溯源 / 0 買賣建議）設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：FR-004、Deep Research v1 驗收門檻、**場景 2（Deep Research 主秀，同業比較）**：「比較 A 與 B 最近兩季毛利率變化」→ **≤6 迴圈、≥3 引用、結論可溯源、0 買賣建議**、R2 spec §3 W3 D16
**前置**：D15（v0 ReAct loop：state/agent、≤6 should_continue、evidence 累積、D9 Compliance）
**範圍決策**：用戶選 **(a) 硬保證 verify-or-synthesize（所有路徑）**

---

## 1. 目的

把 D15 v0 推到**過驗收**。四門檻中 v0 已覆蓋 ≤6（`should_continue`）、≥3（確定性 facet 政策）、0 買賣（D9 Compliance）；**新增「句句可溯源」的結構保證 + 驗收測試**。

場景 2 期望輸出含「並列數字表」需 R4 真實財務資料 → stub 階段不做（記為 pending R4）；
但 **≤6 / ≥3 / 可溯源 / 0 建議** 四門檻以 stub evidence 即可達成並驗收。

---

## 2. 變更（對 D15 小幅、加法）

### ① `_synthesize` → 結構化、逐點可溯源（`agent.py`）
```
關於「{question}」的研究摘要（依據 {n} 條引用）：
- {snippet_1}（來源：{source_id_1}）
- {snippet_2}（來源：{source_id_2}）
- {snippet_3}（來源：{source_id_3}）
本回答僅描述事實與來源，不提供買賣建議。
```
每點 = 一條 evidence + 其 source_id → **句句可溯源 by construction**（同時滿足場景 2「≥3 點摘要、各自來源」）。

### ② `is_fully_traceable(answer, evidence) -> bool`（`state.py`）
- 每個 bullet（`- ` 開頭）行須含 `（來源：sid）` 且 `sid ∈ evidence`；
- 至少 1 個 bullet；header / disclaimer 等 meta 行豁免；
- 自由文（無 tagged bullet）→ False。純函式、確定性可測。

### ③ v1 可溯源硬保證（`run_deep_research`，compliance 前）
```python
candidate = state["final_answer"]
if state["evidence"] and not is_fully_traceable(candidate, state["evidence"]):
    candidate = _synthesize(question, state["evidence"])   # 未通過（含 LLM 自由文）→ grounded 結構摘要
```
- gated on **evidence present** → 不破 D15「無證據 finish」測試（advisory→blocked、即時 LLM finish）。
- 接地 > 文采（法遵取向）；LLM 推理仍保留在 `react_steps`（審計）。

---

## 3. 測試（TDD，red-green-refactor）

`tests/test_deep_research_acceptance.py`：
- **驗收（場景 2）**：問「比較台積電與聯發科最近兩季的毛利率變化」→ 斷言
  `iterations ≤ 6`、`len(evidence) ≥ 3`、`is_fully_traceable(answer, evidence)`、
  `compliance_status == "passed"`、0 買賣關鍵字；**可重現**（同輸入兩跑相同）。
- **`is_fully_traceable`**：全有效 tag→True；bullet 缺 tag→False；tag 不在 evidence→False；自由文→False。
- **硬保證**：LLM 自由文 finish + 有 evidence → 最終答案轉為結構化可溯源（is_fully_traceable True）。

---

## 4. 不變量

- 無新增依賴；`workflow.py` / `state.py`(5 節點) / `compliance.py` 不動。
- 既有測試全綠（format 變更維持非空/no-buysell/確定性；硬保證 gated on evidence 不破無證據測試）。

---

## 5. Constitution

- **I（NFR-031）**：最終結論過 D9 Compliance；結構化答案不含買賣建議。
- 「結論可溯源」以結構保證 + 檢查器落實（FR-004 驗收門檻）。

---

## 6. 交付物

程式 + 測試（TDD）· 本設計文件 · R2 spec D16 → `[x]`（repo + Drive mirror）· 專案記憶更新 · PR + admin-merge。接著 D17 G3 評審。

---

## 7. 事故註記（2026-06-03）

本任務一度因 **Desktop repo 的同步/備份代理回滾檔案 + git 狀態**，導致首次 D16 實作未進 remote（PR #25 僅含設計文件）。本版為乾淨重建（自 origin/main #24 起、含 required CI）。Root cause（同步回滾 Desktop 工作目錄）需單獨處理，已向使用者標示。
