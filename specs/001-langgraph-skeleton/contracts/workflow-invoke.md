# Contract: `workflow.invoke()` (W1 D1 Stub Mode)

> 本檔定義 LangGraph compiled app 的對外契約。R3 / R4 / R5 / R7 對接此 contract 開發，不需要看 workflow 內部。

## Entry point

```python
from polaris.graph.workflow import build_workflow

app = build_workflow()
result = app.invoke({"query": "台積電 2025 Q1 營收 YoY"})
```

## Input

| Key | Type | Required | Notes |
|---|---|---|---|
| `query` | `str` | yes | 自然語言問題。W1 唯一輸入欄位。空字串或全空白 → 觸發 FR-008 守門 |

任何其他 key 都會被 LangGraph 忽略（TypedDict 容錯）。

## Output（正常路徑）

回傳 dict，包含以下 key（皆必出現）：

| Key | Type | Notes |
|---|---|---|
| `query` | `str` | echo 輸入 |
| `answer` | `str` | 最終要顯示給使用者的文字（已過 compliance） |
| `citations` | `list[Citation]` | ≥ 1 條引用（W1 stub 含 1 條固定 citation） |
| `compliance_status` | `Literal["passed","blocked","rewritten","unknown"]` | W1 D1 出現的值：`passed` 或 `blocked` 或 `unknown`（halt 時） |
| `trace` | `list[NodeTrace]` | 完整 5 筆（正常路徑）；halt 時為「成功節點 + 失敗節點」共 N 筆（無下游 skipped 條目，halt 後條件邊直接跳 terminal） |
| `halt` | `bool` | True = 中斷路徑；False = 正常完成 |
| `plan`, `contexts`, `calculations`, `draft` | various | 各節點輸出，供 debug / R3 替換時驗證用 |

## Output（compliance 攔截）

當 writer 草稿含買賣建議關鍵字（W1 6 個：建議買進 / 建議賣出 / 加碼 / 減碼 / 看多 / 看空）：

```python
{
    "query": "...",
    "draft": "...建議買進台積電...",
    "answer": "本系統不提供買賣建議，僅描述事實與引用來源。",
    "compliance_status": "blocked",
    "halt": False,
    "trace": [...5 筆 ok...],
    # 其餘正常欄位
}
```

合約承諾：`answer` 字串中**保證不出現** 6 個關鍵字中任何一個（SC-003 = 0）。

## Output（空輸入）

`query=""` 或 `query="   "`：

```python
{
    "query": "",
    "answer": "請提供具體問題。",
    "halt": True,
    "compliance_status": "unknown",
    "trace": [
        NodeTrace(node_name="planner", status="error", error_message="empty query", ...)
    ],
    # 沒有 plan / contexts / calculations / draft / citations
}
```

合約承諾：除了 `planner`，其他 4 個節點的 trace **不應出現**（SC-007）。

## Output（節點例外）

任一非 planner 節點拋例外，例如 retriever：

```python
{
    "query": "...",
    "plan": [...3 步...],
    "answer": "處理過程發生錯誤（節點：retriever），請查看 trace 細節。",
    "halt": True,
    "compliance_status": "unknown",
    "trace": [
        NodeTrace(node_name="planner", status="ok", ...),
        NodeTrace(node_name="retriever", status="error", error_message="<exception text>", ...),
        # ← 下游 calculator / writer / compliance 不出現
        #    （halt 後條件邊直接跳 terminal 節點，下游節點未被執行）
    ],
}
```

合約承諾：
- 例外不會 propagate 出 `app.invoke()`（呼叫端不需要 try/except）
- 下游節點不會被執行，且**不出現在 trace 中**（halt 後條件邊直接跳 `terminal` 節點 → END）
- `NodeTrace` 的 `status="skipped"` 是保留枚舉，W1 D1 實作不使用

## Determinism guarantee

對同一 `query` 字串，連續呼叫 N 次 `app.invoke({"query": q})`，回傳 dict 中**除了 `trace[i].elapsed_ms`**，其他所有欄位（含 `answer` 字串、`citations` 內容、`compliance_status`）必須 **byte-by-byte 相同**（SC-006）。

實作上的承諾：
- Stub 節點不呼叫 LLM、不讀檔、不連網
- 不使用 `random` / `time.time()` / `uuid` 作為輸出
- LangGraph state reducer 只用確定性 operator（`operator.add` for list）

## Versioning

| 版本 | 內容 |
|---|---|
| **v0.1** (W1 D1, this contract) | Stub mode 全套；6 關鍵字 compliance；TypedDict 狀態 |
| v0.2 (W1 D2+) | R3 換 Planner / Writer 為真 agent；contract 不破 |
| v0.3 (W2 D6) | 加 `ticker`、`period_hint` input keys（Temporal Anchoring）；output 不破 |
| v0.4 (W2 D7) | 加 retry — `trace` 多 `attempt` 欄位；其他不破 |

每次升級必須 **append-only**：不可移除既有 output key，不可改既有 key 的型別。
