# R2 W2 D9 — Compliance Agent（節點接入 / 強化）設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：憲法 Principle I / NFR-031、spec FR-005 / SC-003、R2 spec §3 W2 D9
**前置**：W1（compliance.py 6 關鍵字 floor）、D2/D3（Planner/Writer Agent graduation 模式）、D7（retry primitive）

---

## 1. 目標與邊界

把 Compliance 節點從「6 條 substring 黑名單」**畢業成真正的 Agent**——沿用 Planner(D2)/Writer(D3) 的 graduation（Gemini smart 路徑 + 確定性 fallback），在 **R6 W3 紅隊攻擊之前**先強化 NFR-031 防禦。

### 角色邊界（重要）
- **R2（我，D9）＝建防禦**：Compliance Agent 節點本身（編排 / smart 層 / fail-safe 組合）。
- **R6（W3）＝建攻擊 + 字典**：紅隊題庫、Ontology/lexicon 擴充、實際攻擊系統。
- `BUYSELL_KEYWORDS` 被 `test_exactly_six_keywords` **鎖死＝6 條**；D9 **不動關鍵字數**（lexicon 擴充是 R6 的事）。「Agent 化」＝**加 LLM 偵測層**，不是加關鍵字。

---

## 2. 架構：defense-in-depth，fail-to-floor

新 `src/polaris/graph/nodes/compliance_agent.py`（鏡像 `planner_agent.py` / `writer_agent.py`）。
`src/polaris/graph/compliance.py`（純確定性 floor）**byte 不動**，被 compliance_agent import 當地基。

```
review(draft, client) -> (answer, status):
  Layer 1  answer, status = apply_compliance(draft)      # 6 關鍵字 floor，永遠先跑
           if status == "blocked": return                # floor 命中即收；LLM 不被諮詢、永不解除
  Layer 2  if client:                                     # smart 層，僅有金鑰時
             try: flagged = call_with_retry(λ: llm_flags_violation(draft, client))   # D7 retry
             except: flagged = False                      # fail-to-floor：LLM 錯 → 退回 floor 的 "passed"
             if flagged: return SAFE_MESSAGE, "blocked"   # LLM 只「加攔」
           return draft, "passed"
```

### 不變量（強化重點）
1. **floor 先跑、命中即贏**：LLM 只能**加攔**，永不**解除** floor 已攔的結果。
2. **LLM 永不改寫** draft——只回 verdict → 零 prompt-injection（模型無從把建議塞進輸出）。攔截輸出恆為 `SAFE_MESSAGE`（SC-003 不破）。
3. **fail-to-floor，非弱化保證**：Gemini 掛掉 → 不比今天的 keyword-only floor 差。LLM 是既有保證**之上**的 best-effort 增強，絕不放寬保證。
   - （反例：fail-closed＝LLM 一錯就全攔，會讓研究工具在 Gemini 任何抖動時不可用 → 否決。）

---

## 3. 偵測層

- `COMPLIANCE_SYSTEM_PROMPT`：台灣證券法遵審查者，攔**顯性或隱性**買賣建議（進場時機 / 逢低布局 / 值得擁有 / 現在很適合…），用 **Flash**（分類任務、便宜快速）。
- `llm_flags_violation(draft, client) -> bool`：解析嚴格 verdict token（`VIOLATION` / `違規` → True；`CLEAN` / `合規` / 模糊 / 空 → False——保守但不過殺；6 關鍵字仍由 floor 守）。

---

## 4. 節點接入（`stubs.py`，單一節點）

```python
@traced("compliance")
def compliance(state):
    final, status = compliance_agent.review(state.get("draft", ""), active_llm())
    return {"answer": final, "compliance_status": status}   # 輸出契約不變
```

- 無金鑰（CI）→ floor-only → **與今天行為 byte 一致** → 既有 compliance/e2e/state 測全過不改。
- `workflow.py` / `state.py` / `compliance.py` 不動 → `test_node_swap` + 5 節點 trace 契約不變。

---

## 5. 測試（TDD，red-green-refactor）

`tests/test_compliance_agent.py`：
- **floor**：關鍵字 draft（有/無 client）→ blocked + SAFE_MESSAGE；命中時 LLM **不被呼叫**（`client.calls == []`）。合規 draft 無 client → passed 原文不變。
- **LLM 層**：零關鍵字但隱性建議 + FakeLLM `VIOLATION` → blocked；FakeLLM `CLEAN` → passed 不變；verdict 呼叫用 `flash=True` + system_instruction + draft 在 prompt。
- **fail-to-floor**：持續暫時性錯誤 → passed（退 floor）、不崩、retry 3 次（D7）；永久性錯誤 → 1 次呼叫、passed。
- **LLM-never-unblocks**：關鍵字 draft + FakeLLM `CLEAN` → 仍 blocked（floor 短路，LLM 不被呼叫）。
- **verdict parsing** 表。
- **節點整合**：monkeypatch `stubs.active_llm` → FakeLLM，advisory draft → 節點 blocked。

---

## 6. Constitution 遵循

- **I / NFR-031**：本任務即強化它。攔截輸出不含 6 關鍵字（SC-003）。
- **VI**：Gemini 走 `active_llm()` / google-genai（Flash）。**III**：金鑰沿用 `active_llm()`，無新增金鑰路徑。

---

## 7. 交付物

程式 + 測試（TDD）· 本設計文件 · R2 spec D9 → `[x]`（repo + Drive mirror）· 專案記憶更新 · PR + admin-merge（沿用 #11/#12/#14/#18 模式）。
