# Quickstart: LangGraph 5-Node Skeleton (Stub Mode)

> 5 分鐘讓任何隊友把這顆 feature 跑起來。對應 R5 e2e 驗收與 R3 替換真節點的起點。

## Prerequisites

- Python 3.11+
- 已 `git clone` polaris-desk repo 並 `cd polaris-desk`
- 不需要 `.env`（W1 D1 不呼叫 LLM）
- 不需要 pgvector / BigQuery（W1 D1 不連 DB）

## 1) 安裝 deps

```bash
# 建虛擬環境（若還沒做過）
python3.11 -m venv .venv
source .venv/bin/activate

# 安裝 polaris 與 dev deps
pip install -e ".[dev]"
```

預期：langgraph、pydantic、pytest 安裝完成。其他套件（google-genai、psycopg 等）會一併安裝，但本 feature **不會 import**。

## 2) 跑 e2e 測試（< 1 秒）

```bash
pytest tests/test_workflow_e2e.py tests/test_workflow_edges.py -v
```

預期：15 個測試全綠，分 5 個 class：

| Class | 測試數 | 對應 spec |
|---|---|---|
| `TestE2EHappyPath` | 5 | SC-001 / SC-002（端到端跑通、5 節點 trace 齊全、citations ≥ 1） |
| `TestE2EDeterminism` | 2 | SC-006（同問題連跑 3 次 byte-identical） |
| `TestE2ERuntime` | 1 | SC-004（總耗時 < 10 秒） |
| `TestE2EComplianceBlocks` | 2 | SC-003（買賣建議草稿被攔成 SAFE_MESSAGE） |
| `TestEmptyQuery` + `TestNodeException` | 4 + 3 | SC-007 / FR-008 / FR-009（halt 行為） |

整套 70 個測試一鍵跑：`pytest`（含 vectorstore / state / trace / compliance / node swap）。

## 3) CLI 跑一個範例問題

```bash
python -m polaris.cli ask "台積電 2025 Q1 營收 YoY 是多少？"
```

預期輸出：

```text
== Polaris Desk (W1 D1 stub mode) ==
Query     : '台積電 2025 Q1 營收 YoY 是多少？'
Answer    : （v0 假答案）依據引用來源，2025 Q1 營收 YoY 約 12.34%。本系統目前以 stub 假資料展示工作流骨架。
Compliance: passed
Citations :
  [1] stub-tsmc-2025Q1-001 — "（v0 stub）法說頁碼 X：營收 YYY 億元，YoY 約 12.34%。" (origin=stub)
Trace     :
  planner     ok         0ms  in=['query', 'trace']  out=['plan']
  retriever   ok         0ms  in=['plan', 'query', 'trace']  out=['contexts']
  calculator  ok         0ms  in=['contexts', 'plan', 'query', 'trace']  out=['calculations']
  writer      ok         0ms  in=['calculations', 'contexts', 'plan', 'query', 'trace']  out=['citations', 'draft']
  compliance  ok         0ms  in=['calculations', 'citations', 'contexts', 'draft', 'plan', 'query', 'trace']  out=['answer', 'compliance_status']
```

> 註：trace 的 `in=[...]` 永遠包含 `trace`，那是 `@traced` 裝飾器自己 emit 的 state 累加欄位（LangGraph reducer 用），不是節點業務輸入。

## 4) 看看「攔截買賣建議」實際長怎樣

CLI 內建測試旗標 `--stub-buysell` 會把 writer 換成固定回「建議買進台積電」的版本：

```bash
python -m polaris.cli ask "你看好台積電嗎？" --stub-buysell
```

預期關鍵欄位：

```text
Answer    : 本系統不提供買賣建議，僅描述事實與引用來源。
Compliance: blocked
```

5 個節點 trace 仍全 ok（compliance 節點是「正常跑完攔截」，非 error）。

## 5) 看看「空輸入守門」

```bash
python -m polaris.cli ask ""
```

預期關鍵欄位：

```text
Answer    : 請提供具體問題。
Compliance: unknown
Halt      : True
Trace     :
  planner     error      0ms  in=['query', 'trace']  out=[]  error=ValueError: empty query
```

下游 4 節點不出現在 trace（halt 後條件邊直接跳 terminal 節點，對應 SC-007）。

## 給隊友的對接指引

| 你的角色 | 你要做什麼 |
|---|---|
| **R3 Agent 工程師** | W1 D2 起，在 `src/polaris/graph/nodes/` 新增 `planner_agent.py` 等真實實作；改 `workflow.py` 的 `add_node()` import 來源即可。state 欄位（plan / contexts / calculations / draft / citations）契約已固定，沿用 |
| **R4 資料工程師** | retriever 節點目前 stub 回 `[{"source_id": "stub-...", "text": "..."}]`；你接 HybridRetriever 後保持同樣 shape，retriever 函式內 swap 即可 |
| **R5 Eval 工程師** | 用 `app.invoke({"query": q})` 接你的 Ragas pipeline；output 的 `answer` / `citations` 欄位是穩定 contract |
| **R6 金融品質** | `src/polaris/graph/compliance.py` 是純函式，W3 用完整關鍵字 / regex 替換內容；signature 不變 |
| **R7 Demo 前端** | 後端對接 contract 見 `contracts/workflow-invoke.md` |

## 常見問題

**Q: 為什麼沒設 GEMINI_API_KEY 也跑得起來？**
A: W1 D1 是 stub mode，所有節點回固定假資料、0 LLM 呼叫。等 R3 把真 agent 推進來才需要 key。

**Q: 為什麼 elapsed_ms 都是 0？**
A: stub 函式幾乎 instant；測試斷言時故意排除 `elapsed_ms` 欄位以保確定性。

**Q: trace 為什麼是 list 不是 dict？**
A: 同一節點未來可能因 retry（W2 D7）執行多次；用 list + `operator.add` reducer 完整保留每次嘗試。
