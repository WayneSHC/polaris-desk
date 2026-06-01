# Data Model: LangGraph 5-Node Skeleton (Stub Mode)

> 對應 spec Key Entities。實作位置：`src/polaris/graph/state.py`。

## Citation（pydantic BaseModel）

引用單筆紀錄。

| Field | Type | Required | Notes |
|---|---|---|---|
| `source_id` | `str` | yes | 來源識別（W1 stub 用如 `"stub-tsmc-2025Q1-001"`；後續週次用法說頁碼 / 新聞 URL hash） |
| `snippet` | `str` | yes | 被引用的原文片段（W1 stub 用固定假文字；後續為真實截取） |
| `origin` | `Literal["stub","bm25","embedding","colpali","rerank","news"]` | yes | W1 固定 `"stub"`；後續對應 4-way retrieval + 新聞 |

**Validation**：
- `source_id` 與 `snippet` 不可為空字串
- `origin` 限定 enum 值（Pydantic 自動驗）

## NodeTrace（pydantic BaseModel）

單次節點執行的紀錄，由 `@traced` 裝飾器自動 emit。

| Field | Type | Required | Notes |
|---|---|---|---|
| `node_name` | `str` | yes | `"planner"` / `"retriever"` / `"calculator"` / `"writer"` / `"compliance"` |
| `status` | `Literal["ok","error","skipped"]` | yes | 正常完成 / 例外 / 保留欄位（W1 D1 不使用 `skipped`） |
| `input_keys` | `list[str]` | yes | 節點進入時的 state keys 排序 |
| `output_keys` | `list[str]` | yes | 節點返回 state patch 的 keys 排序 |
| `error_message` | `str \| None` | no | `status="error"` 時必填，其餘為 None |
| `elapsed_ms` | `int` | yes | 從進入到返回（含例外）的 wall-clock 毫秒 |

**State transitions**：節點未開始 → `ok` / `error`。`skipped` 為保留枚舉，**W1 D1 實作不使用**——任一節點 halt 後，conditional edge 直接跳 `terminal` 節點，下游節點**不執行也不出現在 trace**（對應 spec SC-007）。預留 `skipped` 是給未來若加上「明示跳過某節點」（例如 W2 retry 失敗後標記）的可能。

## ResearchState（TypedDict，LangGraph state）

5 個節點共用、由 LangGraph 在節點間傳遞的狀態。為了確定性與 trace 累積，部分欄位使用 LangGraph `Annotated[..., reducer]` 模式。

| Field | Type | When written | Notes |
|---|---|---|---|
| `query` | `str` | 入口 | 使用者問題原文。W1 D1 唯一輸入欄位 |
| `plan` | `list[str]` | planner | 拆解後的步驟清單。stub 固定 3 步 |
| `contexts` | `list[dict[str, Any]]` | retriever | 檢索結果原料。stub 固定 1 筆 fake context |
| `calculations` | `dict[str, Any]` | calculator | 算出的指標。stub 固定 `{"YoY_pct": 12.34}` |
| `draft` | `str` | writer | 候選答案（未過 compliance）。stub 含可控的關鍵字觸發測試 |
| `answer` | `str` | compliance | **最終**輸出文字。compliance 通過則 = draft；攔截則 = 固定安全訊息 |
| `citations` | `list[Citation]` | writer | 引用清單（≥ 1 條 stub citation） |
| `compliance_status` | `Literal["passed","blocked","rewritten","unknown"]` | compliance | `passed` / `blocked` 為 W1 用；`rewritten` 預留 R6 W3；`unknown` 用於 halt |
| `trace` | `Annotated[list[NodeTrace], operator.add]` | every node (via decorator) | LangGraph reducer 自動 append；不可被覆蓋 |
| `halt` | `bool` | any node on error | 任一節點掛掉時設 True，conditional edge 直接跳 `terminal` 節點 → END（下游節點不執行、不出現在 trace） |

**Backwards compatibility**：
- 既有 starter `workflow.py` 的 `PolarisState` 留 `compliance_ok: bool` 欄位（被 `compliance_status` 取代），W1 D1 staging 期同時填兩個，後續 PR 拿掉 `compliance_ok`。
- 既有 `__main__` 的 `app.invoke({"query": ...})` 呼叫不變，保留 starter「跑得起來」的承諾。

**Initial state**（入口）：
```python
{"query": "<使用者問題>"}
```

**Terminal state**（成功路徑，所有欄位齊全）：
```python
{
    "query": "台積電 2025 Q1 營收 YoY",
    "plan": ["擷取相關段落", "計算指標", "撰寫並標引用"],
    "contexts": [{"source_id": "stub-tsmc-2025Q1-001", "text": "..."}],
    "calculations": {"YoY_pct": 12.34},
    "draft": "（v0 假答案）...",
    "answer": "（v0 假答案）...",
    "citations": [Citation(source_id="stub-tsmc-2025Q1-001", snippet="...", origin="stub")],
    "compliance_status": "passed",
    "trace": [NodeTrace(node_name="planner", status="ok", ...), ... 共 5 筆],
    "halt": False,
}
```

**Terminal state**（compliance 攔截）：
- `draft` = 含「建議買進」的 stub 文字
- `answer` = `"本系統不提供買賣建議，僅描述事實與引用來源。"`
- `compliance_status` = `"blocked"`
- 其餘照填

**Terminal state**（節點例外，halt）：
- 例如 retriever 拋例外
- `halt` = True
- `answer` = `"處理過程發生錯誤（節點：retriever），請查看 trace 細節。"`
- `compliance_status` = `"unknown"`
- `trace` 含 1 筆 planner ok + 1 筆 retriever error，**僅此 2 筆**；calculator / writer / compliance 因 halt 條件邊直接跳 `terminal` 節點而未執行，**不出現在 trace**（對應 spec SC-007 對空輸入 halt 的「下游 4 節點 status 不存在」精神，此處延伸到任一節點 halt）

## Question（W1 純概念，不獨立 model）

Spec Key Entities 列了 `Question`，W1 D1 為簡化 = 直接吃 `state["query"]: str`，不獨立成 pydantic model。W2 Temporal Anchoring 加 ticker / period 時再升級成 `Question(text, ticker, period_hint)` model。

---

## 對 spec 的對應

| Spec Key Entity | data-model.md 落地 |
|---|---|
| Question | `state["query"]: str`（W1 簡化） |
| ResearchState | `ResearchState` TypedDict |
| Citation | `Citation` pydantic model |
| NodeTrace | `NodeTrace` pydantic model |

| Spec FR | 模型上的落實 |
|---|---|
| FR-004 `answer + citations` | `answer: str` + `citations: list[Citation]` |
| FR-005 Compliance 攔截 | `compliance_status` 4 種狀態 + `answer` 被 compliance 改寫 |
| FR-006 trace 完整 | `trace: Annotated[list[NodeTrace], operator.add]` reducer 確保不丟失 |
| FR-008 空輸入守門 | planner 進入時檢查 `query.strip()`，空則 halt |
| FR-009 例外處理 | `@traced` 裝飾器 + `halt` 欄位 + conditional edge |
| FR-010 確定性 | 所有 stub 函式無時間 / 隨機；唯一非確定 = `elapsed_ms`（測試斷言時排除） |
